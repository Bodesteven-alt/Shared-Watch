"""Export local scraper cache into GitHub Pages JSON format."""
from __future__ import annotations

import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "cache.json"
DEFAULT_OUTPUT = ROOT / "docs" / "data" / "watchlist.json"


def infer_source(row: dict) -> str:
    lb = bool(row.get("letterboxd"))
    imdb = bool(row.get("imdb"))
    if lb and imdb:
        return "both"
    if lb:
        return "letterboxd"
    return "imdb"


def main() -> int:
    source_path = Path(os.environ.get("WATCHLIST_SOURCE_CACHE", str(DEFAULT_INPUT)))
    output_path = Path(os.environ.get("WATCHLIST_OUTPUT_JSON", str(DEFAULT_OUTPUT)))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not source_path.exists():
        print(f"Source cache not found: {source_path}")
        return 1

    with source_path.open(encoding="utf-8") as f:
        cache = json.load(f)

    rows = cache.get("rows") or []
    stats = cache.get("stats") or {}
    posters_resolved = sum(1 for r in rows if r.get("poster_url"))

    movies = []
    for r in rows:
        title = (r.get("display") or "").strip()
        if not title:
            continue
        movies.append(
            {
                "title": title,
                "poster_url": r.get("poster_url"),
                "source": infer_source(r),
                "imdb_id": r.get("imdb_id"),
            }
        )

    movies.sort(key=lambda m: m["title"].lower())

    payload = {
        "updated_at": cache.get("updated_at"),
        "stats": {
            "total": int(stats.get("total", len(movies))),
            "both": int(stats.get("both", 0)),
            "letterboxd_only": int(stats.get("letterboxd_only", 0)),
            "imdb_only": int(stats.get("imdb_only", 0)),
            "posters_resolved": posters_resolved,
        },
        "movies": movies,
    }

    with output_path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")

    print(f"Exported {len(movies)} movies to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
