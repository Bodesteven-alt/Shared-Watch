"""One-time migration of data/posters.json to the v2 id-keyed format.

Why: the v1 cache was keyed by bare title, so two films sharing a title
collided (Godzilla 1954 carried the 2014 poster). This script rebuilds the
cache keyed by IMDb id, verifying every poster against TMDb /find for that
exact IMDb id, and repairs conflicting title-keyed entries in
data/imdb_ids.json.

API discipline: at most one TMDb /find per distinct IMDb id in the current
export, throttled, and every call passes through the api_budget guard in
tmdb_client. OMDb is never called. Run without --apply for a dry run that
reports every mismatch it would fix (the /find calls still happen; they
are how mismatches are known).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import posters  # noqa: E402
import title_hints  # noqa: E402


def _poster_path(url: str | None) -> str:
    """Poster identity ignoring the CDN size segment."""
    if not url:
        return ""
    return re.sub(r"/t/p/[^/]+/", "/t/p/X/", str(url))


def _atomic_write_json(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def main() -> int:
    apply = "--apply" in sys.argv
    watchlist = json.loads((ROOT / "docs" / "data" / "watchlist.json").read_text(encoding="utf-8"))
    rows = watchlist.get("movies") or []
    today = date.today().isoformat()

    old_posters = posters._load_cache()  # normalized v2 entries
    id_cache = posters._load_id_cache()

    new_posters: dict[str, dict] = {}
    mismatches: list[str] = []
    id_fixes: list[str] = []
    find_calls = 0
    unverified = 0

    # Reuse a same-day audit file when present so a dry run followed by
    # --apply does not spend the /find calls twice.
    audit_path = ROOT / "data" / "poster_audit_results.json"
    audit_cache: dict[str, str | None] = {}
    if audit_path.is_file():
        try:
            saved = json.loads(audit_path.read_text(encoding="utf-8"))
            if saved.get("date") == today:
                audit_cache = saved.get("results") or {}
        except ValueError:
            audit_cache = {}

    seen_ids: set[str] = set()
    for row in rows:
        title = row.get("title") or ""
        year = row.get("year")
        imdb_id = (row.get("imdb_id") or "").strip()
        current = row.get("poster_url")
        if imdb_id:
            if imdb_id in seen_ids:
                continue
            seen_ids.add(imdb_id)
            canonical = None
            if imdb_id in audit_cache:
                canonical = audit_cache[imdb_id]
            elif config.TMDB_API_CONFIGURED:
                canonical = posters._fetch_tmdb_poster_by_imdb_find(imdb_id)
                audit_cache[imdb_id] = canonical
                find_calls += 1
                time.sleep(0.25)
            if canonical:
                if _poster_path(canonical) != _poster_path(current):
                    mismatches.append(
                        f"{title} ({year}) {imdb_id}: {current} -> {canonical}"
                    )
                new_posters[f"imdb:{imdb_id}"] = {
                    "url": canonical,
                    "source": "migration",
                    "checked_at": today,
                }
            else:
                unverified += 1
                new_posters[f"imdb:{imdb_id}"] = {
                    "url": current,
                    "source": "legacy",
                    "checked_at": None,
                }
            # Repair conflicting title-keyed id entries for this film.
            base = title_hints.normalize_metadata_key(title)
            for key in {base, f"{base}|{year}" if year else base}:
                if key in id_cache and id_cache[key] != imdb_id:
                    id_fixes.append(f"imdb_ids[{key!r}]: {id_cache[key]} -> {imdb_id}")
                    id_cache[key] = imdb_id
        else:
            key = title_hints.poster_cache_key_from_title(
                f"{title} ({year})" if year else title
            )
            old = old_posters.get(key)
            if old and old.get("url"):
                new_posters[key] = old

    print(f"Rows: {len(rows)}; distinct IMDb ids: {len(seen_ids)}")
    print(f"TMDb /find calls made: {find_calls}; unverified (kept legacy): {unverified}")
    print(f"Poster mismatches: {len(mismatches)}")
    for m in mismatches:
        print("  MISMATCH", m)
    print(f"imdb_ids.json repairs: {len(id_fixes)}")
    for f in id_fixes:
        print("  IDFIX", f)

    audit_path.write_text(
        json.dumps({"date": today, "results": audit_cache}, indent=2), encoding="utf-8"
    )
    if apply:
        _atomic_write_json(config.POSTER_CACHE_PATH, new_posters)
        _atomic_write_json(config.IMDB_ID_CACHE_PATH, id_cache)
        print(f"APPLIED: wrote {len(new_posters)} poster entries (v2, id-keyed).")
    else:
        print("DRY RUN: nothing written. Re-run with --apply to write the v2 cache.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
