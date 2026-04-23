# Sentiment Analyzer Architecture

This document shows how the `Sentiment Analyzer` application executes, which Python files are involved, and what each file does during runtime.

## Execution Overview

There are two main user flows:

1. `Search`
   - Collect records from Reddit, X.com, and Facebook
   - Filter and enrich them with Gemini
   - Return formatted results to the Gradio UI

2. `Download PDF`
   - Reuse the serialized search results already stored in UI state
   - Build a PDF with a cover page and platform sections

## Runtime Architecture

```text
+------------------------------+
| User                         |
| Starts a search or requests  |
| a PDF download               |
+------------------------------+
               |
               v
+------------------------------+
| app.py                       |
| Shows the Gradio UI and      |
| routes button actions        |
+------------------------------+
        | Search                               | Download PDF
        v                                      v
+------------------------------+      +------------------------------+
| logic.py                     |      | platform_agents/pdf_agent.py |
| Runs the search workflow and |      | Builds the final PDF from    |
| prepares UI output           |      | saved search results         |
+------------------------------+      +------------------------------+
               |
               v
+------------------------------+      +------------------------------+
| reddit_agent.py              |      | x_agent.py                   |
| Collects matching Reddit     |      | Collects matching X posts,   |
| posts and comments           |      | using the API first          |
+------------------------------+      +------------------------------+
               |                              |
               v                              v
[Reddit public JSON endpoints]        [Official X API]
                                             |
                                             v
                                   [Public X web fallback]

+------------------------------+      +------------------------------+
| facebook_agent.py            |      | enrichment_agent.py          |
| Collects matching Facebook   |      | Uses Gemini to keep relevant |
| posts and comments           |      | records and enrich metadata  |
+------------------------------+      +------------------------------+
               |                              |
               v                              v
[facebook-scraper]                    [base_agent.py]
               |                      runs Gemini model calls
               v                              |
[Public Facebook web fallback]               v
                                       [Gemini model provider]


Shared support modules used across the runtime path:

  [core/env.py] -------- loads .env values before the app runs
  [core/config.py] ----- stores shared settings like lookback and API values
  [core/time_window.py] - calculates the shared search date window
  [core/text_utils.py] -- cleans text and checks keyword matches
  [core/records.py] ---- builds the common record format for all platforms
  [core/formatting.py] - formats, sorts, and counts records for display
  [core/platforms.py] -- keeps platform labels consistent
  [core/web_search.py] - handles fallback web-search lookups


Final output path:

  Search:
    collectors -> merge -> dedupe/sort -> Gemini filter -> Gemini enrich -> UI + serialized state

  PDF:
    serialized state -> pdf_agent.py -> cover page + platform sections -> generated PDF
```

## Search Flow

```text
+------------------------------+     +------------------------------+     +------------------------------+
| app.py                       | --> | logic.py                     | --> | Platform collectors          |
| Receives the user search     |     | Coordinates the search       |     | Gather Reddit, X, and        |
| action from the UI           |     | process                      |     | Facebook candidates          |
+------------------------------+     +------------------------------+     +------------------------------+
                                                                                   |
                                                                                   v
                                                                +------------------------------+
                                                                | Deduplicate and sort         |
                                                                | Remove duplicates and order  |
                                                                | newest records first         |
                                                                +------------------------------+
                                                                                   |
                                                                                   v
                                                                +------------------------------+
                                                                | Gemini match filtering       |
                                                                | Keep only records truly      |
                                                                | related to the keyword       |
                                                                +------------------------------+
                                                                                   |
                                                                                   v
                                                                +------------------------------+
                                                                | Gemini enrichment            |
                                                                | Add sentiment, location, and |
                                                                | a suggested response         |
                                                                +------------------------------+
                                                                           |                |
                                                                           v                v
                                                     +--------------------------------+   +------------------------------+
                                                     | Results textbox                |   | Serialized UI state          |
                                                     | Show the final search results  |   | Save results for PDF export  |
                                                     +--------------------------------+   +------------------------------+
```

## PDF Flow

```text
+------------------------------+     +------------------------------+     +------------------------------+
| app.py                       | --> | Serialized records state     | --> | platform_agents/pdf_agent.py |
| Handles the PDF download     |     | Reuses the last search       |     | Builds the PDF layout and    |
| request from the UI          |     | output already in memory     |     | writes the report file       |
+------------------------------+     +------------------------------+     +------------------------------+
                                                                                   |
                                                                                   v
                                                                +------------------------------+
                                                                | Cover page                   |
                                                                | Show title, generated time,  |
                                                                | and platform count box       |
                                                                +------------------------------+
                                                                                   |
                                                                                   v
                                                                +------------------------------+
                                                                | Platform sections            |
                                                                | Render separate Reddit,      |
                                                                | Facebook, and X.com details  |
                                                                +------------------------------+
                                                                                   |
                                                                                   v
                                                                +------------------------------+
                                                                | Downloadable PDF file        |
                                                                | Return the final report      |
                                                                | to the user                  |
                                                                +------------------------------+
```

