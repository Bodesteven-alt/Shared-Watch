"""Shared TMDb API v3 GET: Bearer read token and/or api_key query param."""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

import api_budget
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

    def _budgeted_get(params_q, hdrs) -> requests.Response:
        # Daily budget guard (api_budget): never fire a TMDb call past the cap.
        if not api_budget.allow("tmdb"):
            raise requests.RequestException("tmdb daily budget exhausted")
        api_budget.record("tmdb")
        return requests.get(url, params=params_q, headers=hdrs, timeout=20)

    def _do_get() -> requests.Response:
        return _budgeted_get(q, headers)

    try:
        r = _do_get()
    except requests.RequestException:
        return None

    # TMDb sometimes returns 401 when both Bearer and api_key are sent but one is wrong or mismatched.
    if r.status_code == 401 and token and api_key:
        try:
            rb = _budgeted_get(
                dict(params or {}),
                {"Accept": "application/json", "Authorization": f"Bearer {token}"},
            )
            if rb.status_code == 200:
                _log.warning(
                    "TMDb HTTP 401 with Bearer+api_key for %s; Bearer-only retry succeeded",
                    path,
                )
                r = rb
            else:
                qk: dict[str, Any] = dict(params or {})
                qk["api_key"] = api_key
                rk = _budgeted_get(qk, {"Accept": "application/json"})
                if rk.status_code == 200:
                    _log.warning(
                        "TMDb HTTP 401 with Bearer+api_key for %s; api_key-only retry succeeded",
                        path,
                    )
                    r = rk
                else:
                    _log.warning(
                        "TMDb auth failed for %s: combined (401), Bearer-only (%s), api_key-only (%s). "
                        "Regenerate API key and Read Access Token at themoviedb.org/settings/api; "
                        "ensure token is the long JWT (not the short v3 key) and .env has no quotes/BOM.",
                        path,
                        rb.status_code,
                        rk.status_code,
                    )
        except requests.RequestException:
            pass

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
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None
