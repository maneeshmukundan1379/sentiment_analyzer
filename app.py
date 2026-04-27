"""
Gradio entrypoint for Sentiment Analyzer.
"""

import gradio as gr

from core.platforms import platform_scope_text
from core.time_window import lookback_last_text
from logic import generate_pdf_report, search_social_keyword


# Build the Gradio interface and wire it to the search/export callbacks.
def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Sentiment Analyzer") as demo:
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
        results = gr.Textbox(
            label="Matching Social Posts and Comments",
            lines=24,
            max_lines=40,
        )
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
    demo.launch(share=True)
