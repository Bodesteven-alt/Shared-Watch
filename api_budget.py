"""Daily API call budget guard (added Oct 28, 2026).

Every TMDB and OMDb API call in this project must pass through here so a
runaway loop or an over-eager refresh can never burn a provider's daily
quota. Counts persist in data/api_budget.json, keyed by local date, and
reset automatically at local midnight.

Caps (env-overridable, see config.py):
  TMDB_API_DAILY_CAP  (default 600)
  OMDB_API_DAILY_CAP  (default 250; the OMDb free tier allows 1,000/day,
                      we deliberately stay at a quarter of it)

allow(provider) -> True when one more call fits today's budget.
record(provider) counts one completed HTTP attempt.
summary() returns today's counts and caps for logging.
"""
from __future__ import annotations

import json
import os
from datetime import date

import config

_PROVIDERS = ("tmdb", "omdb")


def _state_path() -> str:
    return os.path.join(os.path.dirname(config.CACHE_PATH), "api_budget.json")


def _caps() -> dict[str, int]:
    return {"tmdb": config.TMDB_API_DAILY_CAP, "omdb": config.OMDB_API_DAILY_CAP}


def _load() -> dict:
    today = date.today().isoformat()
    try:
        with open(_state_path(), encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("date") == today:
            counts = data.get("counts") or {}
            return {
                "date": today,
                "counts": {p: int(counts.get(p) or 0) for p in _PROVIDERS},
            }
    except (OSError, ValueError):
        pass
    return {"date": today, "counts": {p: 0 for p in _PROVIDERS}}


def _save(state: dict) -> None:
    path = _state_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, path)


def allow(provider: str) -> bool:
    if provider not in _PROVIDERS:
        return True
    state = _load()
    return state["counts"][provider] < _caps()[provider]


def record(provider: str, n: int = 1) -> None:
    if provider not in _PROVIDERS:
        return
    state = _load()
    state["counts"][provider] += n
    _save(state)


def summary() -> dict:
    state = _load()
    caps = _caps()
    return {
        p: {"used": state["counts"][p], "cap": caps[p]} for p in _PROVIDERS
    }
