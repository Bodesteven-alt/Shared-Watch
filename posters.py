"""Poster lookups with local JSON cache (no-key first)."""
from __future__ import annotations

import json
import os
import re
import time
from typing import Callable
import requests
from bs4 import BeautifulSoup

import config
import title_hints
import tmdb_client

TMDB_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

TMDB_SEARCH_MOVIE_NAV = frozenset(
    {
        "now-playing",
        "upcoming",
        "top-rated",
        "popular",
        "favorites",
        "watchlist",
    }
)


def _normalize(title: str) -> str:
    t = title.strip().lower()
    t = re.sub(r"\([^)]*\)", "", t)
    t = re.sub(r"\[[^\]]*\]", "", t)
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _load_cache() -> dict[str, str | None]:
    path = config.POSTER_CACHE_PATH
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _save_cache(cache: dict[str, str | None]) -> None:
    os.makedirs(os.path.dirname(config.POSTER_CACHE_PATH), exist_ok=True)
    tmp = config.POSTER_CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp, config.POSTER_CACHE_PATH)


def _load_id_cache() -> dict[str, str | None]:
    path = config.IMDB_ID_CACHE_PATH
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _save_id_cache(cache: dict[str, str | None]) -> None:
    os.makedirs(os.path.dirname(config.IMDB_ID_CACHE_PATH), exist_ok=True)
    tmp = config.IMDB_ID_CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp, config.IMDB_ID_CACHE_PATH)


def _tmdb_search_first_movie_href(soup: BeautifulSoup) -> str | None:
    """
    TMDB /search/movie mixes people and movies; pick /movie/<digits>-slug, not nav links.
    """
    best: str | None = None
    for a in soup.select('a[href^="/movie/"]'):
        href = str(a.get("href") or "").split("?")[0]
        if not href.startswith("/movie/"):
            continue
        slug = href.removeprefix("/movie/").strip("/").split("/")[0].lower()
        if not slug or slug in TMDB_SEARCH_MOVIE_NAV:
            continue
        if re.match(r"^\d+-", slug):
            return href
        if best is None:
            best = href
    return best


def _normalize_tmdb_cdn_poster_url(src: str) -> str | None:
    s = (src or "").strip()
    if not s or s.lower().endswith(".svg"):
        return None
    if s.startswith("//"):
        s = "https:" + s
    if s.startswith("/"):
        s = "https://www.themoviedb.org" + s
    m = re.search(r"/t/p/[^/]+(/.+)$", s)
    if m:
        return "https://image.tmdb.org/t/p/w154" + m.group(1)
    if "image.tmdb.org" in s:
        return s
    return s


def _tmdb_jsonld_date_year(obj: dict) -> int | None:
    dpub = obj.get("datePublished")
    if isinstance(dpub, str) and len(dpub) >= 4 and dpub[:4].isdigit():
        try:
            y = int(dpub[:4])
        except ValueError:
            return None
        if 1870 < y < 2100:
            return y
    return None


def _poster_from_tmdb_jsonld_movie(obj: dict) -> str | None:
    img = obj.get("image")
    if isinstance(img, str):
        return _normalize_tmdb_cdn_poster_url(img)
    if isinstance(img, list) and img:
        first = img[0]
        if isinstance(first, str):
            return _normalize_tmdb_cdn_poster_url(first)
        if isinstance(first, dict):
            u = (first.get("url") or first.get("@id") or "").strip()
            if u:
                return _normalize_tmdb_cdn_poster_url(u)
    return None


def _tmdb_movie_page_poster_and_year(html: str) -> tuple[str | None, int | None]:
    """Poster URL and release year (from JSON-LD) for TMDB movie detail HTML."""
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
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
        tpe = obj.get("@type")
        if isinstance(tpe, list):
            is_movie = any(str(x).lower() == "movie" for x in tpe)
        else:
            is_movie = str(tpe or "").lower() == "movie"
        if not is_movie:
            continue
        y = _tmdb_jsonld_date_year(obj)
        p = _poster_from_tmdb_jsonld_movie(obj)
        if p:
            return p, y
        break
    img = soup.select_one("img.poster, .poster img, .image_content img")
    if img:
        src = (img.get("data-src") or img.get("src") or "").strip()
        p = _normalize_tmdb_cdn_poster_url(src)
        if p:
            return p, None
    return None, None


