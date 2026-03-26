"""Export local scraper cache into GitHub Pages JSON format."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "cache.json"
DEFAULT_OUTPUT = ROOT / "docs" / "data" / "watchlist.json"
DEFAULT_METADATA_CACHE = ROOT / "data" / "imdb_metadata_cache.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9",
}


def infer_source(row: dict) -> str:
    lb = bool(row.get("letterboxd"))
    imdb = bool(row.get("imdb"))
    if lb and imdb:
        return "both"
    if lb:
        return "letterboxd"
    return "imdb"


def normalize_title(title: str) -> str:
    t = (title or "").strip().lower()
    t = re.sub(r"\([^)]*\)", "", t)
    t = re.sub(r"\[[^\]]*\]", "", t)
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def lookup_imdb_hint_by_title(title: str) -> dict:
    q = (title or "").strip()
    if not q:
        return {"imdb_id": None, "year": None}
    first = re.sub(r"[^a-zA-Z0-9]", "", q[:1].lower()) or "a"
    url = f"https://v2.sg.media-imdb.com/suggestion/{first}/{quote(q)}.json"
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
    except requests.RequestException:
        return {"imdb_id": None, "year": None}
    if r.status_code != 200:
        return {"imdb_id": None, "year": None}
    try:
        data = r.json()
    except ValueError:
        return {"imdb_id": None, "year": None}
    for item in data.get("d", []) or []:
        imdb_id = (item.get("id") or "").strip()
        if re.fullmatch(r"tt\d+", imdb_id):
            y = item.get("y")
            try:
                year = int(y) if y is not None else None
            except (TypeError, ValueError):
                year = None
            return {"imdb_id": imdb_id, "year": year}
    return {"imdb_id": None, "year": None}


def parse_imdb_title_page(imdb_id: str) -> dict:
    """
    Return metadata from IMDb title page:
      year, genres[], rating_imdb_10
    """
    url = f"https://www.imdb.com/title/{imdb_id}/"
    out = {
        "year": None,
        "genres": [],
        "rating_imdb_10": None,
    }
    try:
        r = requests.get(url, headers=HEADERS, timeout=16)
    except requests.RequestException:
        return out
    if r.status_code != 200:
        return out

    soup = BeautifulSoup(r.text, "html.parser")
    # Prefer JSON-LD for stable metadata extraction.
    for script in soup.find_all("script", type="application/ld+json"):
        txt = (script.string or "").strip()
        if not txt:
            continue
        try:
            obj = json.loads(txt)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        genre = obj.get("genre")
        if isinstance(genre, str):
            out["genres"] = [genre]
        elif isinstance(genre, list):
            out["genres"] = [str(x) for x in genre if x]
        date = str(obj.get("datePublished") or "")
        m = re.match(r"(\d{4})", date)
        if m:
            out["year"] = int(m.group(1))
        rating_obj = obj.get("aggregateRating") or {}
        if isinstance(rating_obj, dict):
            rv = rating_obj.get("ratingValue")
            try:
                if rv is not None:
                    out["rating_imdb_10"] = float(rv)
            except (TypeError, ValueError):
                pass
        if out["year"] or out["genres"] or out["rating_imdb_10"] is not None:
            return out

    # Fallback for rating if JSON-LD wasn't present/parseable.
    t = soup.get_text(" ", strip=True)
    m_rating = re.search(r"\b(\d\.\d)\s*/\s*10\b", t)
    if m_rating:
        try:
            out["rating_imdb_10"] = float(m_rating.group(1))
        except ValueError:
            pass
    return out


def fetch_tmdb_metadata_by_title(title: str) -> dict:
    """
    No-key fallback metadata from TMDB website pages.
    """
    out = {"year": None, "genres": [], "rating_imdb_10": None}
    q = (title or "").strip()
    if not q:
        return out
    try:
        s = requests.get(
            "https://www.themoviedb.org/search/movie",
            params={"query": q},
            headers=HEADERS,
            timeout=16,
        )
    except requests.RequestException:
        return out
    if s.status_code != 200:
        return out
    soup = BeautifulSoup(s.text, "html.parser")
    a = soup.select_one("a.result, .results .title a, .card .image a, .card.v4.tight .image a")
    if not a or not a.get("href"):
        return out
    href = str(a.get("href"))
    if not href.startswith("/movie/"):
        return out
    try:
        r = requests.get("https://www.themoviedb.org" + href, headers=HEADERS, timeout=16)
    except requests.RequestException:
        return out
    if r.status_code != 200:
        return out
    dsoup = BeautifulSoup(r.text, "html.parser")
    for script in dsoup.find_all("script", type="application/ld+json"):
        txt = (script.string or "").strip()
        if not txt:
            continue
        txt = txt.replace("/* <![CDATA[ */", "").replace("/* ]]> */", "").strip()
        try:
            obj = json.loads(txt)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        if str(obj.get("@type", "")).lower() != "movie":
            continue
        genre = obj.get("genre")
        if isinstance(genre, str):
            out["genres"] = [genre]
        elif isinstance(genre, list):
            out["genres"] = [str(x) for x in genre if x]
        date = str(obj.get("datePublished") or obj.get("dateCreated") or "")
        m = re.match(r"(\d{4})", date)
        if m:
            out["year"] = int(m.group(1))
        rating_obj = obj.get("aggregateRating") or {}
        if isinstance(rating_obj, dict):
            rv = rating_obj.get("ratingValue")
            try:
                if rv is not None:
                    out["rating_imdb_10"] = float(rv)
            except (TypeError, ValueError):
                pass
        return out
    return out


def round2(x: float | None) -> float | None:
    if x is None:
        return None
    return round(float(x) + 1e-8, 2)


def main() -> int:
    source_path = Path(os.environ.get("WATCHLIST_SOURCE_CACHE", str(DEFAULT_INPUT)))
    output_path = Path(os.environ.get("WATCHLIST_OUTPUT_JSON", str(DEFAULT_OUTPUT)))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not source_path.exists():
        print(f"Source cache not found: {source_path}")
        return 1

    cache = load_json(source_path, {})
    meta_cache_path = Path(os.environ.get("WATCHLIST_METADATA_CACHE", str(DEFAULT_METADATA_CACHE)))
    meta_cache = load_json(meta_cache_path, {})

    rows = cache.get("rows") or []
    stats = cache.get("stats") or {}
    posters_resolved = sum(1 for r in rows if r.get("poster_url"))

    movies = []
    for r in rows:
        title = (r.get("display") or "").strip()
        if not title:
            continue
        norm = normalize_title(title)
        c = meta_cache.get(norm) if isinstance(meta_cache.get(norm), dict) else {}

        imdb_id = r.get("imdb_id")
        hint = {"imdb_id": None, "year": None}
        if not imdb_id:
            imdb_id = c.get("imdb_id")
        if not imdb_id:
            hint = lookup_imdb_hint_by_title(title)
            imdb_id = hint.get("imdb_id")

        needs_refresh = (
            not c
            or c.get("imdb_id") != imdb_id
            or "year" not in c
            or (
                c.get("year") is None
                and not c.get("genres")
                and c.get("rating_imdb_10") is None
            )
        )
        if imdb_id and needs_refresh:
            parsed = parse_imdb_title_page(imdb_id)
            # If IMDb blocks title page scraping, fallback to TMDB web metadata (no API key).
            if not parsed.get("year") and not parsed.get("genres") and parsed.get("rating_imdb_10") is None:
                parsed = fetch_tmdb_metadata_by_title(title)
            c = {
                "imdb_id": imdb_id,
                "year": parsed.get("year") or hint.get("year"),
                "genres": parsed.get("genres") or [],
                "rating_imdb_10": parsed.get("rating_imdb_10"),
            }
            meta_cache[norm] = c
        elif not c:
            c = {"imdb_id": imdb_id, "year": None, "genres": [], "rating_imdb_10": None}
            meta_cache[norm] = c

        rating_imdb_10 = c.get("rating_imdb_10")
        rating_letterboxd_5 = r.get("rating_letterboxd_5")
        imdb_5 = None
        if rating_imdb_10 is not None:
            try:
                imdb_5 = float(rating_imdb_10) / 2.0
            except (TypeError, ValueError):
                imdb_5 = None

        vals = []
        if imdb_5 is not None:
            vals.append(imdb_5)
        if rating_letterboxd_5 is not None:
            try:
                vals.append(float(rating_letterboxd_5))
            except (TypeError, ValueError):
                pass
        rating_avg_5 = round2(sum(vals) / len(vals)) if vals else None

        movies.append(
            {
                "title": title,
                "poster_url": r.get("poster_url"),
                "source": infer_source(r),
                "imdb_id": imdb_id,
                "year": c.get("year"),
                "genres": c.get("genres") or [],
                "rating_imdb_10": round2(rating_imdb_10 if rating_imdb_10 is not None else None),
                "rating_letterboxd_5": round2(rating_letterboxd_5 if rating_letterboxd_5 is not None else None),
                "rating_avg_5": rating_avg_5,
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
            "metadata_with_year": sum(1 for m in movies if m.get("year") is not None),
            "metadata_with_genres": sum(1 for m in movies if m.get("genres")),
            "metadata_with_rating": sum(1 for m in movies if m.get("rating_imdb_10") is not None),
        },
        "movies": movies,
    }

    save_json(output_path, payload)
    save_json(meta_cache_path, meta_cache)

    print(f"Exported {len(movies)} movies to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
