"""Export local scraper cache into GitHub Pages JSON format."""
from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timezone
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import config  # noqa: E402
import streaming  # noqa: E402
import title_hints  # noqa: E402
import tmdb_client  # noqa: E402
DEFAULT_INPUT = ROOT / "data" / "cache.json"
DEFAULT_OUTPUT = ROOT / "docs" / "data" / "watchlist.json"
DEFAULT_METADATA_CACHE = ROOT / "data" / "imdb_metadata_cache.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _load_omdb_api_key() -> str:
    k = os.environ.get("OMDB_API_KEY", "").strip()
    if k:
        return k
    key_path = ROOT / "data" / "omdb_api_key.txt"
    if key_path.is_file():
        try:
            with key_path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        return line
        except OSError:
            pass
    return ""


OMDB_API_KEY = _load_omdb_api_key()


def infer_source(row: dict) -> str:
    lb = bool(row.get("letterboxd"))
    imdb = bool(row.get("imdb"))
    if lb and imdb:
        return "both"
    if lb:
        return "letterboxd"
    return "imdb"


def normalize_title(title: str) -> str:
    return title_hints.normalize_metadata_key(title)


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path: Path, data, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        if compact:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


DOCS_INDEX_HTML = ROOT / "docs" / "index.html"
WATCHLIST_VERSION_META_RE = re.compile(
    r'<meta\s+name="watchlist-version"\s+content="[^"]*"\s*/?>',
    re.I,
)


def export_poster_url(url: str | None) -> str | None:
    """Match posters.py: TMDb w154 fills the same card box as w185 (object-fit: cover)."""
    if not url or not isinstance(url, str):
        return None
    u = url.strip()
    if "image.tmdb.org" in u and "/t/p/w185/" in u:
        return u.replace("/t/p/w185/", "/t/p/w154/", 1)
    return u


def patch_docs_watchlist_version(version: str) -> None:
    """Keep docs/index.html meta in sync with JSON updated_at for cache-busting fetch URL."""
    path = DOCS_INDEX_HTML
    if not path.is_file():
        return
    safe = html.escape(version.strip(), quote=True)
    replacement = f'<meta name="watchlist-version" content="{safe}">'
    text = path.read_text(encoding="utf-8")
    if WATCHLIST_VERSION_META_RE.search(text):
        text = WATCHLIST_VERSION_META_RE.sub(replacement, text, count=1)
    else:
        insert_after = re.search(
            r'(<meta\s+name="viewport"[^>]*>)',
            text,
            flags=re.I,
        )
        if not insert_after:
            return
        text = text[: insert_after.end()] + "\n  " + replacement + text[insert_after.end() :]
    path.write_text(text, encoding="utf-8", newline="\n")


def lookup_imdb_hint_by_title(title: str, year_hint: int | None = None) -> dict:
    return title_hints.imdb_suggestion_lookup(title, year_hint, headers=HEADERS)


def _parse_int_loose(v) -> int | None:
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if not s:
        return None
    m = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*([KkMm])?$", s.replace(" ", ""))
    if m:
        try:
            n = float(m.group(1))
            suf = (m.group(2) or "").upper()
            if suf == "K":
                n *= 1000
            elif suf == "M":
                n *= 1_000_000
            return max(0, int(round(n)))
        except (TypeError, ValueError):
            return None
    try:
        return max(0, int(float(s)))
    except (TypeError, ValueError):
        return None


def _year_from_schema_movie(obj: dict) -> int | None:
    """Best-effort release year from schema.org Movie JSON-LD."""
    dp = str(obj.get("datePublished") or "")
    m = re.match(r"(\d{4})", dp)
    if m:
        return int(m.group(1))
    ev = obj.get("releasedEvent")
    if isinstance(ev, list) and ev and isinstance(ev[0], dict):
        sd = str(ev[0].get("startDate") or "")
        m = re.match(r"(\d{4})", sd)
        if m:
            return int(m.group(1))
    dc = str(obj.get("dateCreated") or "")
    m = re.match(r"(\d{4})", dc)
    if m:
        return int(m.group(1))
    return None


