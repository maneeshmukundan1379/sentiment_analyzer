"""
Shared time-window helpers.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.config import LOOKBACK_DAYS


# Normalize the configured lookback into a valid positive day count.
def lookback_days() -> int:
    return max(1, int(LOOKBACK_DAYS))


# Format the configured lookback window for user-facing copy.
def lookback_days_text() -> str:
    days = lookback_days()
    unit = "day" if days == 1 else "days"
    return f"{days} {unit}"


# Phrase the lookback window for prompts like "last 7 days".
def lookback_last_text() -> str:
    return f"last {lookback_days_text()}"


# Phrase the lookback window for empty-state UI text.
def lookback_past_text() -> str:
    return f"past {lookback_days_text()}"


# Reuse a single timedelta across collectors that filter by recency.
def lookback_timedelta() -> timedelta:
    return timedelta(days=lookback_days())


# Compute the UTC cutoff timestamp used to filter social records.
def cutoff_utc_timestamp() -> float:
    return (datetime.now(timezone.utc) - lookback_timedelta()).timestamp()


# Translate the shared lookback window into Reddit's native time filter values.
def reddit_time_filter() -> str:
    days = lookback_days()
    if days <= 1:
        return "day"
    if days <= 7:
        return "week"
    if days <= 31:
        return "month"
    if days <= 365:
        return "year"
    return "all"


# Translate the shared lookback window into search-provider-specific filters.
def search_time_filter() -> tuple[str | None, str | None]:
    days = lookback_days()
    if days <= 1:
        return "qdr:d", "d"
    if days <= 7:
        return "qdr:w", "w"
    if days <= 31:
        return "qdr:m", "m"
    if days <= 365:
        return "qdr:y", "y"
    return None, None
