"""
Gemini relevance filtering and enrichment for merged social records.
"""

from __future__ import annotations

from typing import Iterable

from agents import Agent
from pydantic import BaseModel, Field

from core.platforms import platform_scope_text
from core.time_window import lookback_last_text
from platform_agents.base_agent import create_gemini_model, run_agent


# Define the schema Gemini uses when enriching each matched social record.
class MessageEnrichment(BaseModel):
    id: str = Field(..., description="Original social message id")
    sentiment: str = Field(..., description="Positive, Negative, Neutral, or Mixed")
    location: str = Field(..., description="Detected location or N/A")
    response: str = Field(..., description="A short suggested reply tailored to the message sentiment")


class EnrichmentBatch(BaseModel):
    items: list[MessageEnrichment]


# Define the schema Gemini uses when deciding whether a candidate record should stay.
class CommentMatch(BaseModel):
    id: str = Field(..., description="Original social message id")
    keep: bool = Field(..., description="Whether the message should be kept for the final result set")


class CommentMatchBatch(BaseModel):
    items: list[CommentMatch]


# Configure the agent that filters weak or irrelevant keyword matches.
match_search_agent = Agent(
    name="Social Match Search Agent",
    instructions=(
        f"You review {platform_scope_text()} posts/comments that were collected from the {lookback_last_text()} "
        "or from public search results. For each item, keep the same id and return keep=true only when the record "
        "is genuinely about the requested keyword or clearly uses that keyword in a meaningful way. Return keep=false "
        "for spam, off-topic mentions, profile-only matches, or weak keyword matches."
    ),
    model=create_gemini_model(),
    output_type=CommentMatchBatch,
)


# Configure the agent that adds sentiment, location, and reply suggestions.
response_agent = Agent(
    name="Social Sentiment Response Agent",
    instructions=(
        f"You analyze {platform_scope_text()} posts/comments and extract structured metadata. "
        "Return only valid data matching the schema. For each item, keep the same id, assign location only when "
        "clearly present from the location hint or text, otherwise N/A, assign sentiment as one of Positive, "
        "Negative, Neutral, or Mixed, and write a short suggested response that fits the message sentiment: "
        "empathetic and calming for Negative, upbeat for Positive, balanced for Mixed, and factual/helpful for "
        "Neutral. Keep the response under 45 words, avoid insults or escalation, and do not claim facts not present "
        "in the text."
    ),
    model=create_gemini_model(),
    output_type=EnrichmentBatch,
)


# Split large payloads into smaller batches that fit comfortably in one prompt.
def chunked(items: list[dict], size: int) -> Iterable[list[dict]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


# Ask Gemini which collected records are actually about the requested keyword.
def filter_matching_records(records: list[dict], keyword: str) -> list[dict]:
    if not records:
        return records

    decisions: dict[str, bool] = {}
    payload_rows = [
        {
            "id": record["message_id"],
            "platform": record.get("platform", ""),
            "kind": record.get("kind", ""),
            "subject": record.get("subject", "")[:300],
            "text": record["text"][:1200],
            "community": record.get("community", ""),
        }
        for record in records
    ]

    for batch in chunked(payload_rows, 8):
        user_prompt = (
            f"Keyword: {keyword}\n"
            "For each social record below, return an object with keys id and keep.\n\n"
            f"{batch}"
        )
        try:
            batch_output = run_agent(match_search_agent, user_prompt, CommentMatchBatch)
        except Exception:
            for row in batch:
                decisions[row["id"]] = True
            continue
        for item in batch_output.items:
            decisions[item.id] = bool(item.keep)

    return [record for record in records if decisions.get(record["message_id"], True)]


# Ask Gemini to enrich the final record set with additional structured metadata.
def enrich_records(records: list[dict]) -> list[dict]:
    if not records:
        return records

    enriched: dict[str, dict] = {}
    payload_rows = [
        {
            "id": record["message_id"],
            "platform": record.get("platform", ""),
            "kind": record.get("kind", ""),
            "subject": record.get("subject", "")[:300],
            "text": record["text"][:1200],
            "location_hint": record.get("location_hint", ""),
            "community": record.get("community", ""),
        }
        for record in records
    ]

    for batch in chunked(payload_rows, 8):
        user_prompt = (
            "For each social record below, return an object with keys id, sentiment, location, and response.\n"
            "The response should be a short suggested reply based on the record sentiment.\n\n"
            f"{batch}"
        )
        try:
            batch_output = run_agent(response_agent, user_prompt, EnrichmentBatch)
        except Exception:
            for row in batch:
                enriched[row["id"]] = {
                    "sentiment": "Unknown",
                    "location": "N/A",
                    "response": "Suggested response unavailable right now because the Gemini model is temporarily busy.",
                }
            continue
        for item in batch_output.items:
            enriched[item.id] = {
                "sentiment": (item.sentiment or "Unknown").strip() or "Unknown",
                "location": (item.location or "N/A").strip() or "N/A",
                "response": (item.response or "").strip(),
            }

    for record in records:
        item = enriched.get(record["message_id"], {})
        record["sentiment"] = item.get("sentiment", "Unknown")
        record["location"] = item.get("location", "N/A")
        record["response"] = item.get("response", "")
    return records
