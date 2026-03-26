"""Defaults match the watchlists from your notes; override with environment variables."""
import os


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    v = v.strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    if v in ("1", "true", "yes", "on"):
        return True
    return default


LETTERBOXD_WATCHLIST_URL = os.environ.get(
    "LETTERBOXD_WATCHLIST_URL",
    "https://letterboxd.com/miscalim/watchlist/",
)
LETTERBOXD_USERNAME_EXCLUDE = os.environ.get("LETTERBOXD_USERNAME_EXCLUDE", "miscalim")

IMDB_WATCHLIST_URL = os.environ.get(
    "IMDB_WATCHLIST_URL",
    "https://www.imdb.com/user/ur42352318/watchlist/",
)

# Selenium: "chrome" or "firefox"
SELENIUM_BROWSER = os.environ.get("SELENIUM_BROWSER", "chrome").lower()
# Default headless so the server can run without a visible window. Set SELENIUM_HEADLESS=0 for a visible browser.
SELENIUM_HEADLESS = _env_bool("SELENIUM_HEADLESS", True)
# If True, retry IMDb once with visible browser when headless gets zero titles.
IMDB_ALLOW_VISIBLE_FALLBACK = _env_bool("IMDB_ALLOW_VISIBLE_FALLBACK", False)
# Prefer IMDb CSV export flow before scroll scraping.
IMDB_USE_EXPORT_FLOW = _env_bool("IMDB_USE_EXPORT_FLOW", True)

# Background refresh: interval in minutes (0 = timer off; manual refresh still works).
AUTO_REFRESH_MINUTES = int(os.environ.get("AUTO_REFRESH_MINUTES", "360") or "0")
# Run one fetch shortly after startup (uses same lock as periodic refresh).
AUTO_REFRESH_ON_START = _env_bool("AUTO_REFRESH_ON_START", True)
AUTO_REFRESH_START_DELAY_SEC = int(os.environ.get("AUTO_REFRESH_START_DELAY_SEC", "15"))

_data_dir = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
CACHE_PATH = os.path.join(_data_dir, "cache.json")
POSTER_CACHE_PATH = os.path.join(_data_dir, "posters.json")
IMDB_ID_CACHE_PATH = os.path.join(_data_dir, "imdb_ids.json")


def _load_tmdb_api_key() -> str:
    """Letterboxd uses TMDB with their own key; this app needs yours. Env or one-line file."""
    k = os.environ.get("TMDB_API_KEY", "").strip()
    if k:
        return k
    key_path = os.environ.get(
        "TMDB_API_KEY_FILE",
        os.path.join(_data_dir, "tmdb_api_key.txt"),
    )
    if os.path.isfile(key_path):
        try:
            with open(key_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        return line
        except OSError:
            pass
    return ""


# Optional TMDB poster lookup — see https://www.themoviedb.org/settings/api
TMDB_API_KEY = _load_tmdb_api_key()
TMDB_IMAGE_BASE = os.environ.get("TMDB_IMAGE_BASE", "https://image.tmdb.org/t/p/w185")
POSTER_MAX_NETWORK_LOOKUPS = int(os.environ.get("POSTER_MAX_NETWORK_LOOKUPS", "120"))
