"""
PDF aggregation agent for Sentiment Analyzer.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import os
import tempfile
import unicodedata

from fpdf import FPDF

from core.platforms import SEARCH_ACTIVE_PLATFORMS
from core.formatting import format_timestamp, link_label, normalize_sentiment, sentiment_colors
from core.records import deserialize_records
from platform_agents.enrichment_agent import extract_pdf_themes


SENTIMENT_STYLES = {
    "Positive": {"fill": (229, 247, 245), "line": (32, 161, 151), "text": (17, 117, 109)},
    "Negative": {"fill": (253, 232, 239), "line": (190, 48, 92), "text": (145, 36, 70)},
    "Neutral": {"fill": (244, 246, 248), "line": (160, 166, 176), "text": (83, 91, 103)},
    "Mixed": {"fill": (255, 244, 229), "line": (237, 147, 55), "text": (153, 89, 22)},
    "Unknown": {"fill": (238, 242, 255), "line": (109, 123, 186), "text": (73, 84, 143)},
}
SENTIMENT_ORDER = ["Positive", "Negative", "Neutral", "Mixed", "Unknown"]

# Normalize text down to PDF-safe ASCII so report generation stays robust.
def _pdf_safe_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return normalized.encode("ascii", "ignore").decode("ascii")


def _sentiment_style(sentiment: object) -> dict:
    return SENTIMENT_STYLES.get(normalize_sentiment(sentiment), SENTIMENT_STYLES["Unknown"])


def _hex_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _pdf_export_date_range_utc() -> tuple[str, str]:
    """Filename window: start = 7 calendar days before today (UTC), end = today (UTC)."""
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=7)
    return start.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")


def _pdf_export_basename() -> str:
    start_d, end_d = _pdf_export_date_range_utc()
    name = f"OptioRx Reddit Sentiment Analysis {start_d}_{end_d}.pdf"
    return "".join(ch if ch not in '<>:"/\\|?*' else "_" for ch in name)


def _ensure_space(pdf: FPDF, height: float) -> None:
    if pdf.get_y() + height > pdf.h - pdf.b_margin:
        pdf.add_page()


def _record_date(record: dict) -> str:
    timestamp = float(record.get("created_utc") or 0)
    if timestamp <= 0:
        return "Unknown"
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%m/%d")


def _usable_width(pdf: FPDF) -> float:
    return pdf.w - pdf.l_margin - pdf.r_margin


def _draw_panel(pdf: FPDF, x: float, y: float, w: float, h: float, *, fill: tuple[int, int, int] = (255, 255, 255)) -> None:
    pdf.set_draw_color(226, 232, 240)
    pdf.set_fill_color(*fill)
    pdf.rect(x, y, w, h, style="DF", round_corners=True, corner_radius=2)


def _section_title(pdf: FPDF, title: str, subtitle: str = "") -> None:
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(17, 24, 39)
    pdf.cell(0, 5, _pdf_safe_text(title), new_x="LMARGIN", new_y="NEXT")
    if subtitle:
        pdf.set_font("Helvetica", size=7)
        pdf.set_text_color(100, 116, 139)
        pdf.multi_cell(0, 4, _pdf_safe_text(subtitle), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)


def _sentiment_score(records: list[dict]) -> int:
    if not records:
        return 0
    weights = {"Positive": 100, "Mixed": 25, "Neutral": 0, "Unknown": 0, "Negative": -100}
    total = sum(weights.get(normalize_sentiment(record.get("sentiment")), 0) for record in records)
    return int(round(total / len(records)))


# Compute shared summary totals used by the PDF cover and section summaries.
def _summary_counts(records: list[dict]) -> tuple[int, int, Counter]:
    total_comments = sum(1 for record in records if record.get("kind") == "comment")
    total_posts = sum(1 for record in records if record.get("kind") == "post")
    sentiment_counts = Counter(
        normalize_sentiment(record.get("sentiment")) for record in records
    )
    return total_comments, total_posts, sentiment_counts


def _render_dashboard_header(pdf: FPDF, keyword: str) -> None:
    pdf.set_fill_color(237, 246, 249)
    pdf.rect(0, 0, pdf.w, 7, style="F")
    pdf.set_draw_color(226, 232, 240)
    pdf.line(0, 14, pdf.w, 14)

    pdf.set_xy(pdf.l_margin, 8)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(32, 161, 151)
    pdf.cell(12, 4, "SA")
    pdf.set_font("Helvetica", size=7)
    pdf.set_text_color(100, 116, 139)
    for item in ["Feed", "Analyze", "Overview", "Reports", "Actions"]:
        pdf.cell(24, 4, item)

    pdf.set_xy(pdf.l_margin, 24)
    pdf.set_font("Helvetica", "B", 17)
    pdf.set_text_color(17, 24, 39)
    pdf.cell(0, 8, "Sentiment Dashboard", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=8)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(0, 5, _pdf_safe_text("Find out how your topic is perceived online."), new_x="LMARGIN", new_y="NEXT")

    chip_y = 24
    chip_w = 44
    right_x = pdf.w - pdf.r_margin - chip_w
    for label in [datetime.now(timezone.utc).strftime("%Y-%m-%d"), keyword or "Keyword"]:
        pdf.set_xy(right_x, chip_y)
        _draw_panel(pdf, right_x, chip_y, chip_w, 8, fill=(255, 255, 255))
        pdf.set_xy(right_x + 3, chip_y + 2.2)
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(51, 65, 85)
        pdf.cell(chip_w - 6, 3, _pdf_safe_text(label[:28]))
        right_x -= chip_w + 4
    pdf.set_text_color(0, 0, 0)
    pdf.set_y(45)


def _render_topic_overview(pdf: FPDF, records: list[dict]) -> None:
    total_comments, total_posts, sentiment_counts = _summary_counts(records)
    platform_counts = Counter(str(record.get("platform") or "Unknown") for record in records)
    x = pdf.l_margin
    y = pdf.get_y()
    w = _usable_width(pdf)
    h = 54
    _draw_panel(pdf, x, y, w, h)
    pdf.set_xy(x + 5, y + 5)
    _section_title(pdf, "Topic Overview", "See how many people are talking, where conversations happen, and the current sentiment mix.")

    kpi_y = y + 22
    kpi_w = 36
    kpis = [
        ("Mentions", len(records), "Total social records"),
        ("Comments", total_comments, "Conversation replies"),
        ("Posts", total_posts, "Original posts"),
    ]
    for index, (label, value, sublabel) in enumerate(kpis):
        card_x = x + 5 + index * 46
        pdf.set_xy(card_x, kpi_y)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(71, 85, 105)
        pdf.cell(kpi_w, 4, label)
        pdf.set_xy(card_x, kpi_y + 7)
        pdf.set_font("Helvetica", "B", 17)
        pdf.set_text_color(17, 24, 39)
        pdf.cell(kpi_w, 7, str(value))
        pdf.set_xy(card_x, kpi_y + 18)
        pdf.set_font("Helvetica", size=7)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(kpi_w, 4, sublabel)

    dist_x = x + w - 54
    dist_y = kpi_y
    pdf.set_xy(dist_x, dist_y)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(0, 4, "Sources Distribution")
    max_platform = max(platform_counts.values(), default=1)
    for row, platform in enumerate(SEARCH_ACTIVE_PLATFORMS):
        count = platform_counts.get(platform, 0)
        bar_y = dist_y + 8 + row * 8
        pdf.set_xy(dist_x, bar_y)
        pdf.set_font("Helvetica", size=7)
        pdf.set_text_color(71, 85, 105)
        pdf.cell(18, 4, platform)
        pdf.set_fill_color(238, 242, 246)
        pdf.rect(dist_x + 19, bar_y + 1, 23, 3, style="F")
        pdf.set_fill_color(32, 161, 151)
        pdf.rect(dist_x + 19, bar_y + 1, 23 * count / max_platform, 3, style="F")
        pdf.set_xy(dist_x + 43, bar_y)
        pdf.cell(8, 4, str(count), align="R")

    pdf.set_text_color(0, 0, 0)
    pdf.set_y(y + h + 5)


def _render_sentiment_dashboard_panel(pdf: FPDF, records: list[dict]) -> None:
    counts = Counter(normalize_sentiment(record.get("sentiment")) for record in records)
    total = len(records) or 1
    score = _sentiment_score(records)
    x = pdf.l_margin
    y = pdf.get_y()
    w = _usable_width(pdf)
    h = 66
    _draw_panel(pdf, x, y, w, h)
    pdf.set_xy(x + 5, y + 5)
    _section_title(pdf, "Sentiment Score", "Know if people are talking positively or negatively about the topic.")

    score_x = x + 8
    score_y = y + 28
    score_color = (32, 161, 151) if score >= 20 else (190, 48, 92) if score < 0 else (160, 166, 176)
    _draw_panel(pdf, score_x, score_y, 39, 26, fill=(255, 255, 255))
    pdf.set_xy(score_x + 2, score_y + 5)
    pdf.set_font("Helvetica", "B", 19)
    pdf.set_text_color(17, 24, 39)
    pdf.cell(35, 8, str(score), align="C")
    pdf.set_fill_color(238, 242, 246)
    pdf.rect(score_x + 5, score_y + 18, 29, 2.5, style="F")
    pdf.set_fill_color(*score_color)
    pdf.rect(score_x + 5, score_y + 18, 29 * max(0, score + 100) / 200, 2.5, style="F")
    pdf.set_xy(score_x, score_y + 29)
    pdf.set_font("Helvetica", size=6)
    pdf.set_text_color(148, 163, 184)
    pdf.cell(8, 3, "-100")
    pdf.set_x(score_x + 30)
    pdf.cell(8, 3, "100")

    copy_x = x + 58
    pdf.set_xy(copy_x, y + 28)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(17, 24, 39)
    pdf.cell(50, 5, "Analyzed Mentions")
    pdf.set_xy(copy_x, y + 36)
    pdf.set_font("Helvetica", size=8)
    pdf.set_text_color(71, 85, 105)
    for sentiment in ["Positive", "Neutral", "Negative"]:
        pdf.cell(60, 5, _pdf_safe_text(f"{counts.get(sentiment, 0)} with {sentiment.lower()} sentiment"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_x(copy_x)

    bar_x = x + 112
    bar_y = y + 34
    bar_w = 42
    cursor = bar_x
    for sentiment in ["Positive", "Negative", "Neutral", "Mixed", "Unknown"]:
        count = counts.get(sentiment, 0)
        if not count:
            continue
        segment_w = bar_w * count / total
        pdf.set_fill_color(*_sentiment_style(sentiment)["line"])
        pdf.rect(cursor, bar_y, segment_w, 18, style="F")
        cursor += segment_w
    pdf.set_xy(bar_x, bar_y + 22)
    pdf.set_font("Helvetica", size=7)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(bar_w, 4, "Sentiment ratio", align="C")

    note_x = x + w - 52
    note_y = y + 31
    dominant = counts.most_common(1)[0][0] if counts else "Unknown"
    dominant_style = _sentiment_style(dominant)
    _draw_panel(pdf, note_x, note_y, 44, 24, fill=dominant_style["fill"])
    pdf.set_xy(note_x + 4, note_y + 5)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*dominant_style["text"])
    pdf.cell(36, 4, _pdf_safe_text(f"Mostly {dominant.lower()}"))
    pdf.set_xy(note_x + 4, note_y + 11)
    pdf.set_font("Helvetica", size=7)
    pdf.multi_cell(36, 4, _pdf_safe_text("Dominant tone in the current conversation set."), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.set_y(y + h + 5)


def _render_location_dashboard_panel(pdf: FPDF, records: list[dict]) -> None:
    location_counts: dict[str, Counter] = {}
    for record in records:
        location = str(record.get("location") or "N/A").strip()
        if not location or location.upper() == "N/A":
            continue
        location_counts.setdefault(location, Counter())[normalize_sentiment(record.get("sentiment"))] += 1
    if not location_counts:
        return

    rows = sorted(location_counts.items(), key=lambda item: sum(item[1].values()), reverse=True)[:5]
    x = pdf.l_margin
    y = pdf.get_y()
    w = _usable_width(pdf)
    h = 26 + len(rows) * 9
    _ensure_space(pdf, h)
    _draw_panel(pdf, x, y, w, h)
    pdf.set_xy(x + 5, y + 5)
    _section_title(pdf, "Sentiment In Popular Locations", "Use location signals to target follow-up messaging more effectively.")
    table_y = y + 21
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_text_color(71, 85, 105)
    pdf.set_xy(x + 5, table_y)
    pdf.cell(70, 4, "Location")
    pdf.cell(70, 4, "Sentiment ratio")
    pdf.cell(20, 4, "Mentions", align="R")
    pdf.cell(22, 4, "Net", align="R")

    for index, (location, counts) in enumerate(rows):
        row_y = table_y + 7 + index * 9
        total = sum(counts.values()) or 1
        net = int(round((counts.get("Positive", 0) - counts.get("Negative", 0)) * 100 / total))
        pdf.set_xy(x + 5, row_y)
        pdf.set_font("Helvetica", size=8)
        pdf.set_text_color(17, 24, 39)
        pdf.cell(70, 4, _pdf_safe_text(location[:34]))
        bar_x = x + 75
        cursor = bar_x
        for sentiment in ["Negative", "Positive", "Neutral", "Mixed"]:
            count = counts.get(sentiment, 0)
            if count <= 0:
                continue
            segment_w = 70 * count / total
            pdf.set_fill_color(*_sentiment_style(sentiment)["line"])
            pdf.rect(cursor, row_y + 1, segment_w, 3, style="F")
            cursor += segment_w
        pdf.set_xy(x + 148, row_y)
        pdf.cell(20, 4, str(total), align="R")
        pdf.set_xy(x + 171, row_y)
        pdf.set_fill_color(229, 247, 245) if net >= 0 else pdf.set_fill_color(253, 232, 239)
        pdf.set_text_color(17, 117, 109) if net >= 0 else pdf.set_text_color(145, 36, 70)
        pdf.set_font("Helvetica", "B", 7)
        pdf.cell(14, 4, str(net), align="C", fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.set_y(y + h + 5)


# Render the per-platform summary cards and sentiment breakdown table.
def _render_summary(pdf: FPDF, records: list[dict], title: str) -> None:
    total_comments, total_posts, sentiment_counts = _summary_counts(records)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _pdf_safe_text(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    pdf.set_draw_color(225, 230, 240)
    summary_width = (pdf.w - pdf.l_margin - pdf.r_margin - 8) / 3
    summary_items = [
        ("Total Matches", str(len(records)), (17, 24, 39), (255, 255, 255)),
        ("Comments", str(total_comments), (32, 161, 151), (255, 255, 255)),
        ("Posts", str(total_posts), (83, 91, 103), (255, 255, 255)),
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

    _ensure_space(pdf, 80)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Trend Over Time", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(0, 5, "Daily volume by sentiment across the captured social results.", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)

    pdf.ln(4)
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
        day_total = sum(date_counts[date].values())
        for sentiment in SENTIMENT_ORDER:
            count = date_counts[date].get(sentiment, 0)
            if count <= 0:
                continue
            segment_h = chart_h * count / max_total
            y_cursor -= segment_h
            pdf.set_fill_color(*_sentiment_style(sentiment)["line"])
            pdf.rect(x, y_cursor, bar_w, segment_h, style="F")
        bar_top = y_cursor
        label_y = bar_top - 5.0 if day_total > 0 else chart_y + 2.0
        pdf.set_xy(x, label_y)
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(bar_w, 4, _pdf_safe_text(str(day_total)), align="C")
        pdf.set_text_color(0, 0, 0)
        pdf.set_xy(x - 1, chart_y + chart_h + 2)
        pdf.set_font("Helvetica", size=6)
        pdf.cell(bar_w + 2, 3, _pdf_safe_text(date), align="C")
    pdf.set_y(chart_y + chart_h + 10)


def _render_themes(pdf: FPDF, themes: list[tuple[str, int]]) -> None:
    if not themes:
        return

    _ensure_space(pdf, 48)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Top Themes", new_x="LMARGIN", new_y="NEXT")
    max_count = max((c for _, c in themes), default=1)
    label_w = 78
    chart_w = pdf.w - pdf.l_margin - pdf.r_margin - label_w - 22
    for name, count in themes:
        _ensure_space(pdf, 8)
        pdf.set_font("Helvetica", size=9)
        label = name if len(name) <= 54 else name[:51].rstrip() + "..."
        pdf.cell(label_w, 6, _pdf_safe_text(label))
        pdf.set_fill_color(32, 161, 151)
        pdf.rect(pdf.get_x(), pdf.get_y() + 1.5, chart_w * count / max_count, 3.5, style="F")
        pdf.set_x(pdf.get_x() + chart_w + 4)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(16, 6, str(count), align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=9)
    pdf.ln(3)
    pdf.ln(6)


def _recommended_actions(records: list[dict], themes: list[tuple[str, int]]) -> list[str]:
    counts = Counter(normalize_sentiment(record.get("sentiment")) for record in records)
    theme_names = [name for name, _ in themes[:3]]
    theme_text = ", ".join(theme_names) if theme_names else "the highest-volume topics"
    actions = [
        f"Shape campaign messaging around {theme_text}—these themes summarize the main discussion threads in this set.",
    ]
    if counts.get("Positive", 0):
        actions.append("Turn positive comments into short testimonial snippets, social proof, and ad-copy variants.")
    if counts.get("Negative", 0):
        actions.append("Create a response plan for negative posts: acknowledge the concern, clarify next steps, and route repeated issues to support.")
    if counts.get("Mixed", 0) or counts.get("Neutral", 0):
        actions.append("Use neutral and mixed posts for FAQ content, explainer posts, and campaign copy that addresses open questions.")
    actions.append("Re-run the report after the next campaign beat and compare sentiment mix against this baseline.")
    return actions[:5]


def _render_recommended_actions(pdf: FPDF, records: list[dict], themes: list[tuple[str, int]]) -> None:
    _ensure_space(pdf, 56)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Campaign-Ready Recommended Actions", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    for index, action in enumerate(_recommended_actions(records, themes), start=1):
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
    pdf_themes = extract_pdf_themes(records, keyword)
    _render_themes(pdf, pdf_themes)
    _render_recommended_actions(pdf, records, pdf_themes)
    _render_positive_quotes(pdf, records)


def _render_label_value(pdf: FPDF, label: str, value: object, *, line_height: float = 6) -> None:
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(51, 65, 85)
    pdf.cell(34, line_height, _pdf_safe_text(label))
    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(15, 23, 42)
    pdf.multi_cell(
        0,
        line_height,
        _pdf_safe_text(str(value or "N/A")),
        align="L",
        new_x="LMARGIN",
        new_y="NEXT",
    )


def _render_sentiment_badge(pdf: FPDF, sentiment: str, x: float, y: float) -> None:
    style = _sentiment_style(sentiment)
    pdf.set_xy(x, y)
    pdf.set_fill_color(*style["fill"])
    pdf.set_draw_color(*style["line"])
    pdf.set_text_color(*style["text"])
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(27, 6, _pdf_safe_text(sentiment), border=1, align="C", fill=True)
    pdf.set_text_color(0, 0, 0)


def _render_gradio_sentiment_pill(pdf: FPDF, sentiment: str, x: float, y: float) -> float:
    """Rounded pill matching Gradio .sentiment-pill; returns pill height."""
    sentiment_n = normalize_sentiment(sentiment)
    text_c, bg_c, bd_c = sentiment_colors(sentiment_n)
    label = _pdf_safe_text(sentiment_n)
    pdf.set_font("Helvetica", "B", 8)
    pill_w = pdf.get_string_width(label) + 4.5
    pill_h = 5.2
    pdf.set_fill_color(*_hex_rgb(bg_c))
    pdf.set_draw_color(*_hex_rgb(bd_c))
    pdf.rect(x, y, pill_w, pill_h, style="DF", round_corners=True, corner_radius=2.6)
    pdf.set_xy(x + 2.2, y + 1.0)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*_hex_rgb(text_c))
    pdf.cell(pill_w - 4.4, 3.8, label, align="C")
    pdf.set_text_color(0, 0, 0)
    return pill_h


def _render_gradio_result_card_frame(pdf: FPDF, y_top: float, y_bottom: float, sentiment: str) -> None:
    """Outer border and left accent bar like .result-card (border + border-left color)."""
    if y_bottom <= y_top + 0.5:
        return
    card_x = pdf.l_margin
    card_w = pdf.w - pdf.l_margin - pdf.r_margin
    h = y_bottom - y_top
    _, _, border_c = sentiment_colors(normalize_sentiment(sentiment))
    br, bgc, bb = _hex_rgb(border_c)
    pdf.set_draw_color(226, 232, 240)
    pdf.rect(card_x, y_top, card_w, h, style="D", round_corners=True, corner_radius=2.2)
    strip_w = 1.9
    pdf.set_fill_color(br, bgc, bb)
    pdf.rect(card_x + 0.35, y_top + 0.35, strip_w, max(0.0, h - 0.7), style="F")


def _render_callout(
    pdf: FPDF,
    title: str,
    body: object,
    *,
    fill: tuple[int, int, int],
    line: tuple[int, int, int],
    text: tuple[int, int, int] = (15, 23, 42),
) -> None:
    clean_body = _pdf_safe_text(str(body or "N/A").strip() or "N/A")
    _ensure_space(pdf, 22)
    x = pdf.l_margin
    y = pdf.get_y()
    w = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.set_fill_color(*fill)
    pdf.set_draw_color(*line)
    pdf.rect(x, y, w, 9, style="DF")
    pdf.set_xy(x + 3, y + 2)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*text)
    pdf.cell(w - 6, 4, _pdf_safe_text(title))
    pdf.set_y(y + 11)
    pdf.set_x(x + 3)
    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(15, 23, 42)
    pdf.multi_cell(w - 6, 5, clean_body, align="L", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)


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

    labels = [(platform, counts.get(platform, 0)) for platform in SEARCH_ACTIVE_PLATFORMS]
    segment_w = (box_w - 8) / max(len(labels), 1)
    for index, (label, value) in enumerate(labels):
        current_x = box_x + 4 + index * segment_w
        pdf.set_xy(current_x, box_y + 10)
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(segment_w, 5, str(value), align="C")
        pdf.set_xy(current_x, box_y + 16)
        pdf.set_font("Helvetica", size=9)
        pdf.cell(segment_w, 4, _pdf_safe_text(label), align="C")

    pdf.set_y(box_y + box_h + 6)


def _suggested_response_body_lines(
    pdf: FPDF,
    words: list[str],
    first_line_max: float,
    continuation_max: float,
) -> list[str]:
    """Word-wrap body for suggested response: line 1 fits after bold prefix; further lines use full card width."""
    pdf.set_font("Helvetica", size=10)
    # Stay below the width used by multi_cell/cell so we never rely on library line-breaking
    # (multi_cell would continue wrapped fragments under the first line instead of at inner_x).
    eps = 1.35
    lines: list[str] = []
    first = True
    idx = 0
    while idx < len(words):
        cap = first_line_max if first else continuation_max
        first = False
        use_cap = max(4.0, cap - eps)
        acc: list[str] = []
        while idx < len(words):
            trial = " ".join(acc + [words[idx]])
            if pdf.get_string_width(trial) <= use_cap:
                acc.append(words[idx])
                idx += 1
            else:
                break
        if acc:
            lines.append(" ".join(acc))
            continue
        word = words[idx]
        segment = ""
        for char in word:
            cand = segment + char
            if pdf.get_string_width(cand) <= use_cap:
                segment = cand
            else:
                break
        if not segment:
            segment = word[0]
        lines.append(segment)
        remainder = word[len(segment) :]
        if remainder:
            words[idx] = remainder
        else:
            idx += 1
    return lines


def _render_detail_suggested_response_inline(
    pdf: FPDF,
    inner_x: float,
    inner_w: float,
    body: str,
    *,
    line_h: float = 5.2,
    gap_after: float = 0.0,
) -> None:
    """Bold 'Suggested response:' then body on same line; wraps with further lines flush at inner_x."""
    body_safe = _pdf_safe_text((body or "").strip() or "N/A")
    words = body_safe.split() or ["N/A"]
    _ensure_space(pdf, line_h * 2)
    pdf.set_font("Helvetica", "B", 10)
    prefix = _pdf_safe_text("Suggested response: ")
    prefix_w = pdf.get_string_width(prefix)
    first_max = max(8.0, inner_w - prefix_w)
    line_strings = _suggested_response_body_lines(pdf, list(words), first_max, inner_w)

    pdf.set_xy(inner_x, pdf.get_y())
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(prefix_w, line_h, prefix, ln=0)
    pdf.set_font("Helvetica", size=10)
    if line_strings:
        w0 = max(6.0, inner_x + inner_w - pdf.get_x())
        # One physical line per entry — avoids multi_cell wrapping under the prefix column.
        pdf.cell(w0, line_h, line_strings[0], align="L", new_x="LMARGIN", new_y="NEXT")
    for extra in line_strings[1:]:
        pdf.set_x(inner_x)
        pdf.cell(inner_w, line_h, extra, align="L", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(inner_x)
    if gap_after > 0:
        pdf.ln(gap_after)


# Render each detailed record block in the PDF section body.
def _render_details(pdf: FPDF, records: list[dict]) -> None:
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(17, 24, 39)
    pdf.cell(0, 8, "Detailed Results", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    strip_and_pad = 1.9 + 3.2
    right_pad = 3.0

    for index, record in enumerate(records):
        _ensure_space(pdf, 52)
        platform = str(record.get("platform") or "Unknown")
        sentiment_key = record.get("sentiment")
        sentiment = normalize_sentiment(sentiment_key)
        kind = str(record.get("kind") or "match").title()
        created = float(record.get("created_utc") or 0)

        card_w = pdf.w - pdf.l_margin - pdf.r_margin
        inner_x = pdf.l_margin + strip_and_pad
        inner_w = max(40.0, card_w - strip_and_pad - right_pad)

        y_top = pdf.get_y()
        pdf.ln(1.2)
        y_cur = y_top + 3.2

        pdf.set_font("Helvetica", "B", 8)
        pill_label = _pdf_safe_text(sentiment)
        pill_w = pdf.get_string_width(pill_label) + 4.5
        pill_x = inner_x + inner_w - pill_w
        pill_y = y_cur
        pill_h = _render_gradio_sentiment_pill(pdf, sentiment_key, pill_x, pill_y)

        pdf.set_xy(inner_x, pill_y + 0.35)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(15, 23, 42)
        plat = _pdf_safe_text(platform)
        plat_slot = max(10.0, inner_w - pill_w - 2.5)
        pdf.cell(plat_slot, 5, plat, ln=0)
        pdf.set_text_color(0, 0, 0)

        y_cur = pill_y + pill_h + 2.6
        pdf.set_xy(inner_x, y_cur)
        pdf.set_font("Helvetica", size=9)
        pdf.set_text_color(100, 116, 139)
        meta = _pdf_safe_text(f"{kind} | {format_timestamp(created)}")
        pdf.multi_cell(inner_w, 4.8, meta, align="L", new_x="LMARGIN", new_y="NEXT")
        pdf.set_x(inner_x)
        pdf.set_text_color(0, 0, 0)

        pdf.ln(1.8)
        pdf.set_x(inner_x)
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(15, 23, 42)
        pdf.multi_cell(
            inner_w,
            6.0,
            _pdf_safe_text(str(record.get("subject", "") or "N/A")),
            align="L",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.set_x(inner_x)
        pdf.set_text_color(0, 0, 0)

        pdf.ln(1.2)
        pdf.set_x(inner_x)
        pdf.set_font("Helvetica", size=10)
        pdf.set_text_color(30, 41, 59)
        pdf.multi_cell(
            inner_w,
            5.2,
            _pdf_safe_text(str(record.get("text", "") or "")),
            align="L",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.set_x(inner_x)
        pdf.set_text_color(0, 0, 0)

        user_val = _pdf_safe_text(str(record.get("user_id", "Unknown")))
        loc_val = _pdf_safe_text(str(record.get("location", "N/A")))
        url = str(record.get("permalink", "") or "").strip()
        link_visible = _pdf_safe_text(link_label(platform))

        pdf.set_xy(inner_x, pdf.get_y())
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(pdf.get_string_width("User: "), 5, "User: ", ln=0)
        pdf.set_font("Helvetica", size=9)
        pdf.cell(pdf.get_string_width(user_val), 5, user_val, ln=0)
        pdf.cell(3.5, 5, "", ln=0)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(pdf.get_string_width("Location: "), 5, "Location: ", ln=0)
        pdf.set_font("Helvetica", size=9)
        pdf.cell(pdf.get_string_width(loc_val), 5, loc_val, ln=0)
        if url:
            gap_before_link = 3.5
            link_w = pdf.get_string_width(link_visible)
            right_edge = pdf.w - pdf.r_margin
            if pdf.get_x() + gap_before_link + link_w > right_edge:
                pdf.ln(5)
                pdf.set_x(inner_x)
            else:
                pdf.cell(gap_before_link, 5, "", ln=0)
            pdf.set_text_color(0, 102, 204)
            pdf.set_font("Helvetica", "U", 9)
            pdf.cell(link_w, 5, link_visible, link=url, ln=1)
            pdf.set_font("Helvetica", size=9)
        else:
            pdf.ln(5)
        pdf.set_text_color(0, 0, 0)

        pdf.ln(5.2)
        _render_detail_suggested_response_inline(
            pdf,
            inner_x,
            inner_w,
            str(record.get("response", "") or "N/A"),
            line_h=5.2,
            gap_after=0.0,
        )
        pdf.set_text_color(0, 0, 0)

        y_bottom = pdf.get_y() + 3.2
        _render_gradio_result_card_frame(pdf, y_top, y_bottom, sentiment_key)
        pdf.set_y(y_bottom + 3.0)

        if index < len(records) - 1:
            pdf.ln(0.5)


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
    _render_dashboard_header(pdf, clean_keyword)
    _render_topic_overview(pdf, records)
    _render_sentiment_dashboard_panel(pdf, records)
    _render_location_dashboard_panel(pdf, records)
    _render_marketing_insights(pdf, records, clean_keyword)

    for index, platform in enumerate(SEARCH_ACTIVE_PLATFORMS):
        platform_records = [record for record in records if record.get("platform") == platform]
        _render_platform_section(pdf, platform, platform_records, add_page=True)

    basename = _pdf_export_basename()
    pdf_path = os.path.join(tempfile.gettempdir(), basename)
    pdf.output(pdf_path)

    return "PDF is ready to download.", pdf_path