def _poster_from_tmdb_movie_page_html(html: str) -> str | None:
    """Read poster from TMDB movie detail page (JSON-LD image or fallback img)."""
    p, _y = _tmdb_movie_page_poster_and_year(html)
    return p


def _fetch_tmdb_poster_by_imdb_find(imdb_id: str) -> str | None:
    """TMDB /find by IMDb id (accurate poster when TMDb API is configured)."""
    if not config.TMDB_API_CONFIGURED or not imdb_id:
        return None
    data = tmdb_client.tmdb_v3_get(f"/find/{imdb_id}", {"external_source": "imdb_id"})
    if not data:
        return None
    for movie in data.get("movie_results") or []:
        pp = movie.get("poster_path")
        if pp:
            return f"{config.TMDB_IMAGE_BASE}{pp}"
    return None


def _fetch_omdb_poster(
    imdb_id: str | None, title: str | None, year: int | None = None
) -> str | None:
    if not config.OMDB_API_KEY:
        return None
    params: dict[str, str] = {"apikey": config.OMDB_API_KEY}
    tid = (imdb_id or "").strip()
    if tid:
        params["i"] = tid
    elif title and title.strip():
        params["t"] = title.strip()
        if year is not None:
            params["y"] = str(year)
    else:
        return None
    try:
        r = requests.get("http://www.omdbapi.com/", params=params, timeout=12)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    if data.get("Response") != "True":
        return None
    poster = (data.get("Poster") or "").strip()
    if not poster or poster.upper() == "N/A":
        return None
    return poster


def _fetch_tmdb_poster(title: str, year_hint: int | None = None) -> str | None:
    if not config.TMDB_API_CONFIGURED:
        return None
    q = title_hints.title_for_external_search((title or "").strip())
    if not q:
        return None
    params: dict[str, str | int] = {"query": q, "include_adult": "false"}
    if year_hint is not None:
        params["primary_release_year"] = year_hint
    data = tmdb_client.tmdb_v3_get("/search/movie", params)
    if not data:
        return None
    results = data.get("results") or []
    if not results:
        return None

    def _pick_poster(candidates: list) -> str | None:
        for item in candidates:
            if not isinstance(item, dict):
                continue
            pp = item.get("poster_path")
            if pp:
                return f"{config.TMDB_IMAGE_BASE}{pp}"
        return None

    if year_hint is not None:
        ys = str(year_hint)
        matching = [
            r
            for r in results
            if isinstance(r, dict) and str((r.get("release_date") or ""))[:4] == ys
        ]
        return _pick_poster(matching)
    return _pick_poster(results)


def _fetch_tmdb_web_poster_for_query(
    q: str, expect_release_year: int | None = None
) -> str | None:
    """TMDB search → first real movie link → detail page; optional JSON-LD year match."""
    q = (q or "").strip()
    if not q:
        return None
    try:
        r = requests.get(
            "https://www.themoviedb.org/search/movie",
            params={"query": q},
            timeout=16,
            headers=TMDB_HTTP_HEADERS,
        )
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    href = _tmdb_search_first_movie_href(soup)
    if not href:
        return None
    try:
        page = requests.get(
            "https://www.themoviedb.org" + href,
            timeout=16,
            headers=TMDB_HTTP_HEADERS,
        )
    except requests.RequestException:
        return None
    if page.status_code != 200:
        return None
    poster, page_y = _tmdb_movie_page_poster_and_year(page.text)
    if expect_release_year is not None:
        if page_y is None or page_y != expect_release_year:
            return None
    return poster