def _merge_title_meta(base: dict, extra: dict) -> dict:
    """Fill missing year, genres, IMDb-scale rating, and vote count from extra."""
    out = dict(base)
    if out.get("year") is None and extra.get("year") is not None:
        out["year"] = extra["year"]
    if not out.get("genres") and extra.get("genres"):
        out["genres"] = list(extra["genres"])
    if out.get("rating_imdb_10") is None and extra.get("rating_imdb_10") is not None:
        out["rating_imdb_10"] = extra["rating_imdb_10"]
    if out.get("rating_count_imdb") is None and extra.get("rating_count_imdb") is not None:
        out["rating_count_imdb"] = extra["rating_count_imdb"]
    return out


def _apply_omdb_truth_for_imdb_id(base: dict, omdb: dict) -> dict:
    """Overwrite fields when OMDb was queried by imdb_id (corrects bad HTML JSON-LD)."""
    out = dict(base)
    if omdb.get("year") is not None:
        out["year"] = omdb["year"]
    if omdb.get("genres"):
        out["genres"] = list(omdb["genres"])
    if omdb.get("rating_imdb_10") is not None:
        out["rating_imdb_10"] = omdb["rating_imdb_10"]
    if omdb.get("rating_count_imdb") is not None:
        out["rating_count_imdb"] = omdb["rating_count_imdb"]
    return out


_IMDB_JSONLD_MAIN_TYPES = frozenset(
    {
        "movie",
        "tvmovie",
        "tvseries",
        "tvminiseries",
        "tvepisode",
        "tvmovieseries",
    }
)


def _imdb_jsonld_types(node: dict) -> frozenset[str]:
    t = node.get("@type")
    if t is None:
        return frozenset()
    if isinstance(t, str):
        return frozenset(x.strip().lower() for x in t.split(",") if x.strip())
    if isinstance(t, list):
        return frozenset(str(x).strip().lower() for x in t if x)
    return frozenset({str(t).strip().lower()})


def _imdb_jsonld_node_references_title(node: dict, imdb_tt: str) -> bool:
    needle = f"/title/{imdb_tt}/"
    for key in ("url", "@id", "sameAs"):
        val = node.get(key)
        if isinstance(val, str) and needle in val:
            return True
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str) and needle in item:
                    return True
    return False


def _imdb_jsonld_is_main_work(types: frozenset[str]) -> bool:
    return bool(types & _IMDB_JSONLD_MAIN_TYPES)


def _jsonld_candidate_nodes(root) -> list[dict]:
    if isinstance(root, list):
        nodes: list[dict] = []
        for el in root:
            nodes.extend(_jsonld_candidate_nodes(el))
        return nodes
    if not isinstance(root, dict):
        return []
    graph = root.get("@graph")
    nodes = []
    if isinstance(graph, list):
        for el in graph:
            if isinstance(el, dict):
                nodes.append(el)
    if root.get("@type") is not None:
        if root not in nodes:
            nodes.append(root)
    if not nodes:
        nodes.append(root)
    return nodes


def _ld_genre_list(genre) -> list[str]:
    if isinstance(genre, str):
        return [genre] if genre.strip() else []
    if isinstance(genre, list):
        out: list[str] = []
        for x in genre:
            if isinstance(x, str):
                if x.strip():
                    out.append(x)
            elif isinstance(x, dict):
                n = (x.get("name") or "").strip()
                if n:
                    out.append(n)
        return out
    return []


def _meta_from_imdb_jsonld_node(node: dict) -> dict:
    out = {
        "year": None,
        "genres": [],
        "rating_imdb_10": None,
        "rating_count_imdb": None,
    }
    out["genres"] = _ld_genre_list(node.get("genre"))
    yr = _year_from_schema_movie(node)
    if yr is not None:
        out["year"] = yr
    rating_obj = node.get("aggregateRating") or {}
    if isinstance(rating_obj, dict):
        rv = rating_obj.get("ratingValue")
        try:
            if rv is not None:
                out["rating_imdb_10"] = float(rv)
        except (TypeError, ValueError):
            pass
        for rc_key in ("ratingCount", "reviewCount"):
            rc = rating_obj.get(rc_key)
            if rc is not None:
                n = _parse_int_loose(rc)
                if n is not None:
                    out["rating_count_imdb"] = n
                    break
    return out


