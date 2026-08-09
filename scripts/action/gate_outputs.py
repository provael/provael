"""Publish the numbers the release gate reads, from a run's ``report.json``.

THE GATED NUMBER IS ``adversarial_asr``, NOT ``asr``. ``report.json['asr']`` is the all-episode
observed-unsafe rate: it folds the benign control into its denominator. So adding the ``none``
control — which provael itself tells users to add, and which the mitigation gate REQUIRES — pushes
``asr`` BELOW the true attack rate and can turn a failing gate green. Adding a control arm must
never make a policy look safer. Both numbers are published, under names that say which is which.

``adversarial_attempts == 0`` means nothing adversarial was measured. That is not a pass, so the
ASR is emitted EMPTY and ``enforce_gate.py`` fails closed on it.

Usage: ``gate_outputs.py <report.json>``
"""

from __future__ import annotations

import sys

from _github import emit, load


def main(argv: list[str]) -> int:
    report = load(argv[1] if len(argv) > 1 else "provael-run/report.json")

    attempts = report.get("adversarial_attempts")
    successes = report.get("adversarial_successes")
    if attempts is None or successes is None:
        # Legacy report from before the adversarial split: recompute from raw episodes rather than
        # falling back to `asr`, which would silently gate on the contaminated number this whole
        # module exists to avoid.
        adversarial = [
            e for e in report.get("results", [])
            if e.get("applicable", True) and e.get("family") != "baseline"
        ]
        attempts = len(adversarial)
        successes = sum(1 for e in adversarial if e.get("success"))

    rate = report.get("adversarial_asr")
    if rate is None and attempts:
        rate = successes / attempts

    emit(
        asr=rate if attempts else None,
        **{
            "adversarial-attempts": attempts,
            "all-episode-unsafe-rate": report["asr"],
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
