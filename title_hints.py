"""Shared title normalization, release-year hints, and IMDb suggestion picking."""
from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import quote

import requests

_LEADING_ARTICLES_RE = re.compile(r"^(?:the|an|a)\s+", re.IGNORECASE)

# Whole English number words -> digits so "Fantastic Four" and "Fantastic 4" share a merge key.
_EN_WORD_TO_DIGIT: dict[str, str] = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
    "thirty": "30",
    "forty": "40",
    "fifty": "50",
    "sixty": "60",
    "seventy": "70",
    "eighty": "80",
    "ninety": "90",
}
_EN_WORD_NUM_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in sorted(_EN_WORD_TO_DIGIT.keys(), key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def fold_english_number_words(text: str) -> str:
    """Replace standalone English number words with digits (merge key alignment)."""

    def _repl(m: re.Match[str]) -> str:
        return _EN_WORD_TO_DIGIT[m.group(1).lower()]

    return _EN_WORD_NUM_PATTERN.sub(_repl, text)


def normalize_metadata_key(title: str) -> str:
    """Base title part for cache keys; for year-specific keys use poster_cache_key_from_title or poster_cache_key_for_row."""
    t = (title or "").strip().lower()
    t = fold_english_number_words(t)
    t = re.sub(r"\([^)]*\)", "", t)
    t = re.sub(r"\[[^\]]*\]", "", t)
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def title_for_external_search(title: str) -> str:
    """Strip trailing (YYYY) for APIs that take year as a separate parameter (TMDb, OMDb)."""
    t = (title or "").strip()
    t = re.sub(r"\s*\(\d{4}\)\s*$", "", t).strip()
    return t


def poster_cache_key_from_title(title: str) -> str:
    """Cache/Letterboxd key: `basetitle|YYYY` when a trailing (YYYY) is present, else base only."""
    raw = (title or "").strip()
    base = normalize_metadata_key(raw)
    y = release_year_hint_from_title(raw)
    if y is not None:
        return f"{base}|{y}"
    return base


def poster_cache_key_for_row(row: dict) -> str:
    """Use display + year from any of display / Letterboxd / IMDb list titles to disambiguate remakes."""
    d = (row.get("display") or "").strip()
    base = normalize_metadata_key(d)
    y = year_hint_from_row(row)
    if y is not None:
        return f"{base}|{y}"
    return base


def article_insensitive_sort_tuple(title: str) -> tuple[str, str]:
    """Return (article-stripped key, full key) for stable alphabetic ordering."""
    full = (title or "").strip().lower()
    primary = _LEADING_ARTICLES_RE.sub("", full, count=1).strip()
    if not primary:
        primary = full
    return primary, full


def release_year_hint_from_title(title: str) -> int | None:
    """e.g. 'Some Film (2019)' -> 2019 for TMDb / IMDb disambiguation."""
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


def year_hint_from_row(row: dict) -> int | None:
    """First trailing (YYYY) found on display, Letterboxd, or IMDb list title."""
    for key in ("display", "letterboxd_title", "imdb_title"):
        raw = row.get(key)
        if not raw or not isinstance(raw, str):
            continue
        y = release_year_hint_from_title(raw.strip())
        if y is not None:
            return y
    return None


def _item_suggestion_year(item: dict) -> int | None:
    y = item.get("y")
    if y is None:
        return None
    try:
        yi = int(y)
    except (TypeError, ValueError):
        return None
    if 1870 < yi < 2100:
        return yi
    return None


def _pick_imdb_from_suggestion_items(
    items: list[Any],
    year_hint: int | None,
) -> tuple[str | None, int | None]:
    candidates: list[tuple[str, int | None]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        imdb_id = (item.get("id") or "").strip()
        if not re.fullmatch(r"tt\d+", imdb_id):
            continue
        candidates.append((imdb_id, _item_suggestion_year(item)))
    if not candidates:
        return None, None
    if year_hint is not None:
        for iid, yr in candidates:
            if yr == year_hint:
                return iid, yr
    iid, yr = candidates[0]
    return iid, yr


def imdb_suggestion_lookup(
    title: str,
    year_hint: int | None = None,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 12,
) -> dict[str, Any]:
    """
    IMDb public autocomplete: return first tt match, or the one whose suggestion year matches year_hint.
    """
    q = (title or "").strip()
    if not q:
        return {"imdb_id": None, "year": None}
    first = re.sub(r"[^a-zA-Z0-9]", "", q[:1].lower()) or "a"
    url = f"https://v2.sg.media-imdb.com/suggestion/{first}/{quote(q)}.json"
    hdrs = headers or {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=hdrs, timeout=timeout)
    except requests.RequestException:
        return {"imdb_id": None, "year": None}
    if r.status_code != 200:
        return {"imdb_id": None, "year": None}
    try:
        data = r.json()
    except ValueError:
        return {"imdb_id": None, "year": None}
    items = data.get("d") or []
    imdb_id, yr = _pick_imdb_from_suggestion_items(items, year_hint)
    return {"imdb_id": imdb_id, "year": yr}


def load_imdb_id_overrides(path: str) -> dict[str, str]:
    """
    JSON object: keys are poster_cache_key_from_title(title) (year suffix |YYYY when (YYYY) is in the
    title) or "display:Some Title (2006)".
    Values: {"imdb_id": "tt123"} or plain "tt123".
    """
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        if not isinstance(k, str):
            continue
        ks = k.strip()
        if ks.lower().startswith("display:"):
            key = poster_cache_key_from_title(ks.split(":", 1)[1].strip())
        else:
            key = poster_cache_key_from_title(ks)
        if isinstance(v, dict):
            iid = (v.get("imdb_id") or "").strip()
        elif isinstance(v, str):
            iid = v.strip()
        else:
            continue
        if re.fullmatch(r"tt\d+", iid):
            out[key] = iid
    return out
