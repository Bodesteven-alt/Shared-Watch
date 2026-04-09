# Watchlist Pages Auto Sync

This project supports a static GitHub Pages frontend (`docs/`) fed by your local scraper cache (`data/cache.json`).

## What runs where

- Local PC: scraper + exporter + git push
- GitHub Pages: static UI (`docs/index.html`, `docs/app.js`, `docs/styles.css`)

## Repository structure

- `docs/` static frontend for GitHub Pages
- `docs/data/watchlist.json` generated data file
- `scripts/export_watchlist.py` converts local cache to Pages JSON
- `scripts/refresh_local_cache.py` one-shot fetch (Letterboxd + IMDb) into `data/cache.json`
- `scripts/startup_sync.ps1` refresh cache + export + commit-if-changed + push
- `scripts/setup_startup_task.ps1` creates Task Scheduler job

## 1) Export static JSON

From repo root:

```powershell
python .\scripts\export_watchlist.py
```

Optional environment overrides:

- `WATCHLIST_SOURCE_CACHE` (default: `data/cache.json`)
- `WATCHLIST_OUTPUT_JSON` (default: `docs/data/watchlist.json`)
- `WATCHLIST_METADATA_CACHE` (default: `data/imdb_metadata_cache.json`)

### Metadata enrichment

The exporter enriches each movie with best-effort metadata (no API key):

- `year`
- `genres[]`
- `rating_imdb_10`
- `rating_letterboxd_5` (if present in source cache)
- `rating_avg_5` (normalized average on 0-5 scale)

Metadata is cached to speed up subsequent runs. If IMDb page scraping is blocked for a title, exporter falls back to TMDB public pages for year/genre/rating fields.

## 2) GitHub Pages setup

1. Push this repo to GitHub (`main` branch).
2. Open repository Settings -> Pages.
3. Set Source to `Deploy from branch`.
4. Choose branch `main`, folder `/docs`.
5. Save. Your site will be published at your GitHub Pages URL.

## 3) One-time Git auth

Run one push manually first so Windows credential manager stores credentials:

```powershell
git push -u origin main
```

## 4) Automatic startup sync

Create startup task (run as your user):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_startup_task.ps1
```

This task runs at logon and executes:

```powershell
.\scripts\startup_sync.ps1
```

That script:

1. Runs `refresh_local_cache.py` (scrapes both lists and updates `data/cache.json`)
2. Exports `docs/data/watchlist.json`
3. Stages the file
4. Commits only if changed
5. Pushes to GitHub

Logs: `scripts/logs/startup_sync.log`

### TMDb credentials (posters, streaming providers)

Refresh and streaming enrichment need TMDb in the **same environment** as the Python process (Task Scheduler does not load a `.env` file).

Set either or both:

- `TMDB_READ_ACCESS_TOKEN` — API Read Access Token (Bearer); recommended for watch-provider data.
- `TMDB_API_KEY` — v3 API key (`api_key` query param).

Or create one-line gitignored files under `data/` (no quotes):

- `data/tmdb_read_access_token.txt`
- `data/tmdb_api_key.txt`

When **both** are set, the app sends **Bearer and `api_key`** together (best compatibility with TMDb v3).

If watch listings stay empty after fixing credentials, delete **`data/tmdb_watch_providers_cache.json`** once and run refresh again so old empty entries are not reused until cache expiry.

### Troubleshooting startup sync

- Confirm the task exists: `schtasks /Query /TN WatchlistGitHubPagesSync`
- Read the log: `scripts/logs/startup_sync.log` (look for Python or git errors)
- Run history: `scripts/logs/startup_sync_attempts.log` — one line per run, comma-separated ISO timestamp and exit code (`timestamp,exit_code`)
- To start the local Flask site at logon, run `.\scripts\setup_site_startup_task.ps1` (creates task `WatchlistLocalSite`). Optional delay: `-LogonDelayMinutes` (0–1439) on `setup_startup_task.ps1` and `setup_site_startup_task.ps1`
- At logon, `py -3.12` must resolve (Windows Launcher). If not, install Python 3.12 or change `startup_sync.ps1` to use a full path to `python.exe`
- IMDb uses Selenium; if refresh fails right after logon, try adding a short delay in Task Scheduler (task Properties → Triggers → Delay task for) so the desktop and browser drivers are ready, or pass `-LogonDelayMinutes` when registering the task

## Verification checklist

- `python .\scripts\refresh_local_cache.py` updates `data\cache.json` from the live lists
- `python .\scripts\export_watchlist.py` updates `docs/data/watchlist.json`
- Opening `docs/index.html` locally renders data
- Startup sync script commits only when JSON changes
- GitHub Pages URL shows updated data after push
