"""Local combined Letterboxd + IMDb watchlist viewer."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone

from flask import Flask, redirect, render_template, request, url_for

import config
import posters
import scrape

app = Flask(__name__)
log = logging.getLogger("watchlist")

os.makedirs(os.path.dirname(config.CACHE_PATH), exist_ok=True)

_refresh_lock = threading.Lock()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_cache() -> dict:
    if not os.path.isfile(config.CACHE_PATH):
        return {
            "updated_at": None,
            "letterboxd": [],
            "imdb": [],
            "imdb_items": [],
            "rows": [],
            "stats": {},
            "poster_stats": {},
            "log": [],
            "letterboxd_error": None,
            "imdb_error": None,
        }
    try:
        with open(config.CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {
            "updated_at": None,
            "letterboxd": [],
            "imdb": [],
            "imdb_items": [],
            "rows": [],
            "stats": {},
            "poster_stats": {},
            "log": [],
            "letterboxd_error": None,
            "imdb_error": None,
        }


def _save_cache(data: dict) -> None:
    tmp = config.CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, config.CACHE_PATH)


def _run_refresh(*, log_prefix: str = "") -> dict:
    """Fetch both lists, merge, write cache. Caller must hold _refresh_lock when needed."""
    log_lines: list[str] = []
    previous = _load_cache()

    def append(msg: str) -> None:
        line = f"{log_prefix}{msg}" if log_prefix else msg
        log_lines.append(line)

    lb, lb_err = scrape.get_letterboxd_titles(log=append)
    append(f"[Done] Letterboxd: {len(lb)} titles")

    im_items, im_err = scrape.get_imdb_items(use_selenium=True, log=append)
    im = [x.get("title", "") for x in im_items if x.get("title")]
    if not im and (previous.get("imdb_items") or previous.get("imdb") or []):
        im_items = previous.get("imdb_items") or [{"title": t, "imdb_id": None} for t in (previous.get("imdb") or [])]
        im = [x.get("title", "") for x in im_items if x.get("title")]
        append(f"[IMDb] Using previous cached IMDb list ({len(im)} titles) because current fetch failed")
        im_err = None
    append(f"[Done] IMDb: {len(im)} titles")

    rows, stats = scrape.merge_watchlists(lb, im, imdb_items=im_items)
    rows, poster_stats = posters.enrich_rows_with_posters(rows, log=append)

    payload = {
        "updated_at": _utc_now_iso(),
        "letterboxd": lb,
        "imdb": im,
        "imdb_items": im_items,
        "rows": rows,
        "stats": stats,
        "poster_stats": poster_stats,
        "log": log_lines[-200:],
        "letterboxd_error": lb_err,
        "imdb_error": im_err,
    }
    _save_cache(payload)
    log.info(
        "Refresh saved: %d unique titles (LB err=%s, IMDb err=%s)",
        stats.get("total", 0),
        lb_err,
        im_err,
    )
    return payload


def _periodic_refresh_loop() -> None:
    interval_sec = max(60, config.AUTO_REFRESH_MINUTES * 60)
    log.info("Auto-refresh every %s minutes", config.AUTO_REFRESH_MINUTES)
    while True:
        time.sleep(interval_sec)
        if not _refresh_lock.acquire(blocking=False):
            log.info("Skipping scheduled refresh; another run is in progress")
            continue
        try:
            _run_refresh(log_prefix="[scheduled] ")
        except Exception:
            log.exception("Scheduled refresh failed")
        finally:
            _refresh_lock.release()


def _delayed_startup_refresh() -> None:
    time.sleep(max(1, config.AUTO_REFRESH_START_DELAY_SEC))
    if not _refresh_lock.acquire(blocking=False):
        log.info("Skipping startup refresh; another run is in progress")
        return
    try:
        _run_refresh(log_prefix="[startup] ")
    except Exception:
        log.exception("Startup refresh failed")
    finally:
        _refresh_lock.release()


def _start_background_jobs() -> None:
    if config.AUTO_REFRESH_MINUTES > 0:
        threading.Thread(
            target=_periodic_refresh_loop,
            daemon=True,
            name="watchlist-periodic-refresh",
        ).start()
    if config.AUTO_REFRESH_ON_START:
        threading.Thread(
            target=_delayed_startup_refresh,
            daemon=True,
            name="watchlist-startup-refresh",
        ).start()


@app.route("/", methods=["GET"])
def index():
    cache = _load_cache()
    filter_q = (request.args.get("q") or "").strip().lower()
    sort = request.args.get("sort") or "title"
    source = request.args.get("source") or "all"

    all_rows = cache.get("rows") or []
    rows = list(all_rows)
    if source == "both":
        rows = [r for r in rows if r.get("letterboxd") and r.get("imdb")]
    elif source == "letterboxd":
        rows = [r for r in rows if r.get("letterboxd") and not r.get("imdb")]
    elif source == "imdb":
        rows = [r for r in rows if r.get("imdb") and not r.get("letterboxd")]

    if filter_q:
        rows = [r for r in rows if filter_q in (r.get("display") or "").lower()]

    if sort == "source":
        rows = sorted(
            rows,
            key=lambda r: (
                -(int(r.get("letterboxd")) + int(r.get("imdb"))),
                (r.get("display") or "").lower(),
            ),
        )
    elif sort == "recent":
        rows = list(reversed(rows))

    filtered_stats = {
        "filtered_total": len(rows),
        "all_total": len(all_rows),
    }

    return render_template(
        "index.html",
        rows=rows,
        stats=cache.get("stats") or {},
        poster_stats=cache.get("poster_stats") or {},
        filtered_stats=filtered_stats,
        updated_at=cache.get("updated_at"),
        log_lines=cache.get("log") or [],
        letterboxd_error=cache.get("letterboxd_error"),
        imdb_error=cache.get("imdb_error"),
        filter_q=request.args.get("q") or "",
        sort=sort,
        source=source,
        letterboxd_url=config.LETTERBOXD_WATCHLIST_URL,
        imdb_url=config.IMDB_WATCHLIST_URL,
        selenium_headless=config.SELENIUM_HEADLESS,
        auto_refresh_minutes=config.AUTO_REFRESH_MINUTES,
        auto_refresh_on_start=config.AUTO_REFRESH_ON_START,
        posters_enabled=bool(config.TMDB_API_KEY),
    )


@app.route("/refresh", methods=["POST"])
def refresh():
    with _refresh_lock:
        _run_refresh(log_prefix="[manual] ")
    return redirect(url_for("index"))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    # Avoid duplicate background threads when Flask debug reloader spawns a child process.
    if (not debug) or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        _start_background_jobs()
    app.run(host=host, port=port, debug=debug, threaded=True, use_reloader=debug)


if __name__ == "__main__":
    main()
