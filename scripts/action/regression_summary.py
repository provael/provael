"""Publish the baseline-regression verdict and render it as a job-summary table.

A REGRESSION HERE IS TWO CONDITIONS, NOT ONE: the delta exceeds tolerance AND the 95% confidence
intervals are disjoint. `provael regression` computes both; this script only reports what it
decided. Rendering `delta > tolerance` alone would flag every noisy run as a regression, which is
how a gate gets disabled.

``None`` is rendered ``n/a``, never ``0.0%``. An unmeasured slice has not been shown to be safe,
and a zero in a table reads as measured-and-fine.

Usage: ``regression_summary.py <regression.json>``
"""

from __future__ import annotations

import sys

from _github import emit, load, summary


def pct(x: float | None) -> str:
    """A rate as a percentage — or ``n/a``, which is NOT the same as 0%."""
    return "n/a" if x is None else f"{100.0 * x:.1f}%"


def table(d: dict) -> str:  # type: ignore[type-arg]
    verdict = "REGRESSED" if d["regressed"] else "no regression"
    rows = [
        "### Provael baseline-regression diff\n",
        f"**{verdict}** (tolerance {d['tolerance']:.0%}, "
        f"policy `{d['policy']}`, suite `{d['suite']}`)\n",
        "| slice | baseline ASR | candidate ASR | delta | status |",
        "| --- | --- | --- | --- | --- |",
    ]
    for s in [d["overall"], *d["by_eai"]]:
        delta = "n/a" if s["delta"] is None else f"{s['delta']:+.1%}"
        rows.append(
            f"| {s['label']} | {pct(s['baseline_asr'])} | {pct(s['candidate_asr'])} | "
            f"{delta} | {'REGRESSED' if s['regressed'] else 'ok'} |"
        )
    return "\n".join(rows) + "\n"


def main(argv: list[str]) -> int:
    d = load(argv[1] if len(argv) > 1 else "provael-run/regression.json")
    emit(regressed=str(d["regressed"]).lower(), **{"asr-delta": d["overall"]["delta"]})
    summary(table(d))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
