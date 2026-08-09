"""The release gate: an absolute ASR threshold, plus the baseline-regression check.

FAILS CLOSED ON AN EMPTY ASR. `gate_outputs.py` emits an empty string when no adversarial episode
was measured — an all-benign run, or every attack inapplicable to the suite. There is nothing to
compare against the threshold, and "nothing measured" must never read as a pass, so the absence is
an error rather than a default.

BOTH CHECKS RUN BEFORE EITHER EXITS. A run that is over threshold AND regressed reports both
reasons, because a maintainer who fixes only the one they were shown pays for the second CI round
trip to learn the rest.

Reads PROVAEL_ASR, PROVAEL_THRESHOLD, PROVAEL_REGRESSED, PROVAEL_ASR_DELTA,
PROVAEL_FAIL_ON_REGRESSION from the environment.
"""

from __future__ import annotations

import os
import sys

from _github import error


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

    failed = False
    if asr > threshold:
        error(f"Provael overall ASR {asr:.1%} exceeds the {threshold:.1%} threshold")
        failed = True
    if regressed and fail_on_regression:
        delta = os.environ.get("PROVAEL_ASR_DELTA", "?")
        error(
            f"Provael regression: overall ASR rose by {delta} vs baseline "
            "(delta beyond tolerance AND 95% CIs disjoint)"
        )
        failed = True

    if failed:
        return 1
    print(f"Provael gate passed: ASR {asr:.1%} within {threshold:.1%}; regressed={regressed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
