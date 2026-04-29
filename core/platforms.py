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

# Platforms whose collectors run during search. Facebook and X agents remain in the codebase;
# omit them here to skip execution. To re-enable, add FACEBOOK_PLATFORM and/or X_PLATFORM.
SEARCH_ACTIVE_PLATFORMS: tuple[str, ...] = (REDDIT_PLATFORM,)


def _oxford_join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


# Build human-readable platform lists for UI and prompt text.
def platform_list_text() -> str:
    return _oxford_join(list(SEARCH_ACTIVE_PLATFORMS))


# Describe the broader Facebook scope used in prompts and status text.
def platform_scope_text() -> str:
    labels: list[str] = []
    for platform in SEARCH_ACTIVE_PLATFORMS:
        if platform == FACEBOOK_PLATFORM:
            labels.append(FACEBOOK_SCOPE_LABEL)
        else:
            labels.append(platform)
    return _oxford_join(labels)
