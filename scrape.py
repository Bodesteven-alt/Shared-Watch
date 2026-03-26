"""Fetch watchlist titles from Letterboxd (HTTP) and IMDb (browser)."""
from __future__ import annotations

import csv
import glob
import os
import re
import tempfile
import time
from dataclasses import dataclass
from typing import Callable

import requests
from bs4 import BeautifulSoup

import config

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


def _parse_imdb_csv(path: str) -> tuple[list[str], list[dict]]:
    titles: list[str] = []
    items: list[dict] = []
    seen: set[str] = set()
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = (row.get("Title") or row.get("title") or "").strip()
            imdb_id = (row.get("Const") or row.get("const") or "").strip()
            if not title:
                continue
            norm = normalize_title(title)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            titles.append(title)
            items.append({"title": title, "imdb_id": imdb_id or None})
    return titles, items


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

        if config.IMDB_USE_EXPORT_FLOW:
            _log("[IMDb] Trying export CSV flow")
            try:
                # Click Export from watchlist page.
                export_button = wait.until(
                    ec.element_to_be_clickable(
                        (
                            By.XPATH,
                            "//button[contains(., 'Export')] | //a[contains(., 'Export')]",
                        )
                    )
                )
                export_button.click()
                time.sleep(1.5)
                driver.get("https://www.imdb.com/exports/")

                deadline = time.time() + 45
                csv_path = ""
                while time.time() < deadline:
                    files = sorted(glob.glob(os.path.join(download_dir, "*.csv")), key=os.path.getmtime, reverse=True)
                    if files:
                        csv_path = files[0]
                        break
                    # Some accounts expose an explicit download link before file appears locally.
                    links = driver.find_elements(By.CSS_SELECTOR, 'a[href$=".csv"], a[href*=".csv?"]')
                    if links:
                        try:
                            links[0].click()
                        except Exception:
                            pass
                    time.sleep(2)

                if csv_path:
                    titles, items = _parse_imdb_csv(csv_path)
                    _log(f"[IMDb] Parsed {len(titles)} titles from IMDb export CSV")
                    if titles:
                        return ImdbResult(titles, items=items, error=None)
            except Exception as export_err:
                _log(f"[IMDb] Export flow not available this run: {export_err!s}")

        time.sleep(2)

        last_count = 0
        stable_rounds = 0
        max_rounds = 45

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
            # Bail early once count is clearly large and stable enough.
            if count >= 180 and stable_rounds >= 2:
                break

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

        for a in driver.find_elements(By.CSS_SELECTOR, 'a[href*="/title/tt"]'):
            href = a.get_attribute("href") or ""
            if "/title/tt" not in href:
                continue
            text = a.text.strip()
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
            imdb_id = ""
            m = re.search(r"/title/(tt\d+)", href)
            if m:
                imdb_id = m.group(1)
            raw_items.append({"title": cleaned, "imdb_id": imdb_id or None})

        _log(f"[IMDb] Collected {len(raw)} titles after scrolling")
        return ImdbResult(raw, items=raw_items, error=None)

    except Exception as e:
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
    if imdb_items:
        for item in imdb_items:
            t = (item.get("title") or "").strip()
            imdb_id = item.get("imdb_id")
            n = normalize_title(t)
            if n and n not in im_map:
                im_map[n] = t
                im_id_map[n] = imdb_id
    else:
        for t in imdb:
            n = normalize_title(t)
            if n and n not in im_map:
                im_map[n] = t
                im_id_map[n] = None

    all_norms = sorted(
        set(lb_map.keys()) | set(im_map.keys()),
        key=lambda n: (lb_map.get(n) or im_map.get(n) or "").lower(),
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
            }
        )

    stats = {
        "letterboxd_only": sum(1 for r in rows if r["letterboxd"] and not r["imdb"]),
        "imdb_only": sum(1 for r in rows if r["imdb"] and not r["letterboxd"]),
        "both": sum(1 for r in rows if r["letterboxd"] and r["imdb"]),
        "total": len(rows),
    }
    return rows, stats
