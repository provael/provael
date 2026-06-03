"""RoboPwn ASR leaderboard — Hugging Face Space (Gradio, ZeroGPU-compatible).

v0 is a STATIC-DATA viewer: it renders the committed ``results/*.json`` files
(produced by ``robopwn leaderboard build``) as a ranked table plus example attacked
payloads. No GPU is used. When every aggregated run used the ``stub`` policy, a clear
"demo data" banner is shown — the numbers are illustrative until real SmolVLA / OpenVLA
runs are added.

ZeroGPU: a future "run a live attack" button would call a function decorated with
``@spaces.GPU`` (see the commented stub at the bottom). The import is guarded so this
app also runs locally with ``python app.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import gradio as gr

try:  # Available on Hugging Face ZeroGPU Spaces; absent locally.
    import spaces  # noqa: F401  (kept available for a future @spaces.GPU live-run button)
except ImportError:  # pragma: no cover - environment dependent
    spaces = None  # type: ignore[assignment]

RESULTS_DIR = Path(__file__).parent / "results"

ROW_HEADERS = ["rank", "policy", "suite", "family", "ASR", "successes", "attempts"]
EXAMPLE_HEADERS = ["family", "attack", "example adversarial payload"]


def _load_results() -> tuple[list[dict], list[dict], bool]:
    """Load and merge every results JSON file. Returns (rows, examples, is_demo)."""
    rows: list[dict] = []
    examples: dict[str, dict] = {}
    is_demo = True
    real_seen = False
    for path in sorted(RESULTS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        rows.extend(data.get("rows", []))
        for example in data.get("examples", []):
            examples.setdefault(example["attack"], example)
        if not data.get("is_demo", True):
            real_seen = True
    if real_seen:
        is_demo = False
    # Rank across all merged rows (ASR desc, then keys) for a stable order.
    rows.sort(key=lambda r: (-r["asr"], r["policy"], r["suite"], r["family"]))
    ordered_examples = sorted(examples.values(), key=lambda e: (e["family"], e["attack"]))
    return rows, ordered_examples, is_demo


def _row_table(rows: list[dict]) -> list[list[str]]:
    return [
        [
            str(rank),
            r["policy"],
            r["suite"],
            r["family"],
            f"{100.0 * r['asr']:.1f}%",
            str(r["successes"]),
            str(r["attempts"]),
        ]
        for rank, r in enumerate(rows, start=1)
    ]


def _example_table(examples: list[dict]) -> list[list[str]]:
    return [[e["family"], e["attack"], e["example"]] for e in examples]


_DEMO_BANNER = (
    "> ⚠️ **Demo data.** These results come from the deterministic CPU **stub** policy, "
    "not a real model. They are illustrative until real SmolVLA / OpenVLA runs are added. "
    "Reproduce/extend with the GPU command in the README."
)
_REAL_BANNER = "> ✅ Includes real-model results."

_INTRO = (
    "# 🦾 RoboPwn — VLA Red-Team ASR Leaderboard\n\n"
    "Attack Success Rate (ASR) of instruction / visual / injection attacks against "
    "Vision-Language-Action robot policies in simulation. Lower ASR = more robust.\n"
)


def build_demo() -> gr.Blocks:
    rows, examples, is_demo = _load_results()
    with gr.Blocks(title="RoboPwn ASR Leaderboard") as demo:
        gr.Markdown(_INTRO)
        gr.Markdown(_DEMO_BANNER if is_demo else _REAL_BANNER)
        gr.Markdown("## Ranked ASR (policy × suite × family)")
        gr.Dataframe(
            value=_row_table(rows),
            headers=ROW_HEADERS,
            datatype="str",
            interactive=False,
            wrap=True,
        )
        gr.Markdown("## Example adversarial payloads")
        gr.Dataframe(
            value=_example_table(examples),
            headers=EXAMPLE_HEADERS,
            datatype="str",
            interactive=False,
            wrap=True,
        )
        gr.Markdown(
            "Built with [`vla-redteam`](https://github.com/sattyamjjain/vla-redteam) — "
            "`robopwn leaderboard build`. Apache-2.0."
        )
    return demo


# --- ZeroGPU live-run placeholder (v0: unused; static data only) -------------
# When wired, a "run a live attack" button would call something like:
#
#   @spaces.GPU(duration=120)
#   def run_live(policy: str, suite: str, attacks: str, seed: int) -> list[list[str]]:
#       from vla_redteam.config import RunConfig
#       from vla_redteam.runner import run
#       report = run(RunConfig(policy=policy, suite=suite,
#                              attacks=attacks.split(","), seed=seed))
#       return [[a, f"{s.asr:.2%}"] for a, s in report.by_attack.items()]
#
# It needs the [lerobot] extra + a GPU, so it is intentionally NOT enabled in v0.


if __name__ == "__main__":
    build_demo().launch()
