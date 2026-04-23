"""
Backward-compatible re-exports for the refactored Gemini modules.
"""

# Re-export the enrichment symbols so older imports keep working.
from platform_agents.enrichment_agent import (
    CommentMatch,
    CommentMatchBatch,
    EnrichmentBatch,
    MessageEnrichment,
    enrich_records,
    filter_matching_records,
    match_search_agent,
    response_agent,
)