def _fetch_tmdb_web_poster(title: str, year_hint: int | None = None) -> str | None:
    """
    No-key: TMDB search → detail page poster. When year_hint is set, only accept
    a detail page whose JSON-LD year matches; never fall back to a title-only search
    (avoids remakes with the same title).
    """
    t = (title or "").strip()
    if not t:
        return None
    st = title_hints.title_for_external_search(t)
    if year_hint is not None:
        yfirst = _fetch_tmdb_web_poster_for_query(
            f"{st} {year_hint}", expect_release_year=year_hint
        )
        if yfirst:
            return yfirst
        yquote = _fetch_tmdb_web_poster_for_query(
            f'"{st}" {year_hint}', expect_release_year=year_hint
        )
        if yquote:
            return yquote
        return None
    return _fetch_tmdb_web_poster_for_query(st, expect_release_year=None)


def _normalize_lb_image_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    if u.startswith("//"):
        return "https:" + u
    return u


def _is_letterboxd_placeholder(url: str) -> bool:
    u = (url or "").lower()
    return "empty-poster" in u or "/img/empty-poster" in u


def _get_letterboxd_poster_map(log: Callable[[str], None] | None = None) -> dict[str, str]:
    """No-key fallback: scrape title->poster mapping from public Letterboxd watchlist pages."""
    base_url = config.LETTERBOXD_WATCHLIST_URL
    out: dict[str, str] = {}
    page = 1
    excluded = _normalize(config.LETTERBOXD_USERNAME_EXCLUDE or "")

    while True:
        url = base_url if page == 1 else base_url.rstrip("/") + f"/page/{page}/"
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        except requests.RequestException:
            break
        if r.status_code != 200:
            break

        soup = BeautifulSoup(r.text, "html.parser")
        found_this_page = 0

        for img in soup.find_all("img", alt=True):
            title = (img.get("alt") or "").strip()
            if not title:
                continue
            n = _normalize(title)
            if not n or n == "letterboxd" or (excluded and n == excluded):
                continue
            # Prefer lazy-loaded real image, not placeholder src.
            src = _normalize_lb_image_url(img.get("data-src") or img.get("src") or "")
            if not src:
                continue
            if _is_letterboxd_placeholder(src):
                continue
            k = title_hints.poster_cache_key_from_title(title)
            if k not in out:
                out[k] = src
                found_this_page += 1

        if found_this_page == 0:
            break
        page += 1

    if log:
        log(f"[Posters] Letterboxd fallback mapped {len(out)} titles")
    return out


def _fetch_imdb_poster_by_id(imdb_id: str) -> str | None:
    if not imdb_id:
        return None
    url = f"https://www.imdb.com/title/{imdb_id}/"
    try:
        r = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return og.get("content").strip()
    tw = soup.find("meta", attrs={"name": "twitter:image"})
    if tw and tw.get("content"):
        return tw.get("content").strip()
    return None


