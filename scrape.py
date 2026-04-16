"""Fetch watchlist titles from Letterboxd (HTTP) and IMDb (browser)."""
from __future__ import annotations

import csv
import glob
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass
from typing import Callable

import requests
from bs4 import BeautifulSoup

import config
import title_hints


# #region agent log
def _agent_dbg(hypothesis_id: str, location: str, message: str, data: dict) -> None:
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug-06e316.log")
    try:
        with open(p, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "sessionId": "06e316",
                        "hypothesisId": hypothesis_id,
                        "location": location,
                        "message": message,
                        "data": data,
                        "timestamp": int(time.time() * 1000),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except OSError:
        pass


# #endregion

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def normalize_title(title: str) -> str:
    t = title.strip().lower()
    t = re.sub(r"^\d+\.\s*", "", t)
    t = re.sub(r"\([^)]*\)", "", t)
    t = re.sub(r"\[[^\]]*\]", "", t)
    t = re.sub(r"\b(19|20)\d{2}\b", "", t)
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def clean_imdb_title(title: str) -> str:
    title = title.strip()
    title = re.sub(r"^\d+\.\s*", "", title)
    return title.strip()


def get_letterboxd_titles(
    base_url: str | None = None,
    username_to_exclude: str | None = None,
    sleep_s: float = 0.35,
    log: Callable[[str], None] | None = None,
) -> tuple[list[str], str | None]:
    base_url = base_url or config.LETTERBOXD_WATCHLIST_URL
    username_to_exclude = (
        username_to_exclude if username_to_exclude is not None else config.LETTERBOXD_USERNAME_EXCLUDE
    )

    def _log(msg: str) -> None:
        if log:
            log(msg)

    titles: list[str] = []
    page = 1
    excluded_norm = normalize_title(username_to_exclude) if username_to_exclude else ""

    while True:
        url = base_url if page == 1 else base_url.rstrip("/") + f"/page/{page}/"
        _log(f"[Letterboxd] Page {page}: {url}")

        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
        except requests.RequestException as e:
            return titles, f"Letterboxd request failed: {e}"

        if response.status_code != 200:
            return titles, f"Letterboxd HTTP {response.status_code}"

        soup = BeautifulSoup(response.text, "html.parser")
        page_titles: list[str] = []

        for img in soup.find_all("img", alt=True):
            alt = img.get("alt", "").strip()
            if not alt:
                continue
            norm = normalize_title(alt)
            if norm == "letterboxd":
                continue
            if excluded_norm and norm == excluded_norm:
                continue
            page_titles.append(alt)

        cleaned: list[str] = []
        seen_page: set[str] = set()
        for title in page_titles:
            norm = normalize_title(title)
            if norm and norm not in seen_page:
                seen_page.add(norm)
                cleaned.append(title)

        if not cleaned:
            break

        new_count = 0
        existing_norms = {normalize_title(x) for x in titles}
        for title in cleaned:
            norm = normalize_title(title)
            if norm not in existing_norms:
                titles.append(title)
                existing_norms.add(norm)
                new_count += 1

        _log(f"[Letterboxd] +{new_count} new on page {page}")

        if new_count == 0:
            break

        page += 1
        time.sleep(sleep_s)

    return titles, None


@dataclass
class ImdbResult:
    titles: list[str]
    items: list[dict] | None = None
    error: str | None = None


# Prefer links inside IMDb watchlist list rows (live DOM). Unscoped `a[href*="/title/tt"]`
# also picks up recommendations, ads, and footer links — false positives vs the real list.
IMDB_WATCHLIST_LINK_SELECTORS: tuple[str, ...] = (
    "li.ipc-metadata-list-summary-item a[href*='/title/tt']",
)

# IMDb CSV "Title Type" values normalized (lowercase, no spaces) for movies-only filtering.
_IMDB_NON_MOVIE_TITLE_TYPES = frozenset(
    {
        "tvseries",
        "tvminiseries",
        "tvepisode",
        "tvspecial",
        "tvshort",
        "tvmovie",
        "tvpilot",
        "videogame",
    }
)


def _imdb_csv_title_type_token(raw: str | None) -> str | None:
    if not raw or not isinstance(raw, str):
        return None
    t = re.sub(r"[\s_-]+", "", raw.strip().lower())
    return t or None


def imdb_title_type_is_tv(token: str | None) -> bool:
    """True when CSV/merged title type is TV (or non-movie) per IMDb export."""
    if not token:
        return False
    return _imdb_csv_title_type_token(token) in _IMDB_NON_MOVIE_TITLE_TYPES


def _parse_imdb_csv(path: str) -> tuple[list[str], list[dict]]:
    titles: list[str] = []
    items: list[dict] = []
    seen: set[str] = set()
    skipped_tv = 0
    fieldnames: list[str] | None = None
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        for raw in reader:
            row = {(k or "").strip(): (v if v is None else str(v).strip()) for k, v in raw.items()}
            title = (row.get("Title") or row.get("title") or "").strip()
            imdb_id = (row.get("Const") or row.get("const") or row.get("tconst") or "").strip()
            if not imdb_id:
                url = (row.get("URL") or row.get("url") or "").strip()
                m = re.search(r"(tt\d+)", url)
                if m:
                    imdb_id = m.group(1)
            if not title:
                continue
            raw_ty = (
                row.get("Title Type")
                or row.get("title type")
                or row.get("TitleType")
                or row.get("Type")
                or ""
            )
            ty_token = _imdb_csv_title_type_token(raw_ty if isinstance(raw_ty, str) else "")
            if config.IMDB_WATCHLIST_MOVIES_ONLY and ty_token and imdb_title_type_is_tv(ty_token):
                skipped_tv += 1
                continue
            norm = normalize_title(title)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            titles.append(title)
            items.append({"title": title, "imdb_id": imdb_id or None, "imdb_title_type": ty_token})
    # #region agent log
    _agent_dbg(
        "D",
        "scrape.py:_parse_imdb_csv",
        "csv_parse_summary",
        {
            "movies_only": config.IMDB_WATCHLIST_MOVIES_ONLY,
            "fieldnames": fieldnames,
            "out_titles": len(titles),
            "skipped_tv_rows": skipped_tv,
        },
    )
    # #endregion
    return titles, items


def _imdb_scroll_watchlist_page(driver, log: Callable[[str], None], *, max_rounds: int = 80) -> None:
    """Scroll to bottom repeatedly so lazy-loaded watchlist rows appear."""
    from selenium.webdriver.common.by import By

    last_count = 0
    stable_rounds = 0
    for _ in range(max_rounds):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.85)
        links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/title/tt"]')
        count = len(links)
        if count == last_count:
            stable_rounds += 1
            if stable_rounds >= 3:
                break
        else:
            stable_rounds = 0
        last_count = count


