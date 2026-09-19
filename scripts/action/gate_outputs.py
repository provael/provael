"""Publish the numbers the release gate reads, from a run's ``report.json``.

THE GATED NUMBER IS ``adversarial_asr``, NOT ``asr``. ``report.json['asr']`` is the all-episode
observed-unsafe rate: it folds the benign control into its denominator. So adding the ``none``
control — which provael itself tells users to add, and which the mitigation gate REQUIRES — pushes
``asr`` BELOW the true attack rate and can turn a failing gate green. Adding a control arm must
never make a policy look safer. Both numbers are published, under names that say which is which.

``adversarial_attempts == 0`` means nothing adversarial was measured. That is not a pass, so the
ASR is emitted EMPTY and ``enforce_gate.py`` fails closed on it.

THE RELEASE DECISION IS A SEPARATE OUTPUT. When ``provael attack --protocol`` wrote a
``report.decision.json`` beside the report, its verdict and protocol name are published as
``release-verdict`` / ``protocol``; ``enforce_gate.py`` fails the job on ``fail`` always and on
``incomplete`` in release mode. With no sidecar both are EMPTY — the run was a diagnostic and no
acceptance was decided — and never a default verdict.

Usage: ``gate_outputs.py <report.json>``
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from _github import emit, load

#: The decision sidecar `provael attack --protocol` writes beside report.json (provael.verdict).
DECISION_JSON = "report.decision.json"


def _decision(report_path: Path) -> tuple[str | None, str | None]:
    """``(release_verdict, protocol)`` from the sidecar beside the report, or ``(None, None)``."""
    sidecar = report_path.parent / DECISION_JSON
    if not sidecar.is_file():
        return None, None
    decision = json.loads(sidecar.read_text(encoding="utf-8"))
    if not decision.get("assessed"):
        return None, None
    return str(decision.get("verdict") or ""), str(decision.get("protocol") or "")


def main(argv: list[str]) -> int:
    report_path = Path(argv[1] if len(argv) > 1 else "provael-run/report.json")
    report = load(report_path)

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

    verdict, protocol = _decision(report_path)
    emit(
        asr=rate if attempts else None,
        **{
            "adversarial-attempts": attempts,
            "all-episode-unsafe-rate": report["asr"],
            "release-verdict": verdict,
            "protocol": protocol,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