def _lookup_imdb_id_by_title(title: str, year_hint: int | None = None) -> str | None:
    got = title_hints.imdb_suggestion_lookup(
        title,
        year_hint,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    iid = got.get("imdb_id")
    return iid if isinstance(iid, str) else None


def enrich_rows_with_posters(
    rows: list[dict], log: Callable[[str], None] | None = None
) -> tuple[list[dict], dict]:
    """
    Add `poster_url` to each row.
    Sources in order:
      1) Letterboxd watchlist scrape (no key)
      2) Disk cache (posters.json)
      3) TMDB find by imdb_id (API key), then IMDb og:image (IMDb og can show franchise promos)
      4) OMDb Poster (API key; imdb_id or title)
      5) TMDB movie page scrape by title (no key; year-qualified query when year hint exists)
      6) TMDB search/movie API (API key)
    """
    if not rows:
        return rows, {}

    cache = _load_cache()
    id_cache = _load_id_cache()
    id_overrides = title_hints.load_imdb_id_overrides(config.IMDB_ID_OVERRIDES_PATH)
    lb_posters = _get_letterboxd_poster_map(log=log)
    stats = {
        "resolved_total": 0,
        "resolved_letterboxd": 0,
        "resolved_cache": 0,
        "resolved_imdb": 0,
        "resolved_tmdb": 0,
        "resolved_omdb": 0,
        "unresolved": 0,
        "new_network_lookups": 0,
    }

    for row in rows:
        title = (row.get("display") or "").strip()
        if not title:
            row["poster_url"] = None
            row["poster_source"] = "none"
            continue
        cache_key = title_hints.poster_cache_key_for_row(row)
        if not cache_key:
            row["poster_url"] = None
            row["poster_source"] = "none"
            continue

        if cache_key in lb_posters:
            row["poster_url"] = lb_posters[cache_key]
            row["poster_source"] = "letterboxd"
            stats["resolved_total"] += 1
            stats["resolved_letterboxd"] += 1
            continue

        if cache_key in cache and cache[cache_key]:
            row["poster_url"] = cache[cache_key]
            if cache[cache_key]:
                row["poster_source"] = "cache"
                stats["resolved_total"] += 1
                stats["resolved_cache"] += 1
            continue

        stats["new_network_lookups"] += 1
        if stats["new_network_lookups"] > max(1, config.POSTER_MAX_NETWORK_LOOKUPS):
            cache[cache_key] = None
            row["poster_url"] = None
            row["poster_source"] = "none"
            stats["unresolved"] += 1
            continue
        poster = None
        source = "none"

        imdb_id = (row.get("imdb_id") or "").strip()
        year_hint = title_hints.year_hint_from_row(row)
        search_title = title_hints.title_for_external_search(title)
        override_base = title_hints.normalize_metadata_key(title)
        if not imdb_id:
            imdb_id = (id_overrides.get(cache_key) or id_overrides.get(override_base) or "").strip()
        if not imdb_id and cache_key in id_cache:
            imdb_id = id_cache[cache_key] or ""
        if not imdb_id:
            imdb_id = _lookup_imdb_id_by_title(search_title, year_hint) or ""
            id_cache[cache_key] = imdb_id or None
        if imdb_id and not row.get("imdb_id"):
            row["imdb_id"] = imdb_id
        if imdb_id:
            if config.TMDB_API_CONFIGURED:
                poster = _fetch_tmdb_poster_by_imdb_find(imdb_id)
                if poster:
                    source = "tmdb"
            if not poster:
                poster = _fetch_imdb_poster_by_id(imdb_id)
                if poster:
                    source = "imdb"
                else:
                    # Small pacing to reduce temporary blocks.
                    time.sleep(0.12)

        if not poster:
            poster = _fetch_omdb_poster(
                imdb_id or None, search_title or None, year_hint
            )
            if poster:
                source = "omdb"

        if not poster:
            poster = _fetch_tmdb_web_poster(title, year_hint)
            if poster:
                source = "tmdb_web"

        if (not poster) and config.TMDB_API_CONFIGURED:
            poster = _fetch_tmdb_poster(title, year_hint)
            if poster:
                source = "tmdb"

        cache[cache_key] = poster
        row["poster_url"] = poster
        row["poster_source"] = source
        if poster:
            stats["resolved_total"] += 1
            if source == "imdb":
                stats["resolved_imdb"] += 1
            elif source == "tmdb_web":
                stats["resolved_tmdb"] += 1
            elif source == "tmdb":
                stats["resolved_tmdb"] += 1
            elif source == "omdb":
                stats["resolved_omdb"] += 1
        else:
            stats["unresolved"] += 1

    _save_cache(cache)
    _save_id_cache(id_cache)
    if log:
        log(
            "[Posters] resolved=%s/%s (lb=%s cache=%s imdb=%s tmdb=%s omdb=%s unresolved=%s new_lookups=%s)"
            % (
                stats["resolved_total"],
                len(rows),
                stats["resolved_letterboxd"],
                stats["resolved_cache"],
                stats["resolved_imdb"],
                stats["resolved_tmdb"],
                stats["resolved_omdb"],
                stats["unresolved"],
                stats["new_network_lookups"],
            )
        )
    return rows, stats