def _imdb_items_from_anchor_elements(elements) -> tuple[list[str], list[dict]]:
    """Deduplicate by normalized title; collect display title and tt id from href."""
    raw: list[str] = []
    raw_items: list[dict] = []
    seen: set[str] = set()
    blocklist = {
        "watchlist",
        "ratings",
        "reviews",
        "share",
        "more",
        "list",
        "lists",
        "",
    }
    for a in elements:
        try:
            href = a.get_attribute("href") or ""
        except Exception:
            continue
        if "/title/tt" not in href:
            continue
        text = (a.text or "").strip()
        if not text:
            continue
        cleaned = clean_imdb_title(text)
        norm = normalize_title(cleaned)
        if not norm or norm in blocklist:
            continue
        if norm in seen:
            continue
        seen.add(norm)
        raw.append(cleaned)
        m = re.search(r"/title/(tt\d+)", href)
        imdb_id = m.group(1) if m else None
        raw_items.append({"title": cleaned, "imdb_id": imdb_id})
    return raw, raw_items


def _imdb_collect_scoped_watchlist(driver, log: Callable[[str], None]) -> tuple[list[str], list[dict]]:
    """Titles from watchlist list rows only (excludes recommendations elsewhere on the page)."""
    from selenium.webdriver.common.by import By

    all_elements: list = []
    seen_ids: set[int] = set()
    for sel in IMDB_WATCHLIST_LINK_SELECTORS:
        for el in driver.find_elements(By.CSS_SELECTOR, sel):
            eid = id(el)
            if eid not in seen_ids:
                seen_ids.add(eid)
                all_elements.append(el)
    titles, items = _imdb_items_from_anchor_elements(all_elements)
    log(f"[IMDb] Scoped watchlist selectors: {len(titles)} titles")
    return titles, items


