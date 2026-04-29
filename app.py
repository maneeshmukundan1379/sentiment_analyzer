"""
Gradio entrypoint for Sentiment Analyzer.
"""

import os

import gradio as gr

from core.platforms import platform_scope_text
from core.time_window import lookback_last_text
from logic import generate_pdf_report, search_social_keyword


APP_CSS = """
.results-grid {
    display: grid;
    gap: 12px;
}
.result-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-left: 6px solid #64748b;
    border-radius: 8px;
    padding: 14px 16px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
}
.result-card__topline,
.result-card__details {
    align-items: center;
    display: flex;
    flex-wrap: wrap;
    gap: 8px 12px;
}
.result-card__topline {
    justify-content: space-between;
}
.result-card h3 {
    color: #0f172a;
    font-size: 16px;
    line-height: 1.35;
    margin: 8px 0 6px;
}
.result-card__meta,
.result-card__details {
    color: #64748b;
    font-size: 13px;
}
.result-card__text {
    color: #1e293b;
    line-height: 1.5;
    margin: 0 0 10px;
    white-space: pre-wrap;
}
.sentiment-pill {
    border: 1px solid;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 700;
    padding: 3px 9px;
}
.empty-results {
    border: 1px dashed #cbd5e1;
    border-radius: 8px;
    color: #475569;
    padding: 16px;
}
"""


# Build the Gradio interface and wire it to the search/export callbacks.
def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Sentiment Analyzer", css=APP_CSS) as demo:
        # Explain the app flow at the top of the page.
        gr.Markdown(
            "# Sentiment Analyzer\n"
            f"Use Gemini in two steps: first to confirm matching {platform_scope_text()} posts "
            f"from the {lookback_last_text()}, then to analyze sentiment, infer location, and generate suggested replies "
            "for the PDF report."
        )
        # Collect the search term and hold the serialized result state between actions.
        keyword = gr.Textbox(
            label="Keyword",
            placeholder="e.g. openai, layoffs, elections, tesla",
        )
        search_btn = gr.Button("Search", variant="primary")
        download_btn = gr.Button("Download PDF")
        status = gr.Markdown("Enter a keyword and click **Search**.")
        searched_keyword = gr.State("")
        records_payload = gr.State("[]")
        results = gr.HTML(label="Matching Social Posts and Comments")
        pdf_file = gr.File(label="PDF Report")

        # Route both button clicks and Enter presses through the same search logic.
        search_btn.click(
            search_social_keyword,
            inputs=[keyword],
            outputs=[status, results, keyword, searched_keyword, records_payload],
        )
        keyword.submit(
            search_social_keyword,
            inputs=[keyword],
            outputs=[status, results, keyword, searched_keyword, records_payload],
        )
        # Build the PDF from the most recent serialized search results.
        download_btn.click(
            generate_pdf_report,
            inputs=[records_payload, searched_keyword],
            outputs=[status, pdf_file],
        )
    return demo


# Instantiate the UI once so the module can be launched directly.
demo = build_ui()

# Start a shareable Gradio app when the file is run as a script.
if __name__ == "__main__":
    demo.launch(
        server_name=os.getenv("GRADIO_SERVER_NAME", "0.0.0.0"),
        server_port=int(os.getenv("PORT", os.getenv("GRADIO_SERVER_PORT", "7860"))),
        share=(os.getenv("GRADIO_SHARE", "").lower() in {"1", "true", "yes"}),
    )
