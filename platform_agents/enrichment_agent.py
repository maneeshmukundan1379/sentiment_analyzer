"""
Gemini relevance filtering and enrichment for merged social records.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from agents import Agent
from pydantic import BaseModel, Field

from core.platforms import REDDIT_PLATFORM, platform_scope_text
from core.time_window import lookback_last_text
from platform_agents.base_agent import create_gemini_model, run_agent


# Define the schema Gemini uses when enriching each matched social record.
class MessageEnrichment(BaseModel):
    id: str = Field(..., description="Original social message id")
    sentiment: str = Field(..., description="Positive, Negative, Neutral, or Mixed")
    location: str = Field(..., description="Detected location or N/A")
    response: str = Field(
        ...,
        description=(
            "A short public reply written in the voice of a real pharmacy team (pharmacist or staff): warm, "
            "professional, and specific to what the poster said—not generic platitudes"
        ),
    )


class EnrichmentBatch(BaseModel):
    items: list[MessageEnrichment]


# Define the schema Gemini uses when deciding whether a candidate record should stay.
class CommentMatch(BaseModel):
    id: str = Field(..., description="Original social message id")
    keep: bool = Field(..., description="Whether the message should be kept for the final result set")


class CommentMatchBatch(BaseModel):
    items: list[CommentMatch]


class PdfRedditExcerptAssignment(BaseModel):
    excerpt_index: int = Field(
        ...,
        ge=0,
        description="Line number from the numbered Reddit list: use 1..N, or 0..N-1 if zero-based.",
    )
    primary_theme: str = Field(
        ...,
        description=(
            "Exactly ONE short substantive label (2-6 words) for this Reddit post or comment—the best single theme. "
            "Use the same wording when the same topic appears on other lines."
        ),
    )


class PdfRedditThemeResult(BaseModel):
    assignments: list[PdfRedditExcerptAssignment] = Field(
        default_factory=list,
        description="One assignment per numbered excerpt 1..N; each excerpt has exactly one primary_theme.",
        max_length=120,
    )


class PdfRedditThemeFallbackRow(BaseModel):
    name: str = Field(..., description="Substantive theme label.")
    count: int = Field(..., ge=0, description="Number of Reddit excerpts in the list for this theme.")


class PdfRedditThemeFallbackResult(BaseModel):
    themes: list[PdfRedditThemeFallbackRow] = Field(default_factory=list, max_length=14)


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
        "Negative, Neutral, or Mixed.\n\n"
        "For the suggested **response** field, write as if you are a knowledgeable pharmacy team member replying "
        "publicly on social media (first person plural “we” or a natural staff voice). Sound like a real pharmacy: "
        "reference the poster’s actual topic when possible (e.g. delivery, refill timing, insurance, side effects "
        "they mentioned, a specific product or program—only when grounded in their text). Offer concrete next steps "
        "a pharmacy would give: call the store, speak with the pharmacist, check the label, transfer or refill "
        "process, delivery options, or visiting in person—without inventing store hours, phone numbers, or policies "
        "not in the post.\n\n"
        "Tone by sentiment: Negative—apologize briefly when appropriate, validate frustration, de-escalate, offer "
        "to help resolve it. Positive—thank them sincerely and reinforce the relationship. Mixed—acknowledge both "
        "sides calmly. Neutral—clear, helpful, professional.\n\n"
        "Avoid generic filler (“Thank you for sharing”, “Great question”, “We appreciate your feedback”) as the "
        "whole reply unless paired with specific pharmacy-relevant substance. Do not sound like a chatbot or "
        "corporate FAQ. Do not ask for protected health information in a public thread—invite them to call or "
        "message the pharmacy privately for account-specific help.\n\n"
        "Keep each response under 55 words, no insults or escalation, and do not state facts that are not supported "
        "by the post."
    ),
    model=create_gemini_model(),
    output_type=EnrichmentBatch,
)


# PDF “Top themes” uses Reddit matches only: one primary theme per post/comment → real counts (scaled if sampled).
pdf_reddit_themes_agent = Agent(
    name="PDF Reddit Theme Extractor",
    instructions=(
        "You read numbered post/comment excerpts tied to a search keyword.\n\n"
        "Return **assignments**: a list with exactly one object per numbered line, fields excerpt_index and primary_theme. "
        "excerpt_index must match the line number (1 through N). primary_theme is exactly ONE short specific label per "
        "line (the best single theme for that item)—not a list, not multiple themes per line.\n\n"
        "Every integer 1..N must appear exactly once. Use consistent primary_theme strings for the same topic. "
        "Avoid generic labels ('questions', 'comments', 'people'). Name concrete angles (insurance, wait times, "
        "side effects, pickup delays, etc.)."
    ),
    model=create_gemini_model(),
    output_type=PdfRedditThemeResult,
)

pdf_reddit_themes_fallback_agent = Agent(
    name="PDF Reddit Theme Extractor Fallback",
    instructions=(
        "Numbered excerpts only. Return **themes**: up to 10 rows with name and integer count. "
        "Each excerpt belongs to exactly one theme; the counts must sum to N. "
        "Specific labels only, no vague single-word themes."
    ),
    model=create_gemini_model(),
    output_type=PdfRedditThemeFallbackResult,
)


# Split large payloads into smaller batches that fit comfortably in one prompt.
def chunked(items: list[dict], size: int) -> Iterable[list[dict]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _even_sample_indices(n_records: int, max_items: int) -> list[int]:
    if n_records <= max_items:
        return list(range(n_records))
    step = (n_records - 1) / (max_items - 1)
    picks: list[int] = []
    seen: set[int] = set()
    for j in range(max_items):
        idx = min(n_records - 1, int(round(j * step)))
        if idx not in seen:
            seen.add(idx)
            picks.append(idx)
    fill = 0
    while len(picks) < max_items and fill < n_records:
        if fill not in seen:
            seen.add(fill)
            picks.append(fill)
        fill += 1
    return picks[:max_items]


def _reddit_records(records: list[dict]) -> list[dict]:
    return [r for r in records if str(r.get("platform") or "").strip() == REDDIT_PLATFORM]


def _reddit_theme_corpus(reddit_records: list[dict], max_excerpts: int) -> tuple[str, int, int]:
    """Build numbered Reddit-only corpus: (text, excerpt_k, reddit_total)."""
    total = len(reddit_records)
    if total == 0:
        return "", 0, 0
    indices = list(range(total)) if total <= max_excerpts else _even_sample_indices(total, max_excerpts)
    lines: list[str] = []
    for display_i, rec_i in enumerate(indices, start=1):
        rec = reddit_records[rec_i]
        sub = str(rec.get("subject") or "").strip().replace("\n", " ")[:120]
        body = str(rec.get("text") or "").strip().replace("\n", " ")[:360]
        kind = rec.get("kind", "")
        sent = rec.get("sentiment", "")
        lines.append(f"{display_i}. [{kind} | {sent}] {sub} | {body}")
    return "\n".join(lines), len(indices), total


def _normalize_excerpt_index(raw: int, excerpt_n: int) -> int | None:
    if excerpt_n <= 0:
        return None
    if 1 <= raw <= excerpt_n:
        return raw
    if 0 <= raw < excerpt_n:
        return raw + 1
    return None


def _primary_theme_counter(assignments: list[PdfRedditExcerptAssignment], excerpt_n: int) -> Counter[str]:
    """Each line 1..excerpt_n gets exactly one bucket (Unclassified if model skipped it)."""
    idx_theme: dict[int, str] = {}
    for row in assignments:
        idx = _normalize_excerpt_index(int(row.excerpt_index), excerpt_n)
        if idx is None:
            continue
        theme = (row.primary_theme or "").strip()
        if not theme:
            continue
        idx_theme.setdefault(idx, theme)
    counts: Counter[str] = Counter()
    for line in range(1, excerpt_n + 1):
        t = idx_theme.get(line, "Unclassified")
        counts[t] += 1
    return counts


def _top_theme_row_list(counts: Counter[str], top_n: int) -> list[tuple[str, int]]:
    return [(n, c) for n, c in counts.most_common(top_n) if c > 0]


def _extract_reddit_themes_fallback(corpus: str, keyword: str, excerpt_k: int) -> list[tuple[str, int]]:
    prompt = (
        f"Search keyword (context): {keyword!r}\n"
        f"N = {excerpt_k} numbered excerpts below. Return themes where counts sum to N.\n\n"
        f"{corpus}"
    )
    try:
        result = run_agent(pdf_reddit_themes_fallback_agent, prompt, PdfRedditThemeFallbackResult)
    except Exception:
        return []
    merged: Counter[str] = Counter()
    for row in result.themes or []:
        name = row.name.strip()
        if name:
            merged[name] += max(0, int(row.count))
    if not merged:
        return []
    s = sum(merged.values())
    if s != excerpt_k and s > 0:
        adj = Counter()
        for k, v in merged.items():
            adj[k] = max(0, int(round(v * excerpt_k / s)))
        drift = excerpt_k - sum(adj.values())
        if drift != 0 and adj:
            mk = max(adj, key=lambda x: adj[x])
            adj[mk] = max(0, adj[mk] + drift)
        merged = adj
    return _top_theme_row_list(merged, 10)


def extract_pdf_themes(records: list[dict], keyword: str) -> list[tuple[str, int]]:
    """Reddit-only data path: up to 10 themes; counts are raw tallies on analyzed excerpts (no scaling)."""
    reddit = _reddit_records(records)
    if not reddit:
        return []
    max_excerpts = 80
    corpus, excerpt_k, reddit_total = _reddit_theme_corpus(reddit, max_excerpts)
    if excerpt_k == 0:
        return []
    sample_note = ""
    if excerpt_k < reddit_total:
        sample_note = (
            f" The export has {reddit_total} matching items; this list shows {excerpt_k} representative lines. "
            f"Cover excerpt_index 1..{excerpt_k} only. Do not extrapolate—counts will reflect exactly these {excerpt_k} lines."
        )
    user_prompt = (
        f"Search keyword (context): {keyword!r}\n"
        f"N = {excerpt_k} numbered lines (1..{excerpt_k}).{sample_note}\n\n"
        f"{corpus}"
    )
    themes: list[tuple[str, int]] = []
    try:
        result = run_agent(pdf_reddit_themes_agent, user_prompt, PdfRedditThemeResult)
        counts = _primary_theme_counter(list(result.assignments or []), excerpt_k)
        themes = _top_theme_row_list(counts, 10)
    except Exception:
        themes = []
    if themes:
        return themes
    return _extract_reddit_themes_fallback(corpus, keyword, excerpt_k)


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
            "The response must read like a real pharmacy replying on social media: specific to the post, "
            "professional, and helpful—not generic.\n\n"
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
