"""
PDF aggregation agent for Sentiment Analyzer.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import tempfile
import unicodedata
import re

from fpdf import FPDF

from core.platforms import PLATFORM_ORDER
from core.formatting import format_timestamp, link_label, normalize_sentiment
from core.records import deserialize_records


SENTIMENT_STYLES = {
    "Positive": {"fill": (220, 252, 231), "line": (34, 197, 94), "text": (22, 101, 52)},
    "Negative": {"fill": (254, 226, 226), "line": (239, 68, 68), "text": (153, 27, 27)},
    "Neutral": {"fill": (241, 245, 249), "line": (148, 163, 184), "text": (51, 65, 85)},
    "Mixed": {"fill": (254, 243, 199), "line": (245, 158, 11), "text": (146, 64, 14)},
    "Unknown": {"fill": (224, 231, 255), "line": (99, 102, 241), "text": (55, 48, 163)},
}
SENTIMENT_ORDER = ["Positive", "Negative", "Neutral", "Mixed", "Unknown"]
STOPWORDS = {
    "all",
    "and",
    "are",
    "about",
    "after",
    "again",
    "also",
    "any",
    "because",
    "being",
    "but",
    "can",
    "could",
    "for",
    "from",
    "has",
    "have",
    "how",
    "into",
    "its",
    "just",
    "like",
    "more",
    "new",
    "not",
    "only",
    "our",
    "out",
    "over",
    "people",
    "post",
    "really",
    "should",
    "still",
    "than",
    "that",
    "the",
    "their",
    "there",
    "they",
    "this",
    "through",
    "too",
    "use",
    "was",
    "what",
    "when",
    "will",
    "with",
    "would",
    "your",
}


# Normalize text down to PDF-safe ASCII so report generation stays robust.
def _pdf_safe_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return normalized.encode("ascii", "ignore").decode("ascii")


def _sentiment_style(sentiment: object) -> dict:
    return SENTIMENT_STYLES.get(normalize_sentiment(sentiment), SENTIMENT_STYLES["Unknown"])


def _ensure_space(pdf: FPDF, height: float) -> None:
    if pdf.get_y() + height > pdf.h - pdf.b_margin:
        pdf.add_page()


def _record_date(record: dict) -> str:
    timestamp = float(record.get("created_utc") or 0)
    if timestamp <= 0:
        return "Unknown"
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%m/%d")


# Compute shared summary totals used by the PDF cover and section summaries.
def _summary_counts(records: list[dict]) -> tuple[int, int, Counter]:
    total_comments = sum(1 for record in records if record.get("kind") == "comment")
    total_posts = sum(1 for record in records if record.get("kind") == "post")
    sentiment_counts = Counter(
        normalize_sentiment(record.get("sentiment")) for record in records
    )
    return total_comments, total_posts, sentiment_counts


# Render the per-platform summary cards and sentiment breakdown table.
def _render_summary(pdf: FPDF, records: list[dict], title: str) -> None:
    total_comments, total_posts, sentiment_counts = _summary_counts(records)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _pdf_safe_text(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    pdf.set_draw_color(225, 230, 240)
    summary_width = (pdf.w - pdf.l_margin - pdf.r_margin - 8) / 3
    summary_items = [
        ("Total Matches", str(len(records)), (13, 39, 92), (255, 255, 255)),
        ("Comments", str(total_comments), (46, 125, 246), (255, 255, 255)),
        ("Posts", str(total_posts), (15, 118, 110), (255, 255, 255)),
    ]
    start_x = pdf.l_margin
    start_y = pdf.get_y()
    box_height = 20
    for idx, (label, value, fill_rgb, text_rgb) in enumerate(summary_items):
        x = start_x + idx * (summary_width + 4)
        pdf.set_xy(x, start_y)
        pdf.set_fill_color(*fill_rgb)
        pdf.rect(x, start_y, summary_width, box_height, style="FD")
        pdf.set_text_color(*text_rgb)
        pdf.set_xy(x, start_y + 4)
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(summary_width, 5, _pdf_safe_text(value), align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_xy(x, start_y + 11)
        pdf.set_font("Helvetica", size=9)
        pdf.cell(summary_width, 4, _pdf_safe_text(label), align="C")
        pdf.set_text_color(0, 0, 0)
    pdf.set_y(start_y + box_height + 6)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Sentiment Breakdown", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    max_count = max(sentiment_counts.values(), default=1)
    chart_w = pdf.w - pdf.l_margin - pdf.r_margin - 72
    for sentiment in SENTIMENT_ORDER:
        count = sentiment_counts.get(sentiment, 0)
        if count == 0:
            continue
        style = _sentiment_style(sentiment)
        pdf.set_fill_color(*style["fill"])
        pdf.set_text_color(*style["text"])
        pdf.cell(38, 8, sentiment, border=1, fill=True)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(18, 8, str(count), border=1, align="C")
        x = pdf.get_x() + 4
        y = pdf.get_y() + 2
        bar_w = (count / max_count) * chart_w
        pdf.set_fill_color(*style["line"])
        pdf.rect(x, y, bar_w, 4, style="F")
        pdf.ln(8)
    pdf.set_fill_color(232, 240, 254)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(46, 8, "Total", border=1, fill=True)
    pdf.cell(20, 8, str(len(records)), border=1, align="C")
    pdf.ln(10)


def _render_overall_sentiment_visual(pdf: FPDF, records: list[dict]) -> None:
    counts = Counter(normalize_sentiment(record.get("sentiment")) for record in records)
    total = len(records) or 1
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Sentiment Mix", new_x="LMARGIN", new_y="NEXT")
    bar_x = pdf.l_margin
    bar_y = pdf.get_y()
    bar_w = pdf.w - pdf.l_margin - pdf.r_margin
    bar_h = 12
    cursor = bar_x
    for sentiment in SENTIMENT_ORDER:
        count = counts.get(sentiment, 0)
        if count <= 0:
            continue
        segment_w = bar_w * count / total
        style = _sentiment_style(sentiment)
        pdf.set_fill_color(*style["line"])
        pdf.rect(cursor, bar_y, segment_w, bar_h, style="F")
        cursor += segment_w
    pdf.set_y(bar_y + bar_h + 6)

    legend_w = (pdf.w - pdf.l_margin - pdf.r_margin) / 5
    for sentiment in SENTIMENT_ORDER:
        style = _sentiment_style(sentiment)
        pdf.set_fill_color(*style["fill"])
        pdf.set_text_color(*style["text"])
        pdf.set_font("Helvetica", "B", 9)
        label = f"{sentiment}: {counts.get(sentiment, 0)}"
        pdf.cell(legend_w, 7, _pdf_safe_text(label), border=1, align="C", fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(12)


def _render_trend_chart(pdf: FPDF, records: list[dict]) -> None:
    dated_records = [record for record in records if float(record.get("created_utc") or 0) > 0]
    if not dated_records:
        return

    date_counts: dict[str, Counter] = {}
    for record in dated_records:
        date_counts.setdefault(_record_date(record), Counter())[normalize_sentiment(record.get("sentiment"))] += 1
    dates = sorted(date_counts.keys())
    max_total = max(sum(date_counts[date].values()) for date in dates) or 1

    _ensure_space(pdf, 72)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Trend Over Time", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(0, 5, "Daily volume by sentiment across the captured social results.", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)

    chart_x = pdf.l_margin
    chart_y = pdf.get_y() + 4
    chart_w = pdf.w - pdf.l_margin - pdf.r_margin
    chart_h = 42
    bar_gap = 2
    bar_w = max(5, (chart_w - (len(dates) - 1) * bar_gap) / len(dates))
    pdf.set_draw_color(226, 232, 240)
    pdf.rect(chart_x, chart_y, chart_w, chart_h)

    for index, date in enumerate(dates):
        x = chart_x + index * (bar_w + bar_gap)
        y_cursor = chart_y + chart_h
        for sentiment in SENTIMENT_ORDER:
            count = date_counts[date].get(sentiment, 0)
            if count <= 0:
                continue
            segment_h = chart_h * count / max_total
            y_cursor -= segment_h
            pdf.set_fill_color(*_sentiment_style(sentiment)["line"])
            pdf.rect(x, y_cursor, bar_w, segment_h, style="F")
        pdf.set_xy(x - 1, chart_y + chart_h + 2)
        pdf.set_font("Helvetica", size=6)
        pdf.cell(bar_w + 2, 3, _pdf_safe_text(date), align="C")
    pdf.set_y(chart_y + chart_h + 10)


def _top_themes(records: list[dict], keyword: str) -> list[tuple[str, int]]:
    keyword_tokens = set(re.findall(r"[a-z0-9]{3,}", keyword.lower()))
    words: list[str] = []
    for record in records:
        text = f"{record.get('subject', '')} {record.get('text', '')}".lower()
        for word in re.findall(r"[a-z][a-z0-9]{2,}", text):
            if word in STOPWORDS or word in keyword_tokens:
                continue
            words.append(word)
    return Counter(words).most_common(12)


def _render_themes(pdf: FPDF, records: list[dict], keyword: str) -> None:
    themes = _top_themes(records, keyword)
    if not themes:
        return

    _ensure_space(pdf, 54)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Top Themes And Keywords", new_x="LMARGIN", new_y="NEXT")
    max_count = max(count for _, count in themes) or 1
    label_w = 36
    chart_w = pdf.w - pdf.l_margin - pdf.r_margin - label_w - 16
    for word, count in themes:
        _ensure_space(pdf, 8)
        pdf.set_font("Helvetica", size=9)
        pdf.cell(label_w, 6, _pdf_safe_text(word.title()))
        pdf.set_fill_color(37, 99, 235)
        pdf.rect(pdf.get_x(), pdf.get_y() + 1.5, chart_w * count / max_count, 3.5, style="F")
        pdf.set_x(pdf.get_x() + chart_w + 4)
        pdf.cell(10, 6, str(count), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)


def _recommended_actions(records: list[dict], keyword: str) -> list[str]:
    counts = Counter(normalize_sentiment(record.get("sentiment")) for record in records)
    themes = [theme for theme, _ in _top_themes(records, keyword)[:3]]
    theme_text = ", ".join(theme.title() for theme in themes) if themes else "the highest-volume topics"
    actions = [
        f"Lead campaign messaging with {theme_text} because these themes appear most often in the conversation.",
    ]
    if counts.get("Positive", 0):
        actions.append("Turn positive comments into short testimonial snippets, social proof, and ad-copy variants.")
    if counts.get("Negative", 0):
        actions.append("Create a response plan for negative posts: acknowledge the concern, clarify next steps, and route repeated issues to support.")
    if counts.get("Mixed", 0) or counts.get("Neutral", 0):
        actions.append("Use neutral and mixed posts for FAQ content, explainer posts, and campaign copy that addresses open questions.")
    actions.append("Re-run the report after the next campaign beat and compare sentiment mix against this baseline.")
    return actions[:5]


def _render_recommended_actions(pdf: FPDF, records: list[dict], keyword: str) -> None:
    _ensure_space(pdf, 56)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Campaign-Ready Recommended Actions", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    for index, action in enumerate(_recommended_actions(records, keyword), start=1):
        _ensure_space(pdf, 12)
        pdf.multi_cell(0, 6, _pdf_safe_text(f"{index}. {action}"), align="L", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)


def _render_positive_quotes(pdf: FPDF, records: list[dict]) -> None:
    positives = [
        record
        for record in records
        if normalize_sentiment(record.get("sentiment")) == "Positive" and str(record.get("text") or "").strip()
    ][:6]
    if not positives:
        return

    _ensure_space(pdf, 52)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Top Positive Quotes For Marketing Copy", new_x="LMARGIN", new_y="NEXT")
    for record in positives:
        _ensure_space(pdf, 24)
        style = _sentiment_style("Positive")
        pdf.set_fill_color(*style["fill"])
        pdf.set_draw_color(*style["line"])
        x = pdf.l_margin
        y = pdf.get_y()
        w = pdf.w - pdf.l_margin - pdf.r_margin
        pdf.rect(x, y, w, 20, style="DF")
        quote = str(record.get("text") or "").strip()
        if len(quote) > 180:
            quote = quote[:177].rstrip() + "..."
        pdf.set_xy(x + 4, y + 3)
        pdf.set_font("Helvetica", size=9)
        pdf.multi_cell(w - 8, 5, _pdf_safe_text(f'"{quote}"'), new_x="LMARGIN", new_y="NEXT")
        pdf.set_xy(x + 4, y + 14)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*style["text"])
        pdf.cell(w - 8, 4, _pdf_safe_text(f"{record.get('platform', 'Unknown')} - {record.get('user_id', 'Unknown')}"))
        pdf.set_text_color(0, 0, 0)
        pdf.set_y(y + 24)


def _render_marketing_insights(pdf: FPDF, records: list[dict], keyword: str) -> None:
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Marketing Insights", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    pdf.set_text_color(71, 85, 105)
    pdf.multi_cell(
        0,
        6,
        _pdf_safe_text("Visual summary for campaign planning, audience messaging, and copy mining."),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)
    _render_overall_sentiment_visual(pdf, records)
    _render_trend_chart(pdf, records)
    _render_themes(pdf, records, keyword)
    _render_recommended_actions(pdf, records, keyword)
    _render_positive_quotes(pdf, records)


# Render the first-page platform count box below the title header.
def _render_cover_platform_counts(pdf: FPDF, records: list[dict]) -> None:
    counts = Counter(str(record.get("platform") or "Unknown") for record in records)
    box_x = pdf.l_margin
    box_y = pdf.get_y()
    box_w = pdf.w - pdf.l_margin - pdf.r_margin
    box_h = 24

    pdf.set_draw_color(210, 218, 230)
    pdf.set_fill_color(248, 250, 252)
    pdf.rect(box_x, box_y, box_w, box_h, style="DF", round_corners=True, corner_radius=2)

    pdf.set_xy(box_x + 4, box_y + 3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(box_w - 8, 5, "Platform Match Counts", align="C", new_x="LMARGIN", new_y="NEXT")

    labels = [
        ("Reddit", counts.get("Reddit", 0)),
        ("Facebook", counts.get("Facebook", 0)),
        ("X.com", counts.get("X.com", 0)),
    ]
    segment_w = (box_w - 8) / 3
    for index, (label, value) in enumerate(labels):
        current_x = box_x + 4 + index * segment_w
        pdf.set_xy(current_x, box_y + 10)
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(segment_w, 5, str(value), align="C")
        pdf.set_xy(current_x, box_y + 16)
        pdf.set_font("Helvetica", size=9)
        pdf.cell(segment_w, 4, _pdf_safe_text(label), align="C")

    pdf.set_y(box_y + box_h + 6)


# Render each detailed record block in the PDF section body.
def _render_details(pdf: FPDF, records: list[dict]) -> None:
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Detailed Results", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=11)
    for index, record in enumerate(records):
        platform = str(record.get("platform") or "Unknown")
        current_link_label = link_label(platform)
        sentiment = normalize_sentiment(record.get("sentiment"))
        style = _sentiment_style(sentiment)
        pdf.set_fill_color(*style["fill"])
        pdf.set_draw_color(*style["line"])
        pdf.set_text_color(*style["text"])
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(
            0,
            8,
            _pdf_safe_text(f"{platform} | {str(record.get('kind') or 'match').title()} | {sentiment}"),
            border=1,
            fill=True,
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", size=11)
        lines = [
            f"User ID: {record.get('user_id', 'Unknown')}",
            f"Location: {record.get('location', 'N/A')}",
            f"Subject: {record.get('subject', '') or 'N/A'}",
            f"Comment: {record.get('text', '')}",
            f"Date: {format_timestamp(float(record.get('created_utc') or 0))}",
            f"Sentiment: {record.get('sentiment', 'Unknown')}",
            f"Suggested Response: {record.get('response', '') or 'N/A'}",
            f"{current_link_label}: {record.get('permalink', '')}",
        ]
        for line in lines:
            clean_line = _pdf_safe_text(line.strip())
            if not clean_line:
                continue
            if clean_line.startswith(f"{current_link_label}: "):
                url = line.split(f"{current_link_label}: ", 1)[1].strip()
                pdf.set_text_color(0, 102, 204)
                pdf.multi_cell(
                    0,
                    7,
                    _pdf_safe_text(f"{current_link_label}: {url}"),
                    align="L",
                    link=url,
                    new_x="LMARGIN",
                    new_y="NEXT",
                )
                pdf.set_text_color(0, 0, 0)
            else:
                pdf.multi_cell(0, 7, clean_line, align="L", new_x="LMARGIN", new_y="NEXT")
        if index < len(records) - 1:
            y = pdf.get_y() + 1
            pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
            pdf.ln(5)


# Render one platform section on its own page, or reuse page one for Reddit.
def _render_platform_section(pdf: FPDF, platform: str, records: list[dict], *, add_page: bool = True) -> None:
    if add_page:
        pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 10, _pdf_safe_text(platform), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    if not records:
        pdf.set_font("Helvetica", size=11)
        pdf.multi_cell(0, 7, _pdf_safe_text(f"No {platform} matches found for this search."))
        return
    _render_summary(pdf, records, f"{platform} Summary")
    _render_details(pdf, records)


# Build the final PDF file from the serialized search results stored by Gradio.
def generate_pdf_report(records_payload: str, keyword: str = "") -> tuple[str, str | None]:
    records = deserialize_records(records_payload)
    clean_keyword = (keyword or "").strip()
    if not records:
        return "Nothing to export yet. Run a search first.", None

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_fill_color(13, 39, 92)
    pdf.set_text_color(255, 255, 255)
    pdf.rect(pdf.l_margin, 12, pdf.w - pdf.l_margin - pdf.r_margin, 24, style="F")
    pdf.set_xy(pdf.l_margin + 5, 16)
    pdf.set_font("Helvetica", "B", 17)
    title = f'Sentiment Analyzer for "{clean_keyword or "Keyword"}"'
    pdf.cell(
        pdf.w - pdf.l_margin - pdf.r_margin - 10,
        8,
        _pdf_safe_text(title),
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.set_x(pdf.l_margin + 5)
    pdf.set_font("Helvetica", size=10)
    pdf.cell(
        pdf.w - pdf.l_margin - pdf.r_margin - 10,
        6,
        _pdf_safe_text(datetime.now(timezone.utc).strftime("Generated on %Y-%m-%d %H:%M UTC")),
        align="C",
        new_y="NEXT",
    )
    pdf.set_text_color(0, 0, 0)
    pdf.ln(10)
    _render_cover_platform_counts(pdf, records)
    _render_summary(pdf, records, "Overall Summary")
    _render_marketing_insights(pdf, records, clean_keyword)

    for index, platform in enumerate(PLATFORM_ORDER):
        platform_records = [record for record in records if record.get("platform") == platform]
        _render_platform_section(pdf, platform, platform_records, add_page=True)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        pdf.output(tmp_file.name)
        pdf_path = tmp_file.name

    return "PDF is ready to download.", pdf_path
