#!/bin/bash
# Our Watch List - Linux sync (replaces scripts/startup_sync.ps1 on Windows)
# refresh cache -> export Pages JSON -> commit (JSON + index.html) if changed -> push
#
# IMDb blocks headless browsers (flat 403) and Firefox (Human Verification).
# What works: VISIBLE Chrome. On this host the real :0 display wedges
# Chromium before it creates a window, so the sync runs Chrome on a
# virtual Xvfb display instead. A persistent Chrome profile
# (data/chrome_imdb_profile, gitignored) carries the WAF cookies.
set -u
REPO="$HOME/shared-watch"
LOG_DIR="$REPO/scripts/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/sync.log"
ATTEMPTS="$LOG_DIR/sync_attempts.log"
export PATH="$HOME/tools/xvfb/usr/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
export GIT_EXEC_PATH="$HOME/tools/git/usr/lib/git-core"
exec 9>"$LOG_DIR/.sync.lock"
if ! flock -n 9; then
  echo "[$(date -Is)] another sync is running, exiting" >> "$LOG"
  exit 0
fi
log() { echo "[$(date -Is)] $*" >> "$LOG"; }
finish() {
  local code=$1
  echo "$(date -Is),$code" >> "$ATTEMPTS"
  printf '{"finished_at": "%s", "exit_code": %s}\n' "$(date -Is)" "$code" > "$LOG_DIR/last_run_status.json"
  log "Exit code $code"
  exit $code
}
cd "$REPO" || finish 1
# Daily snapshot of the pipeline state files (kept 14 days) so a bad run or
# a corrupt cache can be rolled back by hand.
SNAP_DIR="$REPO/data/backups/$(date +%F)"
mkdir -p "$SNAP_DIR"
cp -f data/cache.json data/posters.json data/imdb_ids.json data/imdb_metadata_cache.json data/tmdb_watch_providers_cache.json "$SNAP_DIR/" 2>/dev/null || true
find "$REPO/data/backups" -maxdepth 1 -type d -mtime +14 -exec rm -rf {} + 2>/dev/null || true
export SELENIUM_BROWSER=chrome
export SELENIUM_HEADLESS=0
export IMDB_ALLOW_VISIBLE_FALLBACK=0
export SELENIUM_CHROME_USER_DATA_DIR="$REPO/data/chrome_imdb_profile"
PY="$REPO/.venv/bin/python"
log "======== Run start ========"
log "Host=$(hostname) User=$USER Repo=$REPO"
"$PY" --version >>"$LOG" 2>&1
log "--- refresh (visible Chrome under Xvfb) ---"
xvfb-run -a -s "-screen 0 1280x900x24" "$PY" scripts/refresh_local_cache.py >>"$LOG" 2>&1 || finish $?
log "Refresh completed"
log "--- export ---"
"$PY" scripts/export_watchlist.py >>"$LOG" 2>&1 || finish $?
log "Export completed"
log "--- validation gate ---"
git show HEAD:docs/data/watchlist.json > "$LOG_DIR/prev_watchlist.json" 2>/dev/null || rm -f "$LOG_DIR/prev_watchlist.json"
if ! "$PY" scripts/validate_export.py docs/data/watchlist.json "$LOG_DIR/prev_watchlist.json" >>"$LOG" 2>&1; then
  log "VALIDATION FAILED: reverting docs, publish aborted, last good export stays live"
  git checkout -- docs/data/watchlist.json docs/index.html >>"$LOG" 2>&1
  finish 1
fi
log "Validation passed"
if [ ! -d .git ]; then log "Not a git repo, skipping push"; finish 0; fi
git add -- docs/data/watchlist.json docs/index.html >>"$LOG" 2>&1
if git diff --cached --quiet; then log "No data changes to commit"; finish 0; fi
git commit -m "auto-update watchlist data" >>"$LOG" 2>&1 || finish $?
git push >>"$LOG" 2>&1 || finish $?
log "Push completed"
finish 0
