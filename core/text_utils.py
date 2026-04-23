"""
Text normalization helpers for Sentiment Analyzer.
"""

from __future__ import annotations

import html
import re


# Clean raw social text into a comparable, display-ready string.
def clean_text(*parts: str) -> str:
    text = "\n\n".join(part.strip() for part in parts if part and part.strip())
    text = html.unescape(text).replace("\r", "\n")
    text = text.replace("\\n", " ").replace("\\t", " ").replace('\\"', '"')
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[*_~`#]+", " ", text)
    text = re.sub(r"^\s*>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# Match a keyword as a standalone term instead of a substring.
def contains_exact_keyword(text: str, keyword: str) -> bool:
    clean_body = clean_text(text)
    clean_keyword = clean_text(keyword)
    if not clean_body or not clean_keyword:
        return False
    pattern = re.compile(rf"(?<!\w){re.escape(clean_keyword)}(?!\w)", re.IGNORECASE)
    return bool(pattern.search(clean_body))
