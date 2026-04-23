# Sentiment Analyzer Documentation

## Overview
`Sentiment Analyzer` is a Gradio-based app that searches Reddit, X.com, and Facebook pages/groups for a keyword, uses Gemini to confirm relevant matches, generates `sentiment` plus a suggested response for each matching record, and lets the user export the results as a PDF report with separate platform sections.

## What The App Does
- Accepts a keyword from the user.
- Searches Reddit using public Reddit JSON endpoints.
- Searches X.com primarily through the official authenticated X recent-search API, with a strict public web-search fallback.
- Searches Facebook by discovering candidate group and page URLs from the keyword at runtime, then attempts deeper fetches through `facebook-scraper`, with a public web-search fallback.
- Normalizes all sources into one shared record format.
- Uses Gemini agents to confirm relevant matches and infer `sentiment`, `location`, and a suggested response.
- Shows the final matching posts/comments inside the Gradio UI.
- Generates a downloadable PDF report with separate `Reddit`, `Facebook`, and `X.com` sections.

## Project Files
- `app.py`: Gradio UI entrypoint and event wiring.
- `logic.py`: Thin orchestration layer that runs the three platform searches concurrently and returns the Gradio callback payload.
- `core/`: Shared record, text normalization, formatting, config, and web-search helpers.
- `platform_agents/reddit_agent.py`: Reddit collection and pre-enrichment filtering.
- `platform_agents/x_agent.py`: X.com collection and pre-enrichment filtering.
- `platform_agents/facebook_agent.py`: Facebook pages/groups discovery, collection, and pre-enrichment filtering.
- `platform_agents/enrichment_agent.py`: Shared Gemini relevance filtering and final sentiment/location/response enrichment.
- `platform_agents/pdf_agent.py`: Final PDF aggregation and rendering.
- `social_agents.py`: Backward-compatible re-export module for the refactored Gemini layer.
- `requirements.txt`: Python dependencies.

## Requirements
- Python `3.10+`
- A Gemini-compatible API key set as `GEMINI_API_KEY` or `GOOGLE_API_KEY`
- For reliable X.com results, an `X_BEARER_TOKEN`

## Optional Environment Settings
Create a `.env` file in the project directory:

```env
GEMINI_API_KEY=your_api_key_here
# Optional overrides:
# GOOGLE_API_KEY=your_api_key_here
# GEMINI_MODEL=gemini-3.1-flash-lite-preview
# GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
# X_BEARER_TOKEN=your_x_bearer_token_here
# X_API_BASE_URL=https://api.x.com/2
# SOCIAL_LOOKBACK_DAYS=7
# FACEBOOK_GROUP_PAGES=5  # optional manual cap; omit for no fixed page-depth limit
```

## Installation
```bash
cd /Users/maneeshmukundan/projects/agents/2_openai/sentiment_analyzer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run The App
```bash
python app.py
```

## Notes
- The Gradio interface keeps the same simple one-keyword search flow as the Reddit Scroller app.
- Reddit results are the most direct because they come from Reddit's public JSON endpoints.
- X.com now prefers the official authenticated recent-search API when `X_BEARER_TOKEN` is configured and only falls back to public search when needed.
- The X.com fallback only keeps real `x.com` or `twitter.com` status URLs.
- Facebook is still more fragile on the public web, so the app includes best-effort fallbacks when direct scraping is unavailable.
- Facebook no longer needs pre-stored group IDs or cookie files. The app discovers candidate groups and pages at runtime from the keyword and, when possible, asks `facebook-scraper` to use browser-session cookies directly in memory.
- By default, Facebook scanning is no longer capped at 2 pages. Set `FACEBOOK_GROUP_PAGES` only if you want to impose your own manual limit.
- Reddit, X.com, and Facebook searches now run concurrently, then the merged result set is enriched once before the UI and PDF are generated.
- App-level numeric caps for X.com and public web discovery have been removed; the built-in time filter is controlled centrally by `SOCIAL_LOOKBACK_DAYS`.
- You can create `X_BEARER_TOKEN` from the [X Developer Console](https://console.x.com).
