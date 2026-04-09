"""Print whether TMDb credentials are visible for streaming enrichment (no secrets printed)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config  # noqa: E402


def main() -> int:
    root = Path(config.__file__).resolve().parent
    data_dir = Path(config.CACHE_PATH).parent
    env_path = root / ".env"
    key_path = data_dir / "tmdb_api_key.txt"
    token_path = data_dir / "tmdb_read_access_token.txt"

    try:
        import dotenv  # noqa: F401
    except ImportError:
        dotenv_ok = False
    else:
        dotenv_ok = True

    print("TMDb (watch providers)")
    print(f"  TMDB_API_CONFIGURED: {config.TMDB_API_CONFIGURED}")
    print(f"  token from env/file (set): {bool((config.TMDB_READ_ACCESS_TOKEN or '').strip())}")
    print(f"  api key from env/file (set): {bool((config.TMDB_API_KEY or '').strip())}")
    print(f"  python-dotenv installed: {dotenv_ok}")
    print(f"  project .env file exists: {env_path.is_file()} ({env_path})")
    print(f"  {key_path.name} exists: {key_path.is_file()}")
    print(f"  {token_path.name} exists: {token_path.is_file()}")
    print(f"  DATA_DIR (cache parent): {data_dir}")

    if not config.TMDB_API_CONFIGURED:
        print()
        print(
            "Streaming will stay empty until at least one of: TMDB_READ_ACCESS_TOKEN, TMDB_API_KEY "
            "(env), or one-line files in data/ as above. Add python-dotenv and a project .env if "
            "your scheduler does not inherit user environment variables."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
