"""TMDb watch-provider enrichment for watchlist rows (movies only)."""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Callable

import agent_debug
import config
import posters as posters_mod
import tmdb_client


def _norm_title_key(title: str) -> str:
    return posters_mod._normalize(title or "")


def _cache_key_for_row(row: dict) -> str | None:
    imdb_id = (row.get("imdb_id") or "").strip()
    if imdb_id and re.fullmatch(r"tt\d+", imdb_id):
        return f"imdb:{imdb_id}"
    disp = (row.get("display") or "").strip()
    if disp:
        return f"title:{_norm_title_key(disp)}"
    return None


def _load_providers_cache() -> dict[str, Any]:
    path = config.TMDB_WATCH_PROVIDERS_CACHE_PATH
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_providers_cache(cache: dict[str, Any]) -> None:
    path = config.TMDB_WATCH_PROVIDERS_CACHE_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _normalize_provider_entries(raw: list | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not raw:
        return out
    seen: set[int] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        pid = item.get("provider_id")
        try:
            pid_int = int(pid)
        except (TypeError, ValueError):
            continue
        if pid_int in seen:
            continue
        seen.add(pid_int)
        name = (item.get("provider_name") or "").strip() or str(pid_int)
        out.append({"provider_id": pid_int, "provider_name": name})
    return out


def _trim_results_by_region(full_results: dict, region: str) -> dict[str, Any]:
    region = (region or "US").upper()
    block = full_results.get(region)
    if not isinstance(block, dict):
        return {}
    return {
        region: {
            "flatrate": _normalize_provider_entries(block.get("flatrate")),
            "rent": _normalize_provider_entries(block.get("rent")),
            "buy": _normalize_provider_entries(block.get("buy")),
        }
    }


def _tmdb_request(path: str, params: dict, *, retry_on_429: bool = False) -> dict | None:
    return tmdb_client.tmdb_v3_get(path, params, retry_on_429=retry_on_429)


def _find_movie_id_by_imdb(imdb_id: str) -> int | None:
    # TMDb expects tt-prefixed id in path
    iid = imdb_id if imdb_id.startswith("tt") else f"tt{imdb_id}"
    data = _tmdb_request(f"/find/{iid}", {"external_source": "imdb_id"})
    if not data:
        return None
    movies = data.get("movie_results") or []
    if movies and isinstance(movies[0], dict):
        mid = movies[0].get("id")
        try:
            return int(mid)
        except (TypeError, ValueError):
            return None
    return None


def _release_year_hint_from_title(title: str) -> int | None:
    """e.g. 'Some Film (2019)' -> 2019 for TMDb search disambiguation."""
    m = re.search(r"\((\d{4})\)\s*$", (title or "").strip())
    if not m:
        return None
    try:
        y = int(m.group(1))
    except ValueError:
        return None
    if 1870 < y < 2100:
        return y
    return None


def _find_movie_id_by_title(title: str, year_hint: int | None = None) -> int | None:
    q = (title or "").strip()
    if not q:
        return None
    params: dict[str, Any] = {"query": q, "include_adult": "false"}
    if year_hint is not None:
        params["primary_release_year"] = year_hint
    data = _tmdb_request("/search/movie", params)
    if not data:
        return None
    results = data.get("results") or []
    if not results:
        return None

    def _pick_id(candidates: list) -> int | None:
        for item in candidates:
            if not isinstance(item, dict):
                continue
            mid = item.get("id")
            try:
                return int(mid)
            except (TypeError, ValueError):
                continue
        return None

    if year_hint is not None:
        ys = str(year_hint)
        matching = [
            r
            for r in results
            if isinstance(r, dict)
            and str((r.get("release_date") or ""))[:4] == ys
        ]
        picked = _pick_id(matching)
        if picked is not None:
            return picked

    return _pick_id(results)


def _fetch_watch_providers_raw(tmdb_movie_id: int) -> dict[str, Any]:
    data = _tmdb_request(
        f"/movie/{tmdb_movie_id}/watch/providers",
        {},
        retry_on_429=True,
    )
    if not data:
        return {}
    results = data.get("results")
    return results if isinstance(results, dict) else {}


def _cache_entry_fresh(entry: dict, now: float) -> bool:
    if config.STREAMING_CACHE_MAX_AGE_DAYS <= 0:
        return True
    ts = entry.get("fetched_at")
    try:
        ts_f = float(ts)
    except (TypeError, ValueError):
        return False
    max_age = config.STREAMING_CACHE_MAX_AGE_DAYS * 86400
    return (now - ts_f) < max_age


def enrich_rows_with_streaming(
    rows: list[dict],
    log: Callable[[str], None] | None = None,
) -> tuple[list[dict], dict[str, int]]:
    """
    Attach row['streaming'] = { 'US': { 'flatrate': [...], 'rent': [...], 'buy': [...] }, ... }
    Only the configured profile region is required for the UI; we store that region's slice.
    """
    profile = config.load_owned_streaming_profile()
    region = profile.get("region") or "US"

    def _log(msg: str) -> None:
        if log:
            log(msg)

    # #region agent log
    agent_debug.log(
        hypothesis_id="A",
        location="streaming.py:enrich_rows_with_streaming",
        message="enrich entry",
        data={
            "runId": "pre-fix",
            "tmdb_configured": config.TMDB_API_CONFIGURED,
            "has_token": bool((config.TMDB_READ_ACCESS_TOKEN or "").strip()),
            "has_key": bool((config.TMDB_API_KEY or "").strip()),
            "region": region,
            "row_count": len(rows),
            "max_network_lookups": max(0, config.STREAMING_MAX_NETWORK_LOOKUPS),
        },
    )
    # #endregion

    if not config.TMDB_API_CONFIGURED:
        _log("[Streaming] No TMDb credentials (TMDB_READ_ACCESS_TOKEN or TMDB_API_KEY); skipping watch-provider enrichment")
        # #region agent log
        agent_debug.log(
            hypothesis_id="A",
            location="streaming.py:enrich_no_creds",
            message="skipped enrichment — no TMDb creds",
            data={"runId": "pre-fix", "skipped_rows": len(rows)},
        )
        # #endregion
        for row in rows:
            row["streaming"] = {}
        return rows, {"enriched": 0, "cached": 0, "skipped": len(rows), "api_calls": 0}

    if (config.TMDB_API_KEY or "").strip() and not (config.TMDB_READ_ACCESS_TOKEN or "").strip():
        _log(
            "[Streaming] Hint: set TMDB_READ_ACCESS_TOKEN as well as TMDB_API_KEY for best watch-provider results on v3."
        )

    disk = _load_providers_cache()
    now = time.time()
    api_calls = 0
    max_calls = max(0, config.STREAMING_MAX_NETWORK_LOOKUPS)
    enriched = 0
    cached = 0
    skipped = 0
    _first_watch_raw_logged = False

    for row in rows:
        key = _cache_key_for_row(row)
        if not key:
            skipped += 1
            continue

        entry = disk.get(key)
        if isinstance(entry, dict) and entry.get("streaming") is not None and _cache_entry_fresh(entry, now):
            row["streaming"] = entry["streaming"]
            cached += 1
            enriched += 1
            continue

        if api_calls >= max_calls:
            if isinstance(entry, dict) and entry.get("streaming"):
                row["streaming"] = entry["streaming"]
                enriched += 1
            else:
                skipped += 1
            continue

        tmdb_id: int | None = None
        if isinstance(entry, dict) and entry.get("tmdb_id") is not None:
            try:
                tmdb_id = int(entry["tmdb_id"])
            except (TypeError, ValueError):
                tmdb_id = None

        if tmdb_id is None:
            imdb_id = (row.get("imdb_id") or "").strip()
            if imdb_id and re.fullmatch(r"tt\d+", imdb_id):
                if api_calls >= max_calls:
                    skipped += 1
                    continue
                tmdb_id = _find_movie_id_by_imdb(imdb_id)
                api_calls += 1
            if tmdb_id is None:
                title = (row.get("display") or "").strip()
                if title:
                    if api_calls >= max_calls:
                        skipped += 1
                        continue
                    yh = row.get("release_year")
                    if yh is None:
                        yh = _release_year_hint_from_title(title)
                    else:
                        try:
                            yh = int(yh)
                            if not (1870 < yh < 2100):
                                yh = _release_year_hint_from_title(title)
                        except (TypeError, ValueError):
                            yh = _release_year_hint_from_title(title)
                    tmdb_id = _find_movie_id_by_title(title, year_hint=yh)
                    api_calls += 1

        if tmdb_id is None:
            skipped += 1
            row["streaming"] = {}
            disk[key] = {"tmdb_id": None, "streaming": {}, "fetched_at": now}
            continue

        if api_calls >= max_calls:
            if isinstance(entry, dict) and entry.get("streaming"):
                row["streaming"] = entry["streaming"]
                enriched += 1
            else:
                skipped += 1
            continue

        raw_regions = _fetch_watch_providers_raw(tmdb_id)
        api_calls += 1
        # #region agent log
        if not _first_watch_raw_logged:
            _first_watch_raw_logged = True
            keys = sorted(raw_regions.keys()) if isinstance(raw_regions, dict) else []
            us_blk = raw_regions.get(region) if isinstance(raw_regions, dict) else None
            us_blk = us_blk if isinstance(us_blk, dict) else {}
            agent_debug.log(
                hypothesis_id="B",
                location="streaming.py:first_watch_providers_response",
                message="first TMDb watch/providers raw sample",
                data={
                    "runId": "pre-fix",
                    "tmdb_id": tmdb_id,
                    "profile_region": region,
                    "raw_region_key_count": len(keys),
                    "raw_region_keys_head": keys[:20],
                    "us_flatrate_n": len(us_blk.get("flatrate") or []) if isinstance(us_blk.get("flatrate"), list) else 0,
                    "us_rent_n": len(us_blk.get("rent") or []) if isinstance(us_blk.get("rent"), list) else 0,
                    "raw_empty": not keys,
                },
            )
        # #endregion
        slim = _trim_results_by_region(raw_regions, region)
        row["streaming"] = slim
        disk[key] = {"tmdb_id": tmdb_id, "streaming": slim, "fetched_at": now}
        enriched += 1

    _save_providers_cache(disk)
    # #region agent log
    agent_debug.log(
        hypothesis_id="E",
        location="streaming.py:enrich_complete",
        message="enrich finished",
        data={
            "runId": "pre-fix",
            "enriched": enriched,
            "cached": cached,
            "skipped": skipped,
            "api_calls": api_calls,
        },
    )
    # #endregion
    _log(
        f"[Streaming] rows with data={enriched} (disk_hits~{cached}), skipped={skipped}, TMDb calls={api_calls}"
    )
    _log(
        "[Streaming] If provider lists stay empty after fixing TMDb credentials, delete "
        "data/tmdb_watch_providers_cache.json once and refresh."
    )
    return rows, {
        "enriched": enriched,
        "cached": cached,
        "skipped": skipped,
        "api_calls": api_calls,
    }


def count_streamable_flatrate(
    rows: list[dict],
    *,
    region: str,
    selected_provider_ids: list[int],
) -> int:
    """How many rows have at least one selected subscription provider in flatrate for region."""
    if not selected_provider_ids:
        return 0
    want = set(selected_provider_ids)
    reg = (region or "US").upper()
    n = 0
    for row in rows:
        st = row.get("streaming") or {}
        block = st.get(reg) or {}
        flat = block.get("flatrate") or []
        have = {x.get("provider_id") for x in flat if isinstance(x, dict)}
        if have & want:
            n += 1
    return n


def row_matches_streamable_flatrate(
    row: dict,
    *,
    region: str,
    selected_provider_ids: list[int],
) -> bool:
    if not selected_provider_ids:
        return False
    want = set(selected_provider_ids)
    reg = (region or "US").upper()
    st = row.get("streaming") or {}
    block = st.get(reg) or {}
    flat = block.get("flatrate") or []
    have = {x.get("provider_id") for x in flat if isinstance(x, dict)}
    return bool(have & want)
