"""
Configuration helpers for Sentiment Analyzer.
"""

from __future__ import annotations

import os

from core.env import load_app_env

# Load environment variables before computing module-level settings.
load_app_env()

# Parse integer environment values while falling back safely on bad input.
def safe_int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Accept only positive integer overrides for optional limits.
def optional_positive_int_env(name: str) -> int | None:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


# Expose the effective app configuration as module-level constants.
LOOKBACK_DAYS = safe_int_env("SOCIAL_LOOKBACK_DAYS", 7)
FACEBOOK_GROUP_PAGES_LIMIT = optional_positive_int_env("FACEBOOK_GROUP_PAGES")
REDDIT_CLIENT_ID = (os.getenv("REDDIT_CLIENT_ID") or "").strip()
REDDIT_CLIENT_SECRET = (os.getenv("REDDIT_CLIENT_SECRET") or "").strip()
REDDIT_USER_AGENT = (
    os.getenv("REDDIT_USER_AGENT")
    or "script:sentiment-analyzer:1.0.0 (by /u/your_reddit_username)"
).strip()
X_API_BASE_URL = (os.getenv("X_API_BASE_URL") or "https://api.x.com/2").strip().rstrip("/")
X_BEARER_TOKEN = (os.getenv("X_BEARER_TOKEN") or "").strip()
