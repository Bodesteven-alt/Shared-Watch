"""Shared TMDb API v3 GET: Bearer read token and/or api_key query param."""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

import config

_TMDB_V3_BASE = "https://api.themoviedb.org/3"
_log = logging.getLogger("tmdb_client")


def tmdb_v3_get(
    path: str,
    params: dict[str, Any] | None = None,
    *,
    retry_on_429: bool = False,
) -> dict | None:
    """
    GET https://api.themoviedb.org/3{path} with auth.
    If TMDB_READ_ACCESS_TOKEN is set: Authorization: Bearer.
    If TMDB_API_KEY is set: api_key query param (can be combined with Bearer).
    """
    if not config.TMDB_API_CONFIGURED:
        return None
    url = f"{_TMDB_V3_BASE}{path}"
    q: dict[str, Any] = dict(params or {})
    headers: dict[str, str] = {"Accept": "application/json"}
    token = (config.TMDB_READ_ACCESS_TOKEN or "").strip()
    api_key = (config.TMDB_API_KEY or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if api_key:
        q["api_key"] = api_key
    if token and api_key:
        auth_mode = "bearer+api_key"
    elif token:
        auth_mode = "bearer"
    else:
        auth_mode = "api_key"

    def _do_get() -> requests.Response:
        return requests.get(url, params=q, headers=headers, timeout=20)

    try:
        r = _do_get()
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

    if r.status_code == 429 and retry_on_429:
        _log.warning("TMDb 429 for %s; retrying once after delay", path)
        time.sleep(2.0)
        try:
            r = _do_get()
        except requests.RequestException as ex:
            _log.warning("TMDb retry failed for %s: %s", path, type(ex).__name__)
            return None

    if r.status_code != 200:
        _log.warning(
            "TMDb HTTP %s for %s (auth_mode=%s)",
            r.status_code,
            path,
            auth_mode,
        )
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
