"""Q&A engine — question answering, output rendering, feedback filing."""

from compendium.qa.engine import ask_question
from compendium.qa.filing import file_to_wiki
from compendium.qa.output import render_chart_bundle, render_html, render_report, render_slides

__all__ = [
    "ask_question",
    "file_to_wiki",
    "render_chart_bundle",
    "render_html",
    "render_report",
    "render_slides",
]
