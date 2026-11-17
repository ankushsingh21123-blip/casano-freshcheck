"""Configuration for casano-freshcheck backend.

Reads only environment variables (and an optional local ``.env`` file).
The Tavily API key is never logged or returned by any endpoint.
"""

from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
TAVILY_API_URL = "https://api.tavily.com/search"
TAVILY_TIMEOUT_SECONDS = 20.0
TAVILY_MAX_RESULTS = 5


def _load_dotenv() -> None:
    """Load ``backend/.env`` into os.environ without overwriting real env vars.

    Minimal parser on purpose: no extra dependency, no shell expansion.
    Lines starting with ``#`` and blank lines are ignored.
    """
    env_path = BACKEND_DIR / ".env"
    if not env_path.exists():
        return
    try:
        text = env_path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


def get_tavily_api_key() -> str | None:
    """Return the Tavily API key if set, else None. Never log the value."""
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    return key or None


def get_mode() -> str:
    """'live' when a Tavily key is configured, otherwise 'offline'."""
    return "live" if get_tavily_api_key() else "offline"


def get_db_path() -> Path:
    """SQLite file path. ``FRESHCHECK_DB_PATH`` overrides the default.

    The override exists so tests can use a temporary database.
    """
    override = os.environ.get("FRESHCHECK_DB_PATH", "").strip()
    if override:
        return Path(override)
    return BACKEND_DIR / "data" / "freshcheck.db"


def get_cors_origins() -> list[str]:
    """Allowed CORS origins. Localhost-only by default.

    Override with ``CORS_ORIGINS`` as a comma-separated list.
    """
    raw = os.environ.get("CORS_ORIGINS", "").strip()
    if raw:
        return [origin.strip() for origin in raw.split(",") if origin.strip()]
    return ["http://localhost:3000", "http://127.0.0.1:3000"]
