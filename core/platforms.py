"""
Centralized platform labels and ordering.
"""

from __future__ import annotations

# Keep the canonical platform labels and display order in one place.
REDDIT_PLATFORM = "Reddit"
FACEBOOK_PLATFORM = "Facebook"
X_PLATFORM = "X.com"
FACEBOOK_SCOPE_LABEL = "Facebook pages and groups"

PLATFORM_ORDER = [REDDIT_PLATFORM, FACEBOOK_PLATFORM, X_PLATFORM]
PLATFORM_LINK_LABELS = {
    REDDIT_PLATFORM: "Reddit Link",
    FACEBOOK_PLATFORM: "Facebook Link",
    X_PLATFORM: "X.com Link",
}


# Build human-readable platform lists for UI and prompt text.
def platform_list_text() -> str:
    return f"{REDDIT_PLATFORM}, {FACEBOOK_PLATFORM}, and {X_PLATFORM}"


# Describe the broader Facebook scope used in prompts and status text.
def platform_scope_text() -> str:
    return f"{REDDIT_PLATFORM}, {X_PLATFORM}, and {FACEBOOK_SCOPE_LABEL}"
