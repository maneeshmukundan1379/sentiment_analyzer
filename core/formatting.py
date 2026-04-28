"""
Formatting helpers for UI and sorting.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from html import escape

from core.platforms import PLATFORM_LINK_LABELS, PLATFORM_ORDER, platform_list_text
from core.time_window import lookback_past_text


# Render timestamps consistently for both the UI and the PDF layer.
def format_timestamp(created_utc: float) -> str:
    if not created_utc or created_utc <= 0:
        return "N/A"
    return datetime.fromtimestamp(created_utc, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# Pick the right source-link label for each platform block.
def link_label(platform: str) -> str:
    return PLATFORM_LINK_LABELS.get(platform, "Source Link")


# Normalize sentiment labels so the UI and PDF use the same categories.
def normalize_sentiment(value: object) -> str:
    sentiment = str(value or "Unknown").strip().title()
    return sentiment if sentiment in {"Positive", "Negative", "Neutral", "Mixed"} else "Unknown"


# Convert sentiment to semantic colors used by the Gradio HTML results.
def sentiment_colors(value: object) -> tuple[str, str, str]:
    palette = {
        "Positive": ("#166534", "#dcfce7", "#22c55e"),
        "Negative": ("#991b1b", "#fee2e2", "#ef4444"),
        "Neutral": ("#334155", "#f1f5f9", "#94a3b8"),
        "Mixed": ("#92400e", "#fef3c7", "#f59e0b"),
        "Unknown": ("#3730a3", "#e0e7ff", "#6366f1"),
    }
    return palette[normalize_sentiment(value)]


# Convert normalized records into the multiline textbox format shown in Gradio.
def format_records_for_textbox(records: list[dict], keyword: str) -> str:
    if not records:
        return f"No {platform_list_text()} posts/comments found for '{keyword}' in the {lookback_past_text()}."

    blocks: list[str] = []
    for record in records:
        platform = str(record.get("platform") or "Unknown")
        blocks.append(
            "\n".join(
                [
                    f"Platform: {platform}",
                    f"User ID: {record.get('user_id', 'Unknown')}",
                    f"Location: {record.get('location', 'N/A')}",
                    f"Subject: {record.get('subject', '') or 'N/A'}",
                    f"Comment: {record['text']}",
                    f"Sentiment: {record.get('sentiment', 'Unknown')}",
                    f"Date: {format_timestamp(float(record.get('created_utc') or 0))}",
                    f"{link_label(platform)}: {record.get('permalink', '')}",
                ]
            )
        )
    return "\n\n".join(blocks)


# Render normalized records as sentiment-coded HTML cards for the Gradio app.
def format_records_for_html(records: list[dict], keyword: str) -> str:
    if not records:
        return (
            '<div class="empty-results">'
            f"No {escape(platform_list_text())} posts/comments found for "
            f"'{escape(keyword)}' in the {escape(lookback_past_text())}."
            "</div>"
        )

    cards: list[str] = []
    for record in records:
        platform = str(record.get("platform") or "Unknown")
        sentiment = normalize_sentiment(record.get("sentiment"))
        text_color, bg_color, border_color = sentiment_colors(sentiment)
        source_url = str(record.get("permalink") or "")
        link = (
            f'<a href="{escape(source_url)}" target="_blank" rel="noopener noreferrer">'
            f"{escape(link_label(platform))}</a>"
            if source_url
            else ""
        )
        cards.append(
            "\n".join(
                [
                    f'<article class="result-card" style="border-left-color:{border_color};">',
                    '<div class="result-card__topline">',
                    f"<strong>{escape(platform)}</strong>",
                    f'<span class="sentiment-pill" style="color:{text_color};background:{bg_color};border-color:{border_color};">{escape(sentiment)}</span>',
                    "</div>",
                    f'<div class="result-card__meta">{escape(str(record.get("kind") or "match").title())} | {escape(format_timestamp(float(record.get("created_utc") or 0)))}</div>',
                    f'<h3>{escape(record.get("subject", "") or "N/A")}</h3>',
                    f'<p class="result-card__text">{escape(record.get("text", ""))}</p>',
                    '<div class="result-card__details">',
                    f"<span>User: {escape(str(record.get('user_id', 'Unknown')))}</span>",
                    f"<span>Location: {escape(str(record.get('location', 'N/A')))}</span>",
                    link,
                    "</div>",
                    "</article>",
                ]
            )
        )
    return '<section class="results-grid">' + "\n".join(cards) + "</section>"


# Remove duplicate records while preserving the first occurrence of each id.
def dedupe_records(records: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen_ids: set[str] = set()
    for record in records:
        message_id = str(record.get("message_id") or "")
        if not message_id or message_id in seen_ids:
            continue
        deduped.append(record)
        seen_ids.add(message_id)
    return deduped


# Order records by recency first, then by platform and stable id.
def sort_records(records: list[dict]) -> list[dict]:
    platform_rank = {platform: index for index, platform in enumerate(PLATFORM_ORDER)}
    return sorted(
        records,
        key=lambda item: (
            -float(item.get("created_utc") or 0),
            platform_rank.get(str(item.get("platform") or ""), len(platform_rank)),
            str(item.get("message_id") or ""),
        ),
    )


# Summarize how many normalized records came from each platform.
def platform_counts(records: list[dict]) -> Counter:
    return Counter(str(record.get("platform") or "Unknown") for record in records)
