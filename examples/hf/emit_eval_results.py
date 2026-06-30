"""Emit a Provael ASR as a Hugging Face eval result for a policy's model page.

Pushing ASR onto the model card (and, via PR, onto *other* people's VLA models) makes Provael
self-distributing and feeds the leaderboard flywheel. This writes the modern `.eval_results`
YAML shape (https://huggingface.co/docs/hub/eval-results) locally; uploading it to a repo is a
separate, deliberate step (writing to someone else's repo is gated — open a PR, don't push).

    pip install huggingface_hub provael
    python examples/hf/emit_eval_results.py            # writes eval_results.yaml locally

On a box without huggingface_hub it still writes the YAML (it's just text).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from provael import __version__
from provael.config import RunConfig
from provael.runner import run


def build_eval_result(model_id: str, suite: str) -> dict[str, object]:
    report = run(
        RunConfig(
            policy="stub", suite=suite,
            attacks=["instruction", "visual", "injection", "action"], episodes=10, seed=0,
        )
    )
    # The eval-results shape: a benchmark + task + metric record keyed to the model.
    return {
        "model": model_id,
        "results": [
            {
                "task": {"type": "vla-red-team", "name": "Provael VLA red-team"},
                "dataset": {"type": f"provael/{suite}", "name": f"Provael {suite} suite"},
                "metrics": [
                    {"type": "attack-success-rate", "name": "ASR", "value": round(report.asr, 4)}
                ],
                "source": {"name": f"Provael {__version__}", "url": "https://github.com/provael/provael"},
            }
        ],
    }


def main() -> None:
    record = build_eval_result(model_id="lerobot/smolvla_base", suite="stub")
    out = Path("eval_results.yaml")
    out.write_text(yaml.safe_dump(record, sort_keys=False), encoding="utf-8")
    print(f"Wrote {out} (ASR={record['results'][0]['metrics'][0]['value']}).")  # type: ignore[index]
    print(
        "To publish: open a PR adding this to the model's card metadata "
        "(writing to another org's repo is gated — never push directly)."
    )


if __name__ == "__main__":
    main()
