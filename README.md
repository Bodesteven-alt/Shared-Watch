# Watchlist Pages Auto Sync

This project supports a static GitHub Pages frontend (`docs/`) fed by your local scraper cache (`data/cache.json`).

## What runs where

- Local PC: scraper + exporter + git push
- GitHub Pages: static UI (`docs/index.html`, `docs/app.js`, `docs/styles.css`)

## Repository structure

- `docs/` static frontend for GitHub Pages
- `docs/data/watchlist.json` generated data file
- `scripts/export_watchlist.py` converts local cache to Pages JSON
- `scripts/startup_sync.ps1` export + commit-if-changed + push
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

1. Exports `docs/data/watchlist.json`
2. Stages file
3. Commits only if changed
4. Pushes to GitHub

Logs: `scripts/logs/startup_sync.log`

## Verification checklist

- `python .\scripts\export_watchlist.py` updates `docs/data/watchlist.json`
- Opening `docs/index.html` locally renders data
- Startup sync script commits only when JSON changes
- GitHub Pages URL shows updated data after push
