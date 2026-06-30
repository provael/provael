"""Provael interactive demo — a Hugging Face Space (Gradio).

Run a CPU red-team scan in the browser: pick a recipe, get the ASR table + the one-page scorecard.
Zero install for the visitor, shareable URL — the conference-demo / drive-by surface. No GPU.

    pip install gradio provael
    python examples/hf-space/app.py
"""

from __future__ import annotations

import gradio as gr

from provael.config import RunConfig
from provael.recipes import available_recipes, load_recipe
from provael.runner import run
from provael.scorecard import to_scorecard_markdown


def scan(recipe: str, threshold: float) -> tuple[list[list[str]], str]:
    """Run the chosen recipe on the CPU stub; return (ASR rows, scorecard markdown)."""
    cfg = {"policy": "stub", "suite": "stub", **load_recipe(recipe)}
    report = run(RunConfig.model_validate(cfg))
    rows = [
        [name, report.eai.get(name).id if name in report.eai else "—",
         f"{100.0 * stat.asr:.1f}%", f"{stat.successes}/{stat.attempts}"]
        for name, stat in report.by_attack.items()
    ]
    return rows, to_scorecard_markdown(report, threshold)


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="Provael demo") as demo:
        gr.Markdown(
            "# 🦾 Provael — try a VLA red-team scan\n"
            "Runs on the deterministic CPU **stub** (numbers are fixture properties, not a real "
            "VLA). Pick a recipe and scan."
        )
        with gr.Row():
            recipe = gr.Dropdown(available_recipes(), value="full-sweep", label="Recipe")
            threshold = gr.Slider(0.0, 1.0, value=0.5, step=0.05, label="Pass/fail threshold")
        button = gr.Button("Run scan", variant="primary")
        table = gr.Dataframe(headers=["attack", "EAI", "ASR", "s/n"], datatype="str", wrap=True)
        scorecard = gr.Markdown()
        button.click(scan, inputs=[recipe, threshold], outputs=[table, scorecard])
    return demo


if __name__ == "__main__":
    build_demo().launch()
