"""
Async orchestration entrypoints for Sentiment Analyzer.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from core.formatting import dedupe_records, format_records_for_html, platform_counts, sort_records
from core.platforms import FACEBOOK_PLATFORM, REDDIT_PLATFORM, SEARCH_ACTIVE_PLATFORMS, X_PLATFORM, platform_list_text
from core.records import serialize_records
from core.time_window import lookback_past_text
from platform_agents import facebook_agent, reddit_agent, x_agent
from platform_agents.enrichment_agent import enrich_records
from platform_agents.pdf_agent import generate_pdf_report


# Run one platform collector in a worker thread and surface any warning text.
async def _run_platform_search(
    platform_name: str,
    search_fn: object,
    keyword: str,
    warning_fn: object | None = None,
) -> tuple[str, list[dict], str | None]:
    try:
        records = await asyncio.to_thread(search_fn, keyword)
        warning = warning_fn() if callable(warning_fn) else None
        return platform_name, records, warning
    except Exception as exc:
        return platform_name, [], str(exc)


# Launch collectors for SEARCH_ACTIVE_PLATFORMS only (others are skipped, not removed).
async def _search_all_platforms_async(keyword: str) -> list[tuple[str, list[dict], str | None]]:
    tasks: list[object] = []
    if REDDIT_PLATFORM in SEARCH_ACTIVE_PLATFORMS:
        tasks.append(_run_platform_search(REDDIT_PLATFORM, reddit_agent.search_keyword, keyword))
    if X_PLATFORM in SEARCH_ACTIVE_PLATFORMS:
        tasks.append(_run_platform_search(X_PLATFORM, x_agent.search_keyword, keyword, x_agent.get_last_warning))
    if FACEBOOK_PLATFORM in SEARCH_ACTIVE_PLATFORMS:
        tasks.append(_run_platform_search(FACEBOOK_PLATFORM, facebook_agent.search_keyword, keyword))
    return list(await asyncio.gather(*tasks))


# Support async execution whether or not the caller is already inside an event loop.
def _run_async(coro: object) -> object:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(lambda: asyncio.run(coro))
        return future.result()


# Orchestrate collection, deduplication, enrichment, and status formatting for the UI.
def search_social_keyword(keyword: str) -> tuple[str, str, str, str, str]:
    clean_keyword = (keyword or "").strip()
    if not clean_keyword:
        return "Enter a keyword to search.", "", "", "", ""

    # Merge platform output before sending the combined record set to Gemini.
    all_records: list[dict] = []
    warnings: list[str] = []
    platform_results = _run_async(_search_all_platforms_async(clean_keyword))

    for platform_name, records, error in platform_results:
        all_records.extend(records)
        if error:
            warnings.append(f"{platform_name}: {error}")

    all_records = dedupe_records(all_records)
    all_records = sort_records(all_records)

    # Enrich the merged records in one pass so the UI and PDF share identical metadata.
    try:
        enriched = enrich_records(all_records)
    except Exception as exc:
        warnings.append(f"Gemini enrichment: {exc}")
        enriched = all_records

    if not enriched:
        warning_text = f" Warnings: {'; '.join(warnings)}" if warnings else ""
        return (
            f"No {platform_list_text()} posts/comments found for '{clean_keyword}' in the {lookback_past_text()}.{warning_text}",
            "",
            "",
            clean_keyword,
            "[]",
        )

    # Report a compact cross-platform summary back to the Gradio frontend.
    counts = platform_counts(enriched)
    count_parts = [f"{p}: {counts.get(p, 0)}" for p in SEARCH_ACTIVE_PLATFORMS]
    status = f"Found {len(enriched)} matches for '{clean_keyword}' ({', '.join(count_parts)})."
    if warnings:
        status += " Warnings: " + "; ".join(warnings)
    return status, format_records_for_html(enriched, clean_keyword), "", clean_keyword, serialize_records(enriched)
