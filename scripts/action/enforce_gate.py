"""The release gate: an absolute ASR threshold, the baseline-regression check, and the decision.

FAILS CLOSED ON AN EMPTY ASR. `gate_outputs.py` emits an empty string when no adversarial episode
was measured — an all-benign run, or every attack inapplicable to the suite. There is nothing to
compare against the threshold, and "nothing measured" must never read as a pass, so the absence is
an error rather than a default.

THE RELEASE DECISION IS GATED SEPARATELY FROM THE DIAGNOSTIC. `provael attack --protocol` writes a
decision under a named acceptance protocol; its verdict arrives here as PROVAEL_RELEASE_VERDICT.
A `fail` (a critical slice or the pooled gate breached, or a failed criterion) fails the job
whatever the aggregate threshold said — an attack a protocol names as critical cannot be diluted
by other arms. An `incomplete` (missing required evidence, an unmeasured critical slice, or no
protocol named at all) fails the job only in release mode (PROVAEL_RELEASE_MODE=true): a
diagnostic run is allowed to produce a measurement without deciding anything, and a release run is
not allowed to ship on one. The reasons are read from the sidecar so the annotation names the
slice, not just the state.

EVERY CHECK RUNS BEFORE ANY EXITS. A run that is over threshold AND regressed AND failed its
protocol reports all three reasons, because a maintainer who fixes only the one they were shown pays
for the second CI round trip to learn the rest.

Reads PROVAEL_ASR, PROVAEL_THRESHOLD, PROVAEL_REGRESSED, PROVAEL_ASR_DELTA,
PROVAEL_FAIL_ON_REGRESSION, PROVAEL_RELEASE_VERDICT, PROVAEL_PROTOCOL, PROVAEL_RELEASE_MODE and
PROVAEL_DECISION (path of the sidecar, for the reasons) from the environment.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from _github import error


def _reasons(path: str) -> list[str]:
    """The decision's reasons, so the annotation names what failed; empty when unreadable."""
    p = Path(path)
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    reasons = data.get("reasons")
    return [str(r) for r in reasons] if isinstance(reasons, list) else []


def main() -> int:
    raw = os.environ["PROVAEL_ASR"].strip()
    threshold = float(os.environ["PROVAEL_THRESHOLD"])

    if not raw:
        error(
            f"Provael measured no adversarial episode, so the {threshold:.1%} ASR threshold has "
            "no evidence to evaluate. Check that `attacks` names at least one adversarial attack "
            "applicable to this suite."
        )
        return 1

    asr = float(raw)
    regressed = os.environ.get("PROVAEL_REGRESSED", "") == "true"
    fail_on_regression = os.environ.get("PROVAEL_FAIL_ON_REGRESSION", "true").lower() == "true"
    verdict = os.environ.get("PROVAEL_RELEASE_VERDICT", "").strip().lower()
    protocol = os.environ.get("PROVAEL_PROTOCOL", "").strip() or "none named"
    release_mode = os.environ.get("PROVAEL_RELEASE_MODE", "false").lower() == "true"
    reasons = _reasons(os.environ.get("PROVAEL_DECISION", "provael-run/report.decision.json"))

    failed = False
    if asr > threshold:
        error(f"Provael pooled adversarial ASR {asr:.1%} exceeds the {threshold:.1%} threshold")
        failed = True
    if regressed and fail_on_regression:
        delta = os.environ.get("PROVAEL_ASR_DELTA", "?")
        error(
            f"Provael regression: ASR rose by {delta} vs baseline on the overall slice or a "
            "critical attack (delta beyond tolerance AND 95% CIs disjoint)"
        )
        failed = True
    detail = "; ".join(reasons) if reasons else "no reasons recorded"
    if verdict == "fail":
        error(f"Provael release decision under protocol {protocol}: FAIL — {detail}")
        failed = True
    elif verdict in {"", "incomplete", "conditional"} and release_mode:
        if verdict == "conditional":
            print(f"Provael release decision under protocol {protocol}: conditional — {detail}")
        else:
            state = verdict or "not assessed (no acceptance protocol named)"
            error(
                f"Provael release decision under protocol {protocol}: {state} — {detail}. A "
                "release-mode run needs a named protocol whose requirements are all satisfied."
            )
            failed = True
    elif verdict in {"incomplete", "conditional"}:
        print(f"Provael release decision under protocol {protocol}: {verdict} — {detail}")

    if failed:
        return 1
    decided = verdict or "not assessed"
    print(
        f"Provael gate passed: ASR {asr:.1%} within {threshold:.1%}; regressed={regressed}; "
        f"release decision {decided} (protocol {protocol}; release mode {release_mode})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