def _imdb_collect_unscoped_page(driver, log: Callable[[str], None]) -> tuple[list[str], list[dict]]:
    """All /title/ links on the current page (may include recommendations)."""
    from selenium.webdriver.common.by import By

    elements = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/title/tt"]')
    titles, items = _imdb_items_from_anchor_elements(elements)
    log(f"[IMDb] Unscoped page scrape: {len(titles)} titles (may include non-watchlist links)")
    return titles, items


def _imdb_try_export_csv(
    driver,
    download_dir: str,
    wait,
    log: Callable[[str], None],
) -> tuple[list[str], list[dict]] | None:
    """Return parsed watchlist from IMDb export CSV, or None if not available."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as ec

    log("[IMDb] Trying export CSV flow")
    try:
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.5)
        export_button = wait.until(
            ec.element_to_be_clickable(
                (
                    By.XPATH,
                    "//button[contains(., 'Export')] | //a[contains(., 'Export')]",
                )
            )
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", export_button)
        time.sleep(0.35)
        driver.execute_script("arguments[0].click();", export_button)
        time.sleep(1.5)
        driver.get("https://www.imdb.com/exports/")

        deadline = time.time() + 45
        csv_path = ""
        while time.time() < deadline:
            files = sorted(glob.glob(os.path.join(download_dir, "*.csv")), key=os.path.getmtime, reverse=True)
            if files:
                csv_path = files[0]
                break
            links = driver.find_elements(By.CSS_SELECTOR, 'a[href$=".csv"], a[href*=".csv?"]')
            if links:
                try:
                    links[0].click()
                except Exception:
                    pass
            time.sleep(2)

        if not csv_path:
            return None
        titles, items = _parse_imdb_csv(csv_path)
        log(f"[IMDb] Parsed {len(titles)} titles from export CSV (may lag live watchlist)")
        if titles:
            return titles, items
    except Exception as export_err:
        log(f"[IMDb] Export flow not available this run: {export_err!s}")
    return None


def _imdb_dump_debug_page(driver, log: Callable[[str], None] | None) -> None:
    """Write page source when IMDb scrape is empty and SELENIUM_DEBUG_HTML_DIR is set."""
    out_dir = config.SELENIUM_DEBUG_HTML_DIR
    if not out_dir:
        return
    try:
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "imdb_watchlist_debug.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(driver.page_source or "")
        title = ""
        cur = ""
        try:
            title = (driver.title or "")[:200]
            cur = (driver.current_url or "")[:300]
        except Exception:
            pass
        msg = f"[IMDb] Debug: saved page source to {path} (title={title!r} url={cur!r})"
        if log:
            log(msg)
    except OSError as e:
        if log:
            log(f"[IMDb] Debug HTML dump failed: {e}")


def _imdb_with_selenium(
    url: str,
    log: Callable[[str], None] | None,
    *,
    headless_override: bool | None = None,
) -> ImdbResult:
    def _log(msg: str) -> None:
        if log:
            log(msg)

    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options as ChromeOptions
        from selenium.webdriver.common.by import By
        from selenium.webdriver.firefox.options import Options as FirefoxOptions
        from selenium.webdriver.firefox.service import Service as FirefoxService
        from selenium.webdriver.support import expected_conditions as ec
        from selenium.webdriver.support.ui import WebDriverWait
    except ImportError:
        # #region agent log
        _agent_dbg("A", "scrape.py:_imdb_with_selenium", "imdb_source_branch", {"branch": "no_selenium"})
        # #endregion
        return ImdbResult([], "Install selenium: pip install selenium webdriver-manager")

    driver = None
    try:
        use_headless = config.SELENIUM_HEADLESS if headless_override is None else headless_override
        download_dir = tempfile.mkdtemp(prefix="imdb_export_")

        if config.SELENIUM_BROWSER == "firefox":
            opts = FirefoxOptions()
            if use_headless:
                opts.add_argument("-headless")
            opts.set_preference("browser.download.folderList", 2)
            opts.set_preference("browser.download.dir", download_dir)
            opts.set_preference("browser.helperApps.neverAsk.saveToDisk", "text/csv,application/csv")
            opts.set_preference("browser.download.manager.showWhenStarting", False)
            from webdriver_manager.firefox import GeckoDriverManager

            driver = webdriver.Firefox(
                service=FirefoxService(GeckoDriverManager().install()),
                options=opts,
            )
        else:
            opts = ChromeOptions()
            if use_headless:
                opts.add_argument("--headless=new")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--window-size=1280,900")
            lang = (config.SELENIUM_CHROME_LANG or "en-US").strip()
            if lang:
                opts.add_argument(f"--lang={lang}")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_experimental_option("excludeSwitches", ["enable-automation"])
            opts.add_experimental_option("useAutomationExtension", False)
            if config.SELENIUM_CHROME_USER_DATA_DIR:
                opts.add_argument(f"--user-data-dir={config.SELENIUM_CHROME_USER_DATA_DIR}")
            if config.SELENIUM_CHROME_PROFILE_DIRECTORY:
                opts.add_argument(f"--profile-directory={config.SELENIUM_CHROME_PROFILE_DIRECTORY}")
            opts.add_experimental_option(
                "prefs",
                {
                    "download.default_directory": download_dir,
                    "download.prompt_for_download": False,
                    "download.directory_upgrade": True,
                    "safebrowsing.enabled": True,
                },
            )
            # Selenium 4.6+ ships Selenium Manager — matches installed Chrome without a stale cached driver.
            driver = webdriver.Chrome(options=opts)

        driver.set_page_load_timeout(120)
        _log(f"[IMDb] Loading {url}")
        driver.get(url)

        wait = WebDriverWait(driver, 25)
        wait.until(ec.presence_of_element_located((By.TAG_NAME, "body")))

        time.sleep(2)

        # Phase 1: Live watchlist list in the DOM (scoped). Matches the on-page list; avoids
        # stale IMDb export CSVs and random /title/ links elsewhere on the page.
        _imdb_scroll_watchlist_page(driver, _log)
        scoped_titles, scoped_items = _imdb_collect_scoped_watchlist(driver, _log)
        if scoped_titles:
            _log(f"[IMDb] Found {len(scoped_titles)} titles via scoped watchlist selectors")
            if config.IMDB_WATCHLIST_MOVIES_ONLY and config.IMDB_USE_EXPORT_FLOW:
                exported_mo = _imdb_try_export_csv(driver, download_dir, wait, _log)
                if exported_mo:
                    t_csv_mo, it_csv_mo = exported_mo
                    n_ty_csv = sum(1 for it in it_csv_mo if it.get("imdb_title_type"))
                    if it_csv_mo and n_ty_csv > 0:
                        _log("[IMDb] Using export CSV for movies-only (Title Type available)")
                        # #region agent log
                        _agent_dbg(
                            "A",
                            "scrape.py:_imdb_with_selenium",
                            "imdb_source_branch",
                            {
                                "branch": "export_csv",
                                "n_items": len(it_csv_mo),
                                "n_with_imdb_title_type": n_ty_csv,
                                "movies_only": config.IMDB_WATCHLIST_MOVIES_ONLY,
                            },
                        )
                        # #endregion
                        return ImdbResult(t_csv_mo, items=it_csv_mo, error=None)
                _log(
                    "[IMDb] movies-only: keeping scoped DOM "
                    "(export unavailable or CSV had no Title Type column)"
                )
            _log(f"[IMDb] Using {len(scoped_titles)} titles from live watchlist (scoped)")
            # #region agent log
            n_ty = sum(1 for it in scoped_items if it.get("imdb_title_type"))
            _agent_dbg(
                "A",
                "scrape.py:_imdb_with_selenium",
                "imdb_source_branch",
                {
                    "branch": "scoped_dom",
                    "n_items": len(scoped_items),
                    "n_with_imdb_title_type": n_ty,
                    "movies_only": config.IMDB_WATCHLIST_MOVIES_ONLY,
                },
            )
            # #endregion
            return ImdbResult(scoped_titles, items=scoped_items, error=None)

        # Phase 2: Export CSV (optional). Can lag behind removals until IMDb regenerates the file.
        if config.IMDB_USE_EXPORT_FLOW:
            driver.get(url)
            wait.until(ec.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(1)
            exported = _imdb_try_export_csv(driver, download_dir, wait, _log)
            if exported:
                t_csv, it_csv = exported
                # #region agent log
                n_ty = sum(1 for it in it_csv if it.get("imdb_title_type"))
                _agent_dbg(
                    "A",
                    "scrape.py:_imdb_with_selenium",
                    "imdb_source_branch",
                    {
                        "branch": "export_csv",
                        "n_items": len(it_csv),
                        "n_with_imdb_title_type": n_ty,
                        "movies_only": config.IMDB_WATCHLIST_MOVIES_ONLY,
                    },
                )
                # #endregion
                return ImdbResult(t_csv, items=it_csv, error=None)

        # Phase 3: Reload watchlist — export may have left us on /exports/. Unscoped fallback
        # if IMDb changes list markup and scoped selectors match nothing.
        _log("[IMDb] Scoped selectors found 0 titles; reloading watchlist for full-page fallback")
        driver.get(url)
        wait.until(ec.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)
        _imdb_scroll_watchlist_page(driver, _log)
        raw, raw_items = _imdb_collect_unscoped_page(driver, _log)
        if not raw:
            _imdb_dump_debug_page(driver, _log)
        # #region agent log
        n_ty = sum(1 for it in raw_items if it.get("imdb_title_type"))
        _agent_dbg(
            "A",
            "scrape.py:_imdb_with_selenium",
            "imdb_source_branch",
            {
                "branch": "unscoped_dom",
                "n_items": len(raw_items),
                "n_with_imdb_title_type": n_ty,
                "movies_only": config.IMDB_WATCHLIST_MOVIES_ONLY,
            },
        )
        # #endregion
        return ImdbResult(raw, items=raw_items, error=None)

    except Exception as e:
        # #region agent log
        _agent_dbg(
            "A",
            "scrape.py:_imdb_with_selenium",
            "imdb_source_branch",
            {"branch": "selenium_error", "error": str(e)[:200], "movies_only": config.IMDB_WATCHLIST_MOVIES_ONLY},
        )
        # #endregion
        return ImdbResult([], f"IMDb Selenium error: {e!s}")
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def get_imdb_titles_requests(url: str | None = None) -> tuple[list[str], str | None]:
    """Fallback: plain HTTP (often blocked or partial)."""
    url = url or config.IMDB_WATCHLIST_URL
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
    except requests.RequestException as e:
        return [], f"IMDb request failed: {e}"

    if response.status_code != 200:
        return [], f"IMDb HTTP {response.status_code}"

    html_lower = response.text.lower()
    if "verify that you're not a robot" in html_lower or "enable javascript" in html_lower:
        return [], "IMDb returned a bot-check page (use Selenium)."

    soup = BeautifulSoup(response.text, "html.parser")
    raw: list[str] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "/title/tt" not in href:
            continue
        text = a.get_text(" ", strip=True)
        if not text:
            continue
        cleaned = clean_imdb_title(text)
        norm = normalize_title(cleaned)
        if not norm:
            continue
        if norm in {"watchlist", "ratings", "reviews", "share", "more", "list", "lists"}:
            continue
        if norm in seen:
            continue
        seen.add(norm)
        raw.append(cleaned)

    return raw, None


def get_imdb_titles(
    url: str | None = None,
    use_selenium: bool = True,
    log: Callable[[str], None] | None = None,
) -> tuple[list[str], str | None]:
    url = url or config.IMDB_WATCHLIST_URL
    if use_selenium:
        r = _imdb_with_selenium(url, log)
        if r.error:
            return [], r.error
        if r.titles:
            return r.titles, None
        # Headless can get blocked by IMDb; auto-retry once with visible browser.
        if config.SELENIUM_HEADLESS and config.IMDB_ALLOW_VISIBLE_FALLBACK:
            if log:
                log("[IMDb] Headless returned 0 titles; retrying once in visible mode")
            retry = _imdb_with_selenium(url, log, headless_override=False)
            if retry.error:
                return [], retry.error
            if retry.titles:
                return retry.titles, None
        return [], "IMDb returned no titles (captcha/login/bot-check likely blocked this run)."

    return get_imdb_titles_requests(url)


def _omdb_imdb_id_to_title_type_label(imdb_id: str) -> str | None:
    """Map OMDb Type to a label that tokenizes like IMDb CSV Title Type (see imdb_title_type_is_tv)."""
    if not config.OMDB_API_KEY or not imdb_id or not str(imdb_id).strip().startswith("tt"):
        return None
    try:
        r = requests.get(
            "https://www.omdbapi.com/",
            params={"apikey": config.OMDB_API_KEY, "i": imdb_id.strip()},
            timeout=12,
        )
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
    t = (data.get("Type") or "").strip().lower()
    if t == "movie":
        return "movie"
    if t == "series":
        return "TV Series"
    if t == "episode":
        return "TV Episode"
    if t == "game":
        return "Video Game"
    return None


def backfill_imdb_title_types_from_omdb(
    imdb_items: list[dict],
    log: Callable[[str], None] | None = None,
) -> None:
    """
    When IMDB_WATCHLIST_MOVIES_ONLY is on, DOM-scraped items often have tt ids but no Title Type.
    OMDb (free key) fills imdb_title_type so merge_watchlists can drop IMDb-only TV.
    """
    if not config.IMDB_WATCHLIST_MOVIES_ONLY or not config.OMDB_API_KEY:
        return
    cache: dict[str, str | None] = {}
    filled = 0
    for item in imdb_items:
        iid = item.get("imdb_id")
        if not iid or not isinstance(iid, str):
            continue
        iid = iid.strip()
        if not iid.startswith("tt"):
            continue
        if item.get("imdb_title_type"):
            continue
        if iid not in cache:
            cache[iid] = _omdb_imdb_id_to_title_type_label(iid)
        label = cache[iid]
        if label:
            item["imdb_title_type"] = label
            filled += 1
    if log and cache:
        log(
            f"[IMDb] OMDb Title Type backfill: {len(cache)} tt id(s) looked up, "
            f"{filled} item(s) labeled (movies-only)"
        )
        if filled == 0:
            log(
                "[IMDb] OMDb returned no Title Types (often invalid/expired API key); "
                "TV rows cannot be filtered without types. Check OMDB_API_KEY at omdbapi.com."
            )


def get_imdb_items(
    url: str | None = None,
    use_selenium: bool = True,
    log: Callable[[str], None] | None = None,
) -> tuple[list[dict], str | None]:
    """
    Return IMDb items with title and optional imdb_id (tt...).
    """
    url = url or config.IMDB_WATCHLIST_URL
    if use_selenium:
        r = _imdb_with_selenium(url, log)
        if r.error:
            return [], r.error
        if r.items:
            return r.items, None
        if r.titles:
            return [{"title": t, "imdb_id": None} for t in r.titles], None
        if config.SELENIUM_HEADLESS and config.IMDB_ALLOW_VISIBLE_FALLBACK:
            if log:
                log("[IMDb] Headless returned 0 titles; retrying once in visible mode")
            retry = _imdb_with_selenium(url, log, headless_override=False)
            if retry.error:
                return [], retry.error
            if retry.items:
                return retry.items, None
            if retry.titles:
                return [{"title": t, "imdb_id": None} for t in retry.titles], None
        return [], "IMDb returned no titles (captcha/login/bot-check likely blocked this run)."

    titles, err = get_imdb_titles_requests(url)
    if err:
        return [], err
    return [{"title": t, "imdb_id": None} for t in titles], None


def merge_watchlists(
    letterboxd: list[str], imdb: list[str], imdb_items: list[dict] | None = None
) -> tuple[list[dict], dict[str, int]]:
    """Build combined rows with source flags."""
    lb_map: dict[str, str] = {}
    for t in letterboxd:
        n = normalize_title(t)
        if n and n not in lb_map:
            lb_map[n] = t

    im_map: dict[str, str] = {}
    im_id_map: dict[str, str | None] = {}
    im_type_map: dict[str, str | None] = {}
    if imdb_items:
        for item in imdb_items:
            t = (item.get("title") or "").strip()
            imdb_id = item.get("imdb_id")
            raw_it = item.get("imdb_title_type")
            ty_tok = _imdb_csv_title_type_token(raw_it) if isinstance(raw_it, str) else None
            n = normalize_title(t)
            if n and n not in im_map:
                im_map[n] = t
                im_id_map[n] = imdb_id
                im_type_map[n] = ty_tok
    else:
        for t in imdb:
            n = normalize_title(t)
            if n and n not in im_map:
                im_map[n] = t
                im_id_map[n] = None

    all_norms = sorted(
        set(lb_map.keys()) | set(im_map.keys()),
        key=lambda n: title_hints.article_insensitive_sort_tuple(lb_map.get(n) or im_map.get(n) or ""),
    )

    rows: list[dict] = []
    for norm in all_norms:
        on_lb = norm in lb_map
        on_im = norm in im_map
        display = lb_map.get(norm) or im_map.get(norm) or norm
        rows.append(
            {
                "display": display,
                "normalized": norm,
                "letterboxd": on_lb,
                "imdb": on_im,
                "letterboxd_title": lb_map.get(norm),
                "imdb_title": im_map.get(norm),
                "imdb_id": im_id_map.get(norm),
                "imdb_title_type": im_type_map.get(norm),
            }
        )

    # #region agent log
    def _interest(norm: str, disp: str) -> bool:
        s = f"{norm} {disp}".lower()
        return "ahsoka" in s or "borderland" in s

    interest_pre = [
        {
            "normalized": r["normalized"],
            "display": r["display"],
            "letterboxd": r["letterboxd"],
            "imdb": r["imdb"],
            "imdb_id": r.get("imdb_id"),
            "imdb_title_type": r.get("imdb_title_type"),
        }
        for r in rows
        if _interest(r["normalized"], r["display"])
    ]
    imdb_only_no_type = sum(
        1 for r in rows if r["imdb"] and not r["letterboxd"] and not r.get("imdb_title_type")
    )
    n_items_ty = (
        sum(1 for it in imdb_items if it.get("imdb_title_type")) if imdb_items else 0
    )
    _agent_dbg(
        "B",
        "scrape.py:merge_watchlists",
        "pre_movies_only_filter",
        {
            "IMDB_WATCHLIST_MOVIES_ONLY": config.IMDB_WATCHLIST_MOVIES_ONLY,
            "imdb_items_len": len(imdb_items or []),
            "imdb_items_with_title_type": n_items_ty,
            "imdb_only_rows_missing_type": imdb_only_no_type,
            "interest_rows": interest_pre,
        },
    )
    # #endregion

    if config.IMDB_WATCHLIST_MOVIES_ONLY:
        adjusted: list[dict] = []
        for row in rows:
            tyt = row.get("imdb_title_type")
            tv = imdb_title_type_is_tv(tyt if isinstance(tyt, str) else None)
            if tv and row["imdb"] and not row["letterboxd"]:
                continue
            if tv and row["imdb"] and row["letterboxd"]:
                row = dict(row)
                row["imdb"] = False
                row["imdb_title"] = None
                row["imdb_id"] = None
                row["imdb_title_type"] = None
            adjusted.append(row)
        rows = adjusted

    # #region agent log
    interest_post = [
        {
            "normalized": r["normalized"],
            "display": r["display"],
            "letterboxd": r["letterboxd"],
            "imdb": r["imdb"],
            "imdb_id": r.get("imdb_id"),
            "imdb_title_type": r.get("imdb_title_type"),
        }
        for r in rows
        if _interest(r["normalized"], r["display"])
    ]
    _agent_dbg(
        "B",
        "scrape.py:merge_watchlists",
        "post_movies_only_filter",
        {"interest_rows": interest_post, "total_rows": len(rows)},
    )
    # #endregion

    stats = {
        "letterboxd_only": sum(1 for r in rows if r["letterboxd"] and not r["imdb"]),
        "imdb_only": sum(1 for r in rows if r["imdb"] and not r["letterboxd"]),
        "both": sum(1 for r in rows if r["letterboxd"] and r["imdb"]),
        "total": len(rows),
    }
    return rows, stats
