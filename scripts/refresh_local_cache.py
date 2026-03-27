"""Fetch Letterboxd + IMDb, merge, and write data/cache.json (no Flask server)."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app as watchlist_app  # noqa: E402


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        with watchlist_app._refresh_lock:
            watchlist_app._run_refresh(log_prefix="[startup_sync] ")
        return 0
    except Exception:
        logging.exception("refresh_local_cache failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