## File Responsibilities

### Entry and Orchestration

- `app.py`
  - Gradio entrypoint.
  - Builds the UI.
  - Wires `Search` to `logic.search_social_keyword()`.
  - Wires `Download PDF` to `platform_agents.pdf_agent.generate_pdf_report()`.

- `logic.py`
  - Main runtime orchestrator for search.
  - Runs the three platform collectors concurrently.
  - Merges, deduplicates, sorts, and enriches records.
  - Returns the final status string, formatted text output, and serialized record payload for the UI.

- `social_agents.py`
  - Compatibility re-export module.
  - Not part of the active main execution path for the UI, but preserves older import paths.

### Platform Collection and AI

- `platform_agents/reddit_agent.py`
  - Searches Reddit via public Reddit JSON endpoints.
  - Collects matching submissions and matching comments.
  - Normalizes results into the shared record format.
  - Uses Gemini match filtering before returning results.

- `platform_agents/x_agent.py`
  - Searches X.com through the official authenticated X API first.
  - Falls back to strict public X/Twitter status-link search if necessary.
  - Normalizes X results into the shared record format.
  - Tracks warning text for fallback/API failures.

- `platform_agents/facebook_agent.py`
  - Discovers candidate Facebook groups and pages from public search.
  - Tries `facebook-scraper` first for posts and comments.
  - Falls back to public web discovery if scraping yields nothing.
  - Preserves timestamps when available and normalizes Facebook post/comment results.

- `platform_agents/enrichment_agent.py`
  - Defines the Gemini schemas and agents.
  - Filters weak or off-topic keyword matches.
  - Enriches retained records with sentiment, location, and suggested response.

- `platform_agents/base_agent.py`
  - Shared Gemini runtime layer.
  - Loads environment-backed Gemini config.
  - Creates the Gemini model client and runs typed agent calls with retries.

- `platform_agents/pdf_agent.py`
  - Generates the final PDF report from serialized records.
  - Builds the title block, first-page count box, and platform sections.
  - Renders detailed record blocks for each platform.

### Shared Core Utilities

- `core/env.py`
  - Centralized `.env` discovery and loading.
  - Supports explicit env file override plus upward directory search.

- `core/config.py`
  - Reads shared runtime configuration from environment variables.
  - Exposes lookback and integration settings as module-level constants.

- `core/platforms.py`
  - Central source of platform labels and ordering.
  - Prevents naming drift such as `Facebook` vs `Facebook Groups`.

- `core/time_window.py`
  - Shared time-window logic.
  - Converts `LOOKBACK_DAYS` into timestamps and provider-specific time filters.

- `core/text_utils.py`
  - Cleans and normalizes text from all platforms.
  - Performs exact keyword matching.

- `core/records.py`
  - Defines the normalized record structure used throughout the app.
  - Contains helper builders for Reddit, X.com, Facebook posts, and Facebook comments.
  - Serializes/deserializes record payloads for Gradio state and PDF generation.

- `core/formatting.py`
  - Formats results for the UI textbox.
  - Deduplicates and sorts records.
  - Produces consistent timestamp and link-label output.

- `core/web_search.py`
  - Shared public search abstraction for Serper and DuckDuckGo.
  - Used mainly by X and Facebook fallback discovery.

### Package Marker Modules

- `core/__init__.py`
  - Package marker only.
  - No execution logic.

- `platform_agents/__init__.py`
  - Package marker only.
  - No execution logic.

## What Runs During a Normal Search

The files actively involved in a standard search request are:

- `app.py`
- `logic.py`
- `platform_agents/reddit_agent.py`
- `platform_agents/x_agent.py`
- `platform_agents/facebook_agent.py`
- `platform_agents/enrichment_agent.py`
- `platform_agents/base_agent.py`
- `core/config.py`
- `core/env.py`
- `core/records.py`
- `core/formatting.py`
- `core/text_utils.py`
- `core/time_window.py`
- `core/platforms.py`
- `core/web_search.py`

## What Runs During PDF Export

The files actively involved in PDF generation are:

- `app.py`
- `platform_agents/pdf_agent.py`
- `core/records.py`
- `core/formatting.py`
- `core/platforms.py`

## High-Level Design Notes

- The app is intentionally split into:
  - UI entrypoint
  - orchestration
  - platform collectors
  - Gemini enrichment
  - shared core utilities
  - PDF rendering

- All platform agents return the same normalized record structure.
  - This is what makes shared enrichment, shared UI formatting, and shared PDF generation possible.

- X.com and Facebook use fallback discovery because their official/public access paths are more fragile than Reddit.

- The PDF generator does not recollect data.
  - It only consumes the serialized result payload already produced by the search flow.
