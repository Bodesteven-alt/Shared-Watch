"""Defaults match the watchlists from your notes; override with environment variables."""
import json
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
# CSV export can lag behind the live watchlist (IMDb regenerates files asynchronously).
# Live DOM (scoped list rows) is tried first; enable export only as fallback when needed.
IMDB_USE_EXPORT_FLOW = _env_bool("IMDB_USE_EXPORT_FLOW", False)

# Background refresh: interval in minutes (0 = timer off; manual refresh still works).
AUTO_REFRESH_MINUTES = int(os.environ.get("AUTO_REFRESH_MINUTES", "360") or "0")
# Run one fetch shortly after startup (uses same lock as periodic refresh).
AUTO_REFRESH_ON_START = _env_bool("AUTO_REFRESH_ON_START", True)
AUTO_REFRESH_START_DELAY_SEC = int(os.environ.get("AUTO_REFRESH_START_DELAY_SEC", "15"))

_data_dir = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
CACHE_PATH = os.path.join(_data_dir, "cache.json")
POSTER_CACHE_PATH = os.path.join(_data_dir, "posters.json")
IMDB_ID_CACHE_PATH = os.path.join(_data_dir, "imdb_ids.json")
TMDB_WATCH_PROVIDERS_CACHE_PATH = os.path.join(
    _data_dir,
    os.environ.get("TMDB_WATCH_PROVIDERS_CACHE_FILE", "tmdb_watch_providers_cache.json"),
)
OWNED_STREAMING_SERVICES_PATH = os.path.join(
    _data_dir,
    os.environ.get("OWNED_STREAMING_SERVICES_FILE", "owned_streaming_services.json"),
)
# Max TMDb watch-provider API calls per refresh (remaining rows reuse disk cache only).
STREAMING_MAX_NETWORK_LOOKUPS = int(os.environ.get("STREAMING_MAX_NETWORK_LOOKUPS", "200") or "200")
# Drop cache entries older than this many days (0 = never expire by age).
STREAMING_CACHE_MAX_AGE_DAYS = int(os.environ.get("STREAMING_CACHE_MAX_AGE_DAYS", "14") or "0")


def _load_tmdb_api_key() -> str:
    """TMDb v3 API key: TMDB_API_KEY env or gitignored one-line file."""
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


def _load_tmdb_read_access_token() -> str:
    """TMDb API Read Access Token (JWT): Bearer auth for v3. Env or gitignored one-line file."""
    t = os.environ.get("TMDB_READ_ACCESS_TOKEN", "").strip()
    if t:
        return t
    token_path = os.environ.get(
        "TMDB_READ_ACCESS_TOKEN_FILE",
        os.path.join(_data_dir, "tmdb_read_access_token.txt"),
    )
    if os.path.isfile(token_path):
        try:
            with open(token_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        return line
        except OSError:
            pass
    return ""


# Optional TMDb — see https://www.themoviedb.org/settings/api
TMDB_API_KEY = _load_tmdb_api_key()
TMDB_READ_ACCESS_TOKEN = _load_tmdb_read_access_token()
TMDB_API_CONFIGURED = bool(TMDB_READ_ACCESS_TOKEN or TMDB_API_KEY)
TMDB_IMAGE_BASE = os.environ.get("TMDB_IMAGE_BASE", "https://image.tmdb.org/t/p/w185")

# Optional footer link (e.g. https://github.com/you/repo). Empty = hide GitHub line.
SITE_GITHUB_URL = (os.environ.get("SITE_GITHUB_URL") or "").strip()


def _load_omdb_api_key() -> str:
    k = os.environ.get("OMDB_API_KEY", "").strip()
    if k:
        return k
    key_path = os.path.join(_data_dir, "omdb_api_key.txt")
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


OMDB_API_KEY = _load_omdb_api_key()
# Enough for full watchlist in one refresh (Letterboxd-only rows retry after cache misses).
POSTER_MAX_NETWORK_LOOKUPS = int(os.environ.get("POSTER_MAX_NETWORK_LOOKUPS", "400") or "400")


def load_owned_streaming_profile() -> dict:
    """
    Local streaming profile: region (e.g. US) and providers you subscribe to.
    TMDb provider_id is stable; optional label is for UI only.

    Override with STREAMING_OWNED_PROVIDER_IDS=8,15 and optional STREAMING_REGION=US
    """
    region = (os.environ.get("STREAMING_REGION") or "US").strip().upper() or "US"
    raw_ids = (os.environ.get("STREAMING_OWNED_PROVIDER_IDS") or "").strip()
    if raw_ids:
        providers: list[dict] = []
        for part in raw_ids.split(","):
            part = part.strip()
            if part.isdigit():
                pid = int(part)
                providers.append({"id": pid, "label": part})
        return {"region": region, "providers": providers}

    path = os.environ.get("OWNED_STREAMING_PATH", OWNED_STREAMING_SERVICES_PATH)
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return {"region": region, "providers": []}
        if isinstance(data, dict):
            r = (data.get("region") or region or "US").strip().upper()
            out: list[dict] = []
            for p in data.get("providers") or []:
                if not isinstance(p, dict):
                    continue
                pid = p.get("id")
                if pid is None:
                    continue
                try:
                    pid_int = int(pid)
                except (TypeError, ValueError):
                    continue
                label = (p.get("label") or str(pid_int)).strip()
                out.append({"id": pid_int, "label": label})
            return {"region": r, "providers": out}
    return {"region": region, "providers": []}