def parse_imdb_title_page(imdb_id: str) -> dict:
    """
    Return metadata from IMDb title page:
      year, genres[], rating_imdb_10, rating_count_imdb (from JSON-LD or HTML)
    """
    tid = (imdb_id or "").strip()
    if not re.fullmatch(r"tt\d+", tid):
        tid = "tt" + tid.lstrip("t") if tid else ""
    if not tid:
        return {
            "year": None,
            "genres": [],
            "rating_imdb_10": None,
            "rating_count_imdb": None,
        }

    url = f"https://www.imdb.com/title/{tid}/"
    out = {
        "year": None,
        "genres": [],
        "rating_imdb_10": None,
        "rating_count_imdb": None,
    }
    try:
        r = requests.get(url, headers=HEADERS, timeout=16)
    except requests.RequestException:
        return out
    if r.status_code != 200 or len(r.text) < 800:
        return out

    soup = BeautifulSoup(r.text, "html.parser")
    scored: list[tuple[int, dict]] = []

    for script in soup.find_all("script", type="application/ld+json"):
        txt = (script.string or "").strip()
        if not txt:
            continue
        try:
            parsed = json.loads(txt)
        except ValueError:
            continue
        for node in _jsonld_candidate_nodes(parsed):
            if not isinstance(node, dict):
                continue
            types = _imdb_jsonld_types(node)
            url_ok = _imdb_jsonld_node_references_title(node, tid)
            main = _imdb_jsonld_is_main_work(types)
            if not main and not url_ok:
                continue
            meta = _meta_from_imdb_jsonld_node(node)
            if not (meta["year"] or meta["genres"] or meta["rating_imdb_10"] is not None):
                continue
            score = 0
            if url_ok:
                score += 200
            if main:
                score += 50
            if "movie" in types or "tvmovie" in types:
                score += 15
            if meta["rating_imdb_10"] is not None:
                score += 2
            if meta["year"] is not None:
                score += 1
            scored.append((score, meta))

    if scored:
        scored.sort(key=lambda x: -x[0])
        best = scored[0][1]
        out["year"] = best["year"]
        out["genres"] = list(best["genres"])
        out["rating_imdb_10"] = best["rating_imdb_10"]
        out["rating_count_imdb"] = best["rating_count_imdb"]

    # Fallback for rating if JSON-LD wasn't present/parseable.
    t = soup.get_text(" ", strip=True)
    m_rating = re.search(r"\b(\d\.\d)\s*/\s*10\b", t)
    if m_rating:
        try:
            out["rating_imdb_10"] = float(m_rating.group(1))
        except ValueError:
            pass
    if out["rating_count_imdb"] is None:
        mv = re.search(
            r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*([KkMm])?\s+ratings?\b",
            r.text,
            re.I,
        )
        if mv:
            raw = mv.group(1) + (mv.group(2) or "")
            n = _parse_int_loose(raw.replace(",", ""))
            if n is not None:
                out["rating_count_imdb"] = n
    return out


def _letterboxd_stats_from_film_html(html: str) -> dict:
    """Parse Letterboxd film page HTML for JSON-LD aggregateRating."""
    out = {"rating_letterboxd_5": None, "rating_count_letterboxd": None}
    fsoup = BeautifulSoup(html, "html.parser")
    for script in fsoup.find_all("script", type="application/ld+json"):
        txt = (script.string or "").strip()
        if not txt:
            continue
        try:
            obj = json.loads(txt)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        otypes = str(obj.get("@type", "")).lower()
        if "movie" not in otypes and "creativework" not in otypes:
            continue
        ar = obj.get("aggregateRating") or {}
        if not isinstance(ar, dict):
            continue
        rv = ar.get("ratingValue")
        try:
            if rv is not None:
                r5 = float(rv)
                br = ar.get("bestRating")
                if br is not None:
                    try:
                        bf = float(br)
                        if bf > 5.5:
                            r5 = r5 * 5.0 / bf
                    except (TypeError, ValueError):
                        pass
                out["rating_letterboxd_5"] = min(5.0, max(0.0, r5))
        except (TypeError, ValueError):
            pass
        for rc_key in ("ratingCount", "reviewCount"):
            rc = ar.get(rc_key)
            if rc is not None:
                n = _parse_int_loose(rc)
                if n is not None:
                    out["rating_count_letterboxd"] = n
                    break
        if out["rating_letterboxd_5"] is not None or out["rating_count_letterboxd"] is not None:
            break
    return out


