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
    auth_mode = "bearer" if token else "api_key"
    try:
        r = requests.get(url, params=q, headers=headers, timeout=20)
    except requests.RequestException as ex:
        # region agent log
        import agent_debug

        agent_debug.log(
            hypothesis_id="H3",
            location="tmdb_client.py:tmdb_v3_get",
            message="tmdb_request_exception",
            data={"path": path, "auth_mode": auth_mode, "exc_type": type(ex).__name__},
        )
        # endregion
        return None
    if r.status_code != 200:
        # region agent log
        import agent_debug

        agent_debug.log(
            hypothesis_id="H3",
            location="tmdb_client.py:tmdb_v3_get",
            message="tmdb_non_200",
            data={"path": path, "auth_mode": auth_mode, "status": r.status_code},
        )
        # endregion
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None
