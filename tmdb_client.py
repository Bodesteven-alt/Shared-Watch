"""Shared TMDb API v3 GET: Bearer read token (preferred) or api_key query param."""
from __future__ import annotations

from typing import Any

import requests

import config

_TMDB_V3_BASE = "https://api.themoviedb.org/3"


def tmdb_v3_get(path: str, params: dict[str, Any] | None = None) -> dict | None:
    """
    GET https://api.themoviedb.org/3{path} with auth.
    If TMDB_READ_ACCESS_TOKEN is set, uses Authorization: Bearer (no api_key param).
    Else uses ?api_key= TMDB_API_KEY.
    """
    if not config.TMDB_API_CONFIGURED:
        return None
    url = f"{_TMDB_V3_BASE}{path}"
    q = dict(params or {})
    headers: dict[str, str] = {"Accept": "application/json"}
    token = (config.TMDB_READ_ACCESS_TOKEN or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        q["api_key"] = config.TMDB_API_KEY
    try:
        r = requests.get(url, params=q, headers=headers, timeout=20)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None
