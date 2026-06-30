"""A promptfoo custom provider that runs a Provael VLA red-team scan.

promptfoo (https://www.promptfoo.dev) is a widely-used LLM red-team / eval runner. Its custom
*Python provider* lets you score anything behind one `call_api` function, so this file makes
promptfoo able to run Provael's *embodied* scan alongside its text-I/O tests — the thing no
text-only red-team tool covers.

Wire it into a promptfooconfig.yaml (see this folder):

    providers:
      - id: 'file://provael_provider.py'
        config:
          policy: stub
          suite: stub
          attacks: [instruction, visual, injection, action]
          episodes: 10
          threshold: 0.5

promptfoo calls `call_api` once per test row; we run Provael with the configured policy/suite/
attacks and return the scorecard verdict + the headline ASR as the output, plus the structured
numbers so promptfoo asserts can gate on them.

This provider runs the CPU stub with no extra deps. Point `policy`/`suite` at a real VLA + sim
(needs `provael[lerobot]` on a GPU) to red-team a real policy from inside promptfoo.
"""

from __future__ import annotations

from typing import Any

from provael.config import RunConfig
from provael.runner import run
from provael.scorecard import verdict


def call_api(prompt: str, options: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """promptfoo Python-provider entrypoint. Returns ``{"output": ..., ...}``."""
    config = (options or {}).get("config", {}) or {}
    threshold = float(config.get("threshold", 0.5))
    report = run(
        RunConfig(
            policy=config.get("policy", "stub"),
            suite=config.get("suite", "stub"),
            model=config.get("model"),
            attacks=config.get("attacks", ["instruction", "visual", "injection", "action"]),
            episodes=int(config.get("episodes", 10)),
            seed=int(config.get("seed", 0)),
        )
    )
    status = verdict(report, threshold)
    output = (
        f"{status}: {report.headline()} "
        f"(policy={report.policy}, suite={report.suite}, threshold={threshold:.0%})"
    )
    # The structured block lets promptfoo `assert` on ASR / verdict directly.
    return {
        "output": output,
        "metadata": {
            "asr": report.asr,
            "successes": report.successes,
            "attempts": report.attempts,
            "verdict": status,
            "by_eai": {eid: tag.id for eid, tag in report.eai.items()},
        },
    }
