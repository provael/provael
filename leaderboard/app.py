"""Provael ASR leaderboard — Hugging Face Space (Gradio).

Renders the committed ``results/*.json`` (from ``provael leaderboard build``) as a ranked table
with a RoboArena-style **all-policies vs. open-source-policies** split, example attacked payloads,
and an **open-submission** tab that opens a PR to a requests dataset for review
(Open-LLM-Leaderboard pattern). No GPU is used to *view*; submissions are validated offline by a
maintainer before promotion.

Both the Hub client and ZeroGPU are imported lazily/guarded so this app also runs locally with
``python app.py`` (submission is disabled without ``HF_TOKEN``).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import gradio as gr

try:  # Available on Hugging Face ZeroGPU Spaces; absent locally.
    import spaces  # noqa: F401  (kept for a future @spaces.GPU live-run button)
except ImportError:  # pragma: no cover - environment dependent
    spaces = None  # type: ignore[assignment]

RESULTS_DIR = Path(__file__).parent / "results"

#: The requests dataset a submission opens a PR against (Open-LLM-Leaderboard pattern).
REQUESTS_REPO = "provael-submissions/requests"

#: Policies considered open-source (weights available) — drives the RoboArena-style split.
OPEN_SOURCE_POLICIES = frozenset(
    {"stub", "smolvla", "pi0", "pi05", "pi0fast", "groot", "openvla"}
)

ROW_HEADERS = ["rank", "policy", "suite", "family", "ASR", "successes", "attempts"]
EXAMPLE_HEADERS = ["family", "attack", "example adversarial payload"]


def _load_results() -> tuple[list[dict], list[dict], bool]:
    """Load and merge every results JSON file. Returns (rows, examples, is_demo)."""
    rows: list[dict] = []
    examples: dict[str, dict] = {}
    real_seen = False
    for path in sorted(RESULTS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        rows.extend(data.get("rows", []))
        for example in data.get("examples", []):
            examples.setdefault(example["attack"], example)
        if not data.get("is_demo", True):
            real_seen = True
    rows.sort(key=lambda r: (-r["asr"], r["policy"], r["suite"], r["family"]))
    ordered_examples = sorted(examples.values(), key=lambda e: (e["family"], e["attack"]))
    return rows, ordered_examples, not real_seen


def _row_table(rows: list[dict]) -> list[list[str]]:
    return [
        [
            str(rank), r["policy"], r["suite"], r["family"],
            f"{100.0 * r['asr']:.1f}%", str(r["successes"]), str(r["attempts"]),
        ]
        for rank, r in enumerate(rows, start=1)
    ]


def _example_table(examples: list[dict]) -> list[list[str]]:
    return [[e["family"], e["attack"], e["example"]] for e in examples]


def submit_result(model_id: str, results_file: str | None) -> str:
    """Open a PR to the requests dataset with a submitted results JSON (queued for review)."""
    if not model_id or results_file is None:
        return "Provide a model id and a `provael` results JSON file."
    try:
        from huggingface_hub import HfApi
    except ImportError:  # pragma: no cover - environment dependent
        return "huggingface_hub not available — run on the Space (or pip install huggingface_hub)."
    token = os.environ.get("HF_TOKEN")
    if not token:
        return (
            "Submission queue disabled locally: set HF_TOKEN on the Space. Submitting opens a PR "
            f"to `{REQUESTS_REPO}` for a maintainer to validate and promote."
        )
    api = HfApi(token=token)  # pragma: no cover - requires a live token
    api.upload_file(
        path_or_fileobj=results_file,
        path_in_repo=f"requests/{model_id.replace('/', '__')}.json",
        repo_id=REQUESTS_REPO,
        repo_type="dataset",
        create_pr=True,
    )
    return f"Submitted — a PR was opened on `{REQUESTS_REPO}` for review."


_DEMO_BANNER = (
    "> ⚠️ **Demo data.** These results come from the deterministic CPU **stub** policy, not a "
    "real model. Illustrative until real-model runs are added (GPU command in the README)."
)
_REAL_BANNER = "> ✅ Includes real-model results."
_INTRO = (
    "# 🦾 Provael — VLA Red-Team ASR Leaderboard\n\n"
    "Attack Success Rate (ASR) of templated attacks against Vision-Language-Action robot "
    "policies in simulation. **Lower ASR = more robust.**\n"
)


def _table(rows: list[dict]) -> gr.Dataframe:
    return gr.Dataframe(
        value=_row_table(rows), headers=ROW_HEADERS, datatype="str", interactive=False, wrap=True
    )


def build_demo() -> gr.Blocks:
    rows, examples, is_demo = _load_results()
    open_rows = [r for r in rows if r["policy"] in OPEN_SOURCE_POLICIES]
    with gr.Blocks(title="Provael ASR Leaderboard") as demo:
        gr.Markdown(_INTRO)
        gr.Markdown(_DEMO_BANNER if is_demo else _REAL_BANNER)
        with gr.Tabs():
            with gr.Tab("All policies"):
                _table(rows)
            with gr.Tab("Open-source policies"):
                _table(open_rows)
            with gr.Tab("Example payloads"):
                gr.Dataframe(
                    value=_example_table(examples), headers=EXAMPLE_HEADERS,
                    datatype="str", interactive=False, wrap=True,
                )
            with gr.Tab("Submit a result"):
                gr.Markdown(
                    "Submit a `provael leaderboard build` results JSON. It opens a PR to "
                    f"`{REQUESTS_REPO}`; a maintainer validates and promotes it."
                )
                model_in = gr.Textbox(label="Model id (e.g. org/my-vla)")
                file_in = gr.File(label="results JSON", type="filepath")
                out = gr.Markdown()
                gr.Button("Submit", variant="primary").click(
                    submit_result, inputs=[model_in, file_in], outputs=out
                )
        gr.Markdown(
            "Built with [`provael`](https://github.com/provael/provael) — "
            "`provael leaderboard build`. Apache-2.0."
        )
    return demo


if __name__ == "__main__":
    build_demo().launch()
