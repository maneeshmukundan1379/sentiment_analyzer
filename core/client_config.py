"""
Client report configuration helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from core.platforms import FACEBOOK_PLATFORM, REDDIT_PLATFORM, X_PLATFORM


PLATFORM_CONFIG_KEYS = {
    "reddit": REDDIT_PLATFORM,
    "x": X_PLATFORM,
    "twitter": X_PLATFORM,
    "facebook": FACEBOOK_PLATFORM,
}


@dataclass(frozen=True)
class KeywordRules:
    any: tuple[str, ...]
    all: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClientReportConfig:
    name: str
    keywords: KeywordRules
    platforms: tuple[str, ...]
    schedule: str = "weekly"


def _clean_terms(values: object) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(str(item).strip() for item in values if str(item).strip())


def _parse_keywords(raw: object) -> KeywordRules:
    if isinstance(raw, list):
        return KeywordRules(any=_clean_terms(raw))
    if not isinstance(raw, dict):
        return KeywordRules(any=())
    return KeywordRules(
        any=_clean_terms(raw.get("any")),
        all=_clean_terms(raw.get("all")),
        exclude=_clean_terms(raw.get("exclude")),
    )


def _parse_platforms(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, dict):
        return (REDDIT_PLATFORM,)

    platforms: list[str] = []
    for key, platform in PLATFORM_CONFIG_KEYS.items():
        if raw.get(key) is True and platform not in platforms:
            platforms.append(platform)
    return tuple(platforms) or (REDDIT_PLATFORM,)


def load_client_report_configs(path: str | Path) -> list[ClientReportConfig]:
    client_path = Path(path).expanduser()
    payload = json.loads(client_path.read_text(encoding="utf-8"))
    configs: list[ClientReportConfig] = []

    for index, item in enumerate(payload.get("clients", []), start=1):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or f"Client {index}").strip()
        keywords = _parse_keywords(item.get("keywords"))
        if not keywords.any:
            continue
        configs.append(
            ClientReportConfig(
                name=name,
                keywords=keywords,
                platforms=_parse_platforms(item.get("sources")),
                schedule=str(item.get("schedule") or "weekly").strip() or "weekly",
            )
        )

    return configs
