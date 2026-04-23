"""
Centralized environment loading for Sentiment Analyzer.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None

# Resolve the app root once so env discovery can walk upward consistently.
APP_ROOT = Path(__file__).resolve().parents[1]


# Build the ordered list of candidate .env files to load.
def _env_candidates() -> list[Path]:
    candidates: list[Path] = []
    explicit_path = (os.getenv("SENTIMENT_ANALYZER_ENV_FILE") or "").strip()
    if explicit_path:
        candidates.append(Path(explicit_path).expanduser())

    current = APP_ROOT
    while True:
        candidates.append(current / ".env")
        if current == current.parent:
            break
        current = current.parent
    return candidates


# Load each discovered .env file once without overriding existing process values.
def load_app_env() -> list[Path]:
    if load_dotenv is None:
        return []

    loaded_paths: list[Path] = []
    seen_paths: set[Path] = set()
    for candidate in _env_candidates():
        if not candidate.exists():
            continue
        resolved = candidate.resolve()
        if resolved in seen_paths:
            continue
        load_dotenv(dotenv_path=resolved, override=False)
        loaded_paths.append(resolved)
        seen_paths.add(resolved)
    return loaded_paths