def fetch_letterboxd_film_stats(title: str, year: int | None = None) -> dict:
    """
    Best-effort Letterboxd community average (0–5) and rating count from film pages
    (search → try several /film/…/ hits → JSON-LD aggregateRating).
    """
    out = {"rating_letterboxd_5": None, "rating_count_letterboxd": None}
    t = (title or "").strip()
    if not t:
        return out
    enc = quote(t, safe="")
    try:
        r = requests.get(f"https://letterboxd.com/search/{enc}/", headers=HEADERS, timeout=15)
    except requests.RequestException:
        return out
    if r.status_code != 200:
        return out
    soup = BeautifulSoup(r.text, "html.parser")
    skip = {"lists", "watchlist", "popular", "crew", "actor", "director", "members"}
    hrefs_ordered: list[str] = []
    seen: set[str] = set()
    year_links: list[str] = []
    ypat = re.compile(rf"\b{int(year)}\b") if year is not None else None
    for a in soup.select('a[href^="/film/"]'):
        h = (a.get("href") or "").split("?")[0]
        segs = [x for x in h.strip("/").split("/") if x]
        if len(segs) < 2 or segs[0] != "film" or segs[1] in skip:
            continue
        href = "/" + "/".join(segs[:2]) + "/"
        if href in seen:
            continue
        seen.add(href)
        if ypat is not None:
            ctx = ""
            el = a.parent
            for _ in range(5):
                if el is None:
                    break
                if hasattr(el, "get_text"):
                    ctx += el.get_text(" ", strip=True) + " "
                el = getattr(el, "parent", None)
            if ypat.search(ctx):
                year_links.append(href)
        hrefs_ordered.append(href)
        if len(hrefs_ordered) >= 10:
            break

    yset = set(year_links)
    try_hrefs = year_links + [h for h in hrefs_ordered if h not in yset]
    for href in try_hrefs[:8]:
        try:
            fr = requests.get("https://letterboxd.com" + href, headers=HEADERS, timeout=15)
        except requests.RequestException:
            continue
        if fr.status_code != 200:
            continue
        st = _letterboxd_stats_from_film_html(fr.text)
        if st["rating_letterboxd_5"] is not None:
            return st
        if st["rating_count_letterboxd"] is not None and out["rating_count_letterboxd"] is None:
            out["rating_count_letterboxd"] = st["rating_count_letterboxd"]
    return out


def combined_rating_weighted_5(
    imdb_5: float | None,
    imdb_n: int | None,
    lb_5: float | None,
    lb_n: int | None,
) -> float | None:
    """Vote-weighted average on 0–5 scale; unknown counts use weight 1."""
    parts: list[float] = []
    weights: list[float] = []
    if imdb_5 is not None:
        w = float(imdb_n) if imdb_n and imdb_n > 0 else 1.0
        parts.append(imdb_5 * w)
        weights.append(w)
    if lb_5 is not None:
        w = float(lb_n) if lb_n and lb_n > 0 else 1.0
        parts.append(lb_5 * w)
        weights.append(w)
    if not parts:
        return None
    return round2(sum(parts) / sum(weights))


def fetch_omdb_metadata(imdb_id: str | None = None, title: str | None = None) -> dict:
    """
    Fetch metadata from OMDb API (requires free API key from omdbapi.com).
    Returns year, genres[], rating_imdb_10, content_type.
    """
    out = {
        "year": None,
        "genres": [],
        "rating_imdb_10": None,
        "content_type": None,
        "rating_count_imdb": None,
    }
    if not OMDB_API_KEY:
        return out
    params = {"apikey": OMDB_API_KEY}
    if imdb_id:
        params["i"] = imdb_id
    elif title:
        params["t"] = title.strip()
    else:
        return out
    try:
        r = requests.get("http://www.omdbapi.com/", params=params, timeout=12)
    except requests.RequestException:
        return out
    if r.status_code != 200:
        return out
    try:
        data = r.json()
    except ValueError:
        return out
    if data.get("Response") != "True":
        return out
    year_str = data.get("Year", "")
    m = re.match(r"(\d{4})", str(year_str))
    if m:
        out["year"] = int(m.group(1))
    genre_str = data.get("Genre", "")
    if genre_str and genre_str != "N/A":
        out["genres"] = [g.strip() for g in genre_str.split(",") if g.strip()]
    rating_str = data.get("imdbRating", "")
    if rating_str and rating_str != "N/A":
        try:
            out["rating_imdb_10"] = float(rating_str)
        except ValueError:
            pass
    votes = data.get("imdbVotes", "")
    if votes and votes != "N/A":
        out["rating_count_imdb"] = _parse_int_loose(str(votes).replace(",", ""))
    out["content_type"] = data.get("Type")  # "movie", "series", or "episode"
    return out


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


