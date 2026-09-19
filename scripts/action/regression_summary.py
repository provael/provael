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
    critical = set(d.get("critical_attacks", []))
    critical_rows = [s for s in d.get("by_attack", []) if s.get("key") in critical]
    for s in [d["overall"], *d["by_eai"], *critical_rows]:
        delta = "n/a" if s["delta"] is None else f"{s['delta']:+.1%}"
        label = f"critical: {s['label']}" if s.get("key") in critical else s["label"]
        rows.append(
            f"| {label} | {pct(s['baseline_asr'])} | {pct(s['candidate_asr'])} | "
            f"{delta} | {'REGRESSED' if s['regressed'] else 'ok'} |"
        )
    if d.get("critical_regressed"):
        rows.append(
            f"\n**Critical regression:** {', '.join(d['critical_regressed'])} — trips the gate "
            "whatever the aggregate did."
        )
    if d.get("critical_unmeasured"):
        rows.append(
            f"\n**Critical but not comparable:** {', '.join(d['critical_unmeasured'])} — no data "
            "on one side; not shown to be safe."
        )
    return "\n".join(rows) + "\n"


def main(argv: list[str]) -> int:
    d = load(argv[1] if len(argv) > 1 else "provael-run/regression.json")
    emit(
        regressed=str(d["regressed"]).lower(),
        **{
            "asr-delta": d["overall"]["delta"],
            "critical-regressed": ",".join(d.get("critical_regressed", [])),
        },
    )
    summary(table(d))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
