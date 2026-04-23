# Sentiment Analyzer User Guide

## Purpose
Use `Sentiment Analyzer` to search Reddit, X.com, and Facebook pages/groups for a keyword within the configured social lookback window, review matching posts/comments, and download the enriched results as a PDF report.

## Before You Start
You need:
- Python `3.10+`
- Internet access
- A valid `GEMINI_API_KEY` or `GOOGLE_API_KEY`
- For reliable X.com results, an `X_BEARER_TOKEN`

## Setup

### 1. Install dependencies
```bash
cd /Users/maneeshmukundan/projects/agents/2_openai/sentiment_analyzer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure your API key
Create a `.env` file in the same folder:

```env
GEMINI_API_KEY=your_api_key_here
X_BEARER_TOKEN=your_x_bearer_token_here
```

You can also use:

```env
GOOGLE_API_KEY=your_api_key_here
# Optional:
# X_API_BASE_URL=https://api.x.com/2
# SOCIAL_LOOKBACK_DAYS=7
# FACEBOOK_GROUP_PAGES=5
```

### 3. Launch the application
```bash
python app.py
```

## Screen Overview
The app keeps the same simple UI pattern as the original Reddit Scroller app:

1. `Keyword`
Enter the word or phrase you want to search.

2. `Search`
Starts the Reddit, X.com, and Facebook workflow.

3. `Download PDF`
Exports the current visible results into a PDF file.

4. `Status`
Shows instructions, success messages, empty-state messages, or errors.

5. `Results`
Displays the formatted social records, including platform, date, user ID, location, sentiment, text, and source link.

## How To Use The App

### Search for a keyword
1. Type a keyword such as `openai`, `layoffs`, `elections`, or `tesla`.
2. Click `Search` or press `Enter`.
3. Wait for the app to:
   - search Reddit
   - search X.com
   - search Facebook pages and groups
   - confirm relevant matches with Gemini
   - enrich records with sentiment and location
4. Read the `Status` area for the result count.
5. Review the records in the `Results` textbox.

### Download a PDF report
1. Run a search first.
2. Click `Download PDF`.
3. Wait for the `PDF is ready to download.` message.
4. Use the `PDF Report` file control to download the generated file.

## Notes
- The PDF contains separate sections for `Reddit`, `Facebook`, and `X.com`.
- Reddit is the strongest source because it uses public Reddit endpoints directly.
- X.com now prefers the official authenticated recent-search API and falls back to strict public status-link discovery only when needed.
- If you want reliable X.com coverage for newly posted comments or replies, configure `X_BEARER_TOKEN` from the [X Developer Console](https://console.x.com).
- Facebook now runs fully at runtime: it discovers candidate groups and pages from the keyword and attempts browser-session access without requiring stored group IDs or a cookie file in `.env`.
- Facebook scanning is uncapped by default. You can optionally set `FACEBOOK_GROUP_PAGES` in `.env` only if you want to add your own manual limit.
- Reddit, X.com, and Facebook searches run in parallel, then the app merges those results and builds one PDF with three platform sections.
- The app no longer applies built-in numeric caps for X.com or public web discovery; the built-in time filter is controlled centrally by `SOCIAL_LOOKBACK_DAYS`.
