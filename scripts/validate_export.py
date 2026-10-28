"""Pre-publish validation gate for docs/data/watchlist.json.

Usage: validate_export.py NEW_JSON [PREV_JSON]

Fails (exit 1) when the new export looks unsafe to publish:
  - unparseable or missing movies list
  - total moved more than +/-20% vs the previously published export
  - poster coverage below 95%
  - fewer than 95% of rows carry an IMDb id, or any id is malformed
  - updated_at missing
The sync script runs this before committing; on failure it reverts the
docs files and aborts the publish, keeping the last good export live.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

IMDB_ID_RE = re.compile(r"^tt\d{7,10}$")


def _load(path: str) -> dict | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def main() -> int:
    new = _load(sys.argv[1]) if len(sys.argv) > 1 else None
    if not new or not isinstance(new.get("movies"), list):
        print("VALIDATION FAIL: new export unparseable or has no movies list")
        return 1
    movies = new["movies"]
    problems: list[str] = []

    if not new.get("updated_at"):
        problems.append("updated_at missing")

    if len(sys.argv) > 2:
        prev = _load(sys.argv[2])
        if prev and isinstance(prev.get("movies"), list) and prev["movies"]:
            ratio = len(movies) / len(prev["movies"])
            if not (0.8 <= ratio <= 1.25):
                problems.append(
                    f"total moved {len(prev['movies'])} -> {len(movies)} (ratio {ratio:.2f})"
                )

            def _stream_share(ms: list) -> float:
                def has_prov(m: dict) -> bool:
                    s = m.get("streaming") or {}
                    return any(
                        isinstance(v, dict) and (v.get("flatrate") or v.get("rent") or v.get("buy"))
                        for v in s.values()
                    )

                return sum(1 for m in ms if has_prov(m)) / len(ms) if ms else 0.0

            drop = _stream_share(prev["movies"]) - _stream_share(movies)
            if drop > 0.05:
                problems.append(
                    f"streaming coverage dropped {drop:.0%} vs previous export "
                    "(an empty API response must never erase provider data)"
                )

    if movies:
        posters_ok = sum(1 for m in movies if m.get("poster_url")) / len(movies)
        if posters_ok < 0.95:
            problems.append(f"poster coverage {posters_ok:.1%} < 95%")
        with_id = [m for m in movies if m.get("imdb_id")]
        if len(with_id) / len(movies) < 0.95:
            problems.append(f"only {len(with_id)}/{len(movies)} rows carry an IMDb id")
        bad = [m["imdb_id"] for m in with_id if not IMDB_ID_RE.match(str(m["imdb_id"]))]
        if bad:
            problems.append(f"malformed IMDb ids: {bad[:5]}")

    if problems:
        for p in problems:
            print("VALIDATION FAIL:", p)
        return 1
    print(f"VALIDATION PASS: {len(movies)} movies, sane vs previous export")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