def _tmdb_search_first_movie_href(soup: BeautifulSoup) -> str | None:
    """
    TMDB's /search/movie mixes people and movies in `.result` links; pick a real title path
    (/movie/<digits>-slug), not nav or person URLs.
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


def fetch_tmdb_metadata_by_title(title: str) -> dict:
    """
    No-key fallback metadata from TMDB website pages.
    """
    out: dict = {"year": None, "genres": [], "rating_imdb_10": None, "rating_count_imdb": None}
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
    href = _tmdb_search_first_movie_href(soup)
    if not href:
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
        yr = _year_from_schema_movie(obj)
        if yr is not None:
            out["year"] = yr
        rating_obj = obj.get("aggregateRating") or {}
        if isinstance(rating_obj, dict):
            rv = rating_obj.get("ratingValue")
            try:
                if rv is not None:
                    val = float(rv)
                    br = rating_obj.get("bestRating")
                    if br is not None:
                        try:
                            bf = float(br)
                            if 0 < bf <= 5.5:
                                val = val * 10.0 / bf
                        except (TypeError, ValueError):
                            pass
                    out["rating_imdb_10"] = val
            except (TypeError, ValueError):
                pass
            for rc_key in ("ratingCount", "reviewCount"):
                rc = rating_obj.get(rc_key)
                if rc is not None:
                    n = _parse_int_loose(rc)
                    if n is not None:
                        out["rating_count_imdb"] = n
                        break
        return out
    return out


def _tmdb_movie_detail_to_meta(detail: dict | None) -> dict:
    """Map TMDb /movie/{id} JSON to exporter metadata fields."""
    out: dict = {"year": None, "genres": [], "rating_imdb_10": None, "rating_count_imdb": None}
    if not detail or not isinstance(detail, dict):
        return out
    rd = detail.get("release_date") or ""
    if len(rd) >= 4 and str(rd[:4]).isdigit():
        try:
            out["year"] = int(rd[:4])
        except ValueError:
            pass
    for g in detail.get("genres") or []:
        if isinstance(g, dict):
            n = (g.get("name") or "").strip()
            if n:
                out["genres"].append(n)
    va = detail.get("vote_average")
    if va is not None:
        try:
            v = float(va)
            if v > 0:
                out["rating_imdb_10"] = v
        except (TypeError, ValueError):
            pass
    vc = detail.get("vote_count")
    if vc is not None:
        try:
            out["rating_count_imdb"] = int(vc)
        except (TypeError, ValueError):
            pass
    return out


def fetch_tmdb_metadata_via_imdb_id(imdb_id: str) -> dict:
    """TMDb /find by IMDb id, then /movie/{id} — avoids wrong title search hits."""
    empty: dict = {"year": None, "genres": [], "rating_imdb_10": None, "rating_count_imdb": None}
    if not config.TMDB_API_CONFIGURED or not (imdb_id or "").strip():
        return empty
    tid = (imdb_id or "").strip()
    if not re.fullmatch(r"tt\d+", tid):
        tid = "tt" + tid.lstrip("t")
    data = tmdb_client.tmdb_v3_get(f"/find/{tid}", {"external_source": "imdb_id"})
    if not data:
        return empty
    mid = None
    for mr in data.get("movie_results") or []:
        if not isinstance(mr, dict):
            continue
        try:
            mid = int(mr.get("id"))
            break
        except (TypeError, ValueError):
            continue
    if mid is None:
        return empty
    detail = tmdb_client.tmdb_v3_get(f"/movie/{mid}", {})
    return _tmdb_movie_detail_to_meta(detail)


def fetch_tmdb_metadata_via_api(title: str, year_hint: int | None = None) -> dict:
    """TMDb v3 search (with optional primary_release_year) + /movie/{id} for gap-fill metadata."""
    if not config.TMDB_API_CONFIGURED:
        return {"year": None, "genres": [], "rating_imdb_10": None, "rating_count_imdb": None}
    mid = streaming._find_movie_id_by_title((title or "").strip(), year_hint)
    if mid is None:
        return {"year": None, "genres": [], "rating_imdb_10": None, "rating_count_imdb": None}
    detail = tmdb_client.tmdb_v3_get(f"/movie/{mid}", {})
    return _tmdb_movie_detail_to_meta(detail)


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
    id_overrides = title_hints.load_imdb_id_overrides(config.IMDB_ID_OVERRIDES_PATH)

    rows = cache.get("rows") or []
    stats = cache.get("stats") or {}
    posters_resolved = sum(1 for r in rows if r.get("poster_url"))

    print(f"Processing {len(rows)} movies...")
    print(f"OMDb API: {'enabled' if OMDB_API_KEY else 'disabled'}")
    if id_overrides:
        print(f"IMDb id overrides: {len(id_overrides)} keys ({config.IMDB_ID_OVERRIDES_PATH})")
    print()

    movies = []
    total = len(rows)
    for idx, r in enumerate(rows, 1):
        title = (r.get("display") or "").strip()
        if not title:
            continue
        norm = normalize_title(title)
        c = meta_cache.get(norm) if isinstance(meta_cache.get(norm), dict) else {}

        yr_row = title_hints.year_hint_from_row(r)
        imdb_id = r.get("imdb_id")
        hint: dict = {"imdb_id": None, "year": None}
        if not imdb_id:
            oid = id_overrides.get(norm)
            if oid:
                imdb_id = oid
        if not imdb_id:
            imdb_id = c.get("imdb_id")
        if not imdb_id:
            hint = lookup_imdb_hint_by_title(title, year_hint=yr_row)
            imdb_id = hint.get("imdb_id")

        meta_incomplete = (
            c.get("year") is None
            or not c.get("genres")
            or c.get("rating_imdb_10") is None
        )
        needs_refresh = (
            not c
            or c.get("imdb_id") != imdb_id
            or "year" not in c
            or meta_incomplete
            or (
                imdb_id
                and c.get("rating_imdb_10") is not None
                and c.get("rating_count_imdb") is None
            )
        )

        source_used = "cached"
        content_type = c.get("content_type")
        if imdb_id and needs_refresh:
            prev_meta = dict(c) if isinstance(c, dict) else {}
            parsed = parse_imdb_title_page(imdb_id)
            content_type = None
            sources: list[str] = []
            if parsed.get("year") or parsed.get("genres") or parsed.get("rating_imdb_10") is not None:
                sources.append("IMDb")
            if (
                parsed.get("year") is None
                or not parsed.get("genres")
                or parsed.get("rating_imdb_10") is None
            ):
                tmdb_p = {
                    "year": None,
                    "genres": [],
                    "rating_imdb_10": None,
                    "rating_count_imdb": None,
                }
                if config.TMDB_API_CONFIGURED:
                    tmdb_p = _merge_title_meta(
                        tmdb_p,
                        fetch_tmdb_metadata_via_imdb_id(imdb_id),
                    )
                    tmdb_p = _merge_title_meta(
                        tmdb_p,
                        fetch_tmdb_metadata_via_api(title, yr_row),
                    )
                still_missing = (
                    (parsed.get("year") is None and tmdb_p.get("year") is None)
                    or (not parsed.get("genres") and not tmdb_p.get("genres"))
                    or (
                        parsed.get("rating_imdb_10") is None
                        and tmdb_p.get("rating_imdb_10") is None
                    )
                )
                if still_missing:
                    tmdb_p = _merge_title_meta(tmdb_p, fetch_tmdb_metadata_by_title(title))
                parsed = _merge_title_meta(parsed, tmdb_p)
                if tmdb_p.get("year") or tmdb_p.get("genres") or tmdb_p.get("rating_imdb_10") is not None:
                    sources.append("TMDB")
            if OMDB_API_KEY and imdb_id:
                omdb_p = fetch_omdb_metadata(imdb_id=imdb_id, title=title)
                parsed = _merge_title_meta(parsed, omdb_p)
                parsed = _apply_omdb_truth_for_imdb_id(parsed, omdb_p)
                content_type = omdb_p.get("content_type")
                if omdb_p.get("year") or omdb_p.get("genres") or omdb_p.get("rating_imdb_10"):
                    sources.append("OMDb")
            source_used = "+".join(sources) if sources else "no data"
            if parsed.get("rating_count_imdb") is None and OMDB_API_KEY:
                ov = fetch_omdb_metadata(imdb_id=imdb_id)
                if ov.get("rating_count_imdb"):
                    parsed["rating_count_imdb"] = ov["rating_count_imdb"]
            # If we still don't have content_type, fetch it from OMDb
            if content_type is None and OMDB_API_KEY:
                omdb_check = fetch_omdb_metadata(imdb_id=imdb_id)
                content_type = omdb_check.get("content_type")
            merged_genres = parsed.get("genres") if parsed.get("genres") else (prev_meta.get("genres") or [])
            merged_year = (
                parsed.get("year") or hint.get("year") or yr_row or prev_meta.get("year")
            )
            merged_rating = (
                parsed.get("rating_imdb_10")
                if parsed.get("rating_imdb_10") is not None
                else prev_meta.get("rating_imdb_10")
            )
            merged_count = (
                parsed.get("rating_count_imdb")
                if parsed.get("rating_count_imdb") is not None
                else prev_meta.get("rating_count_imdb")
            )
            merged_ct = content_type if content_type is not None else prev_meta.get("content_type")
            c = {
                "imdb_id": imdb_id,
                "year": merged_year,
                "genres": merged_genres,
                "rating_imdb_10": merged_rating,
                "rating_count_imdb": merged_count,
                "content_type": merged_ct,
                "rating_letterboxd_5": prev_meta.get("rating_letterboxd_5"),
                "rating_count_letterboxd": prev_meta.get("rating_count_letterboxd"),
            }
            meta_cache[norm] = c
        elif not imdb_id and needs_refresh:
            # No imdb_id - try TMDB (API + optional web scrape) and OMDb by title
            parsed = {
                "year": None,
                "genres": [],
                "rating_imdb_10": None,
                "rating_count_imdb": None,
            }
            tmdb_p = {
                "year": None,
                "genres": [],
                "rating_imdb_10": None,
                "rating_count_imdb": None,
            }
            if config.TMDB_API_CONFIGURED:
                tmdb_p = _merge_title_meta(tmdb_p, fetch_tmdb_metadata_via_api(title, yr_row))
            still_missing = (
                tmdb_p.get("year") is None
                and not tmdb_p.get("genres")
                and tmdb_p.get("rating_imdb_10") is None
            )
            if still_missing:
                tmdb_p = _merge_title_meta(tmdb_p, fetch_tmdb_metadata_by_title(title))
            parsed = _merge_title_meta(parsed, tmdb_p)
            content_type = None
            sources_no_id: list[str] = []
            if tmdb_p.get("year") or tmdb_p.get("genres") or tmdb_p.get("rating_imdb_10") is not None:
                sources_no_id.append("TMDB")
            if (
                parsed.get("year") is None
                or not parsed.get("genres")
                or parsed.get("rating_imdb_10") is None
            ):
                omdb_p = fetch_omdb_metadata(title=title)
                parsed = _merge_title_meta(parsed, omdb_p)
                content_type = omdb_p.get("content_type")
                if omdb_p.get("year") or omdb_p.get("genres") or omdb_p.get("rating_imdb_10"):
                    sources_no_id.append("OMDb")
            source_used = "+".join(sources_no_id) if sources_no_id else "no data"
            c = {
                "imdb_id": None,
                "year": parsed.get("year") or hint.get("year") or yr_row,
                "genres": parsed.get("genres") or [],
                "rating_imdb_10": parsed.get("rating_imdb_10"),
                "rating_count_imdb": parsed.get("rating_count_imdb"),
                "content_type": content_type,
                "rating_letterboxd_5": None,
                "rating_count_letterboxd": None,
            }
            meta_cache[norm] = c
        elif not c:
            c = {
                "imdb_id": imdb_id,
                "year": None,
                "genres": [],
                "rating_imdb_10": None,
                "rating_count_imdb": None,
                "content_type": None,
                "rating_letterboxd_5": None,
                "rating_count_letterboxd": None,
            }
            meta_cache[norm] = c
            source_used = "no data"

        print(f"[{idx}/{total}] {title[:50]}{'...' if len(title) > 50 else ''} ({source_used})")

        if r.get("letterboxd") and (
            c.get("rating_letterboxd_5") is None or c.get("rating_count_letterboxd") is None
        ):
            time.sleep(0.08)
            lb_yr = c.get("year")
            lb_year = lb_yr if isinstance(lb_yr, int) and 1870 < lb_yr < 2100 else None
            lbstats = fetch_letterboxd_film_stats(title, year=lb_year)
            if lbstats.get("rating_letterboxd_5") is not None:
                c["rating_letterboxd_5"] = lbstats["rating_letterboxd_5"]
            if lbstats.get("rating_count_letterboxd") is not None:
                c["rating_count_letterboxd"] = lbstats["rating_count_letterboxd"]
            meta_cache[norm] = c

        rating_imdb_10 = c.get("rating_imdb_10")
        rating_count_imdb = c.get("rating_count_imdb")
        try:
            rating_count_imdb = int(rating_count_imdb) if rating_count_imdb is not None else None
        except (TypeError, ValueError):
            rating_count_imdb = None

        rating_letterboxd_5 = c.get("rating_letterboxd_5")
        if rating_letterboxd_5 is None:
            rating_letterboxd_5 = r.get("rating_letterboxd_5")
        rating_count_lb = c.get("rating_count_letterboxd")
        try:
            rating_count_lb = int(rating_count_lb) if rating_count_lb is not None else None
        except (TypeError, ValueError):
            rating_count_lb = None

        imdb_5 = None
        if rating_imdb_10 is not None:
            try:
                imdb_5 = float(rating_imdb_10) / 2.0
            except (TypeError, ValueError):
                imdb_5 = None

        try:
            lb_5f = float(rating_letterboxd_5) if rating_letterboxd_5 is not None else None
        except (TypeError, ValueError):
            lb_5f = None

        rating_avg_5 = combined_rating_weighted_5(imdb_5, rating_count_imdb, lb_5f, rating_count_lb)

        movies.append(
            {
                "title": title,
                "poster_url": export_poster_url(r.get("poster_url")),
                "source": infer_source(r),
                "imdb_id": imdb_id,
                "year": c.get("year"),
                "genres": c.get("genres") or [],
                "rating_imdb_10": round2(rating_imdb_10 if rating_imdb_10 is not None else None),
                "rating_count_imdb": rating_count_imdb,
                "rating_letterboxd_5": round2(lb_5f if lb_5f is not None else None),
                "rating_count_letterboxd": rating_count_lb,
                "rating_avg_5": rating_avg_5,
                "content_type": c.get("content_type"),
                "streaming": r.get("streaming") if isinstance(r.get("streaming"), dict) else {},
            }
        )

    # Filter out TV series and episodes - keep only movies
    total_before_filter = len(movies)
    movies = [m for m in movies if m.get("content_type") in (None, "movie")]
    filtered_count = total_before_filter - len(movies)

    movies.sort(key=lambda m: m["title"].lower())

    profile = config.load_owned_streaming_profile()
    stream_region_export = (profile.get("region") or "US").upper()
    stream_owned_ids = [p["id"] for p in (profile.get("providers") or [])]
    def _streaming_has_providers(m: dict) -> bool:
        s = m.get("streaming") or {}
        if not isinstance(s, dict):
            return False
        for v in s.values():
            if not isinstance(v, dict):
                continue
            if v.get("flatrate") or v.get("rent") or v.get("buy"):
                return True
        return False

    streaming_nonempty = sum(1 for m in movies if _streaming_has_providers(m))

    updated_at = cache.get("updated_at")
    if not updated_at:
        updated_at = datetime.now(timezone.utc).isoformat()

    payload = {
        "updated_at": updated_at,
        "stream_region": stream_region_export,
        "stream_owned_provider_ids": stream_owned_ids,
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

    save_json(output_path, payload, compact=True)
    save_json(meta_cache_path, meta_cache)
    patch_docs_watchlist_version(str(payload["updated_at"]))

    missing_year = sum(1 for m in movies if m.get("year") is None)
    missing_genre = sum(1 for m in movies if not m.get("genres"))
    missing_rating = sum(1 for m in movies if m.get("rating_imdb_10") is None)

    print()
    print(f"Exported {len(movies)} movies to {output_path}")
    print(f"  Streaming blocks (non-empty): {streaming_nonempty}/{len(movies)} (region {stream_region_export} in JSON)")
    if streaming_nonempty == 0:
        print(
            "  Note: All streaming blocks are empty. Provider data is filled when cache refresh runs "
            "with TMDb configured; run: python scripts/check_streaming_setup.py"
        )
    if filtered_count > 0:
        print(f"  Filtered out: {filtered_count} TV series/episodes")
    print(f"  With year: {len(movies) - missing_year}/{len(movies)}")
    print(f"  With genre: {len(movies) - missing_genre}/{len(movies)}")
    print(f"  With rating: {len(movies) - missing_rating}/{len(movies)}")
    if OMDB_API_KEY:
        print("  OMDb API: enabled")
    else:
        print("  OMDb API: not configured (add key to data/omdb_api_key.txt for better coverage)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
