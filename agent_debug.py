"""Session debug NDJSON logger (no secrets)."""
from __future__ import annotations

import json
import os
import time

_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug-b2ee4b.log")
_SESSION = "b2ee4b"


def log(*, hypothesis_id: str, location: str, message: str, data: dict | None = None) -> None:
    payload = {
        "sessionId": _SESSION,
        "timestamp": int(time.time() * 1000),
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data or {},
    }
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass
