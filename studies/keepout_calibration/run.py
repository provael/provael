#!/usr/bin/env python3
"""Locate the benign control's false positives across the committed LIBERO runs (#136).

Defensive, sim-only, CPU-only, no network. A thin driver over
:mod:`provael.studies.benign_firings` — it reimplements no rate and no interval; every number it
prints comes from :meth:`provael.types.RunReport.benign_headline` and
:func:`provael.calibration.wilson_ci`, the same two functions that produce the published figures.

    python studies/keepout_calibration/run.py

It reads only artifacts already in the repository, so it is reproducible by anyone who can clone
it — which is the point. The question it settles is whether the benign firings are scattered (a
stochastic policy excursion) or concentrated (a misplaced boundary), and that is decidable from
where they landed without re-running anything.

WHAT IT CANNOT SETTLE, AND WHY THAT IS RECORDED RATHER THAN WORKED AROUND. Knowing the boundary is
misplaced is not knowing where to put it. That needs the benign end-effector poses, and every
committed LIBERO report predates report schema 3 and carries none — ``trajectories_available``
comes out False and the artifact says so in its own fields. The corrected zone is therefore NOT
derived here. Choosing one anyway, from a study that has just demonstrated the last constant was
chosen without data, would be the same mistake with a citation attached.
"""

from __future__ import annotations

import json
from pathlib import Path

from provael.report import load_report
from provael.studies.benign_firings import BenignFiringStudy, build_study

#: The two committed SmolVLA x LIBERO-Object runs. Both used the SAME uncalibrated default box
#: (``calibrated: false``, tool 0.32.0), and their benign arms are independent draws of 50 —
#: which is what makes one able to test the other out-of-sample.
RUNS = ("smolvla_libero_object_suite", "smolvla_libero_object_control")

RESULTS = Path("results")
OUT = Path("studies/keepout_calibration/benign-firings.json")


def collect() -> BenignFiringStudy:
    pairs = [
        (run, load_report(shard))
        for run in RUNS
        for shard in sorted((RESULTS / run).glob("libero_object_*/report.json"))
    ]
    return build_study(pairs)


def render(study: BenignFiringStudy) -> str:
    pct = lambda v: f"{100.0 * v:.1f}%"  # noqa: E731 - local formatter, not an API
    out = ["Benign control firings — SmolVLA x LIBERO-Object, uncalibrated default box", ""]
    for r in study.runs:
        out.append(
            f"  {r.run:38s} {r.successes}/{r.attempts} = {pct(r.rate):>6s}  "
            f"95% CI [{pct(r.ci95[0])}, {pct(r.ci95[1])}]  fired on: "
            + (", ".join(r.tasks_fired) or "nothing")
        )
    out.append(
        f"  {'POOLED':38s} {study.pooled_successes}/{study.pooled_attempts} = "
        f"{pct(study.pooled_rate):>6s}  95% CI [{pct(study.pooled_ci95[0])}, "
        f"{pct(study.pooled_ci95[1])}]"
    )
    out += ["", "  per task:"]
    for t in study.tasks:
        flag = "  <-- fires" if t.successes else ""
        out.append(f"    {t.task:22s} {t.successes}/{t.attempts}{flag}")
    out += ["", "  firings:"]
    for f in study.firings:
        out.append(
            f"    {f.run:38s} {f.task:18s} seed {f.seed}  {f.steps:>4d} steps  "
            f"task_success={f.task_success}"
        )
    out += ["", "  out-of-sample replication (one run nominates the task set, the other is"
                " tested):"]
    for r in study.replications:
        out.append(
            f"    {r.nominating_run} -> {r.test_run}: all {r.test_firings} test firings inside "
            f"{r.nominated_tasks}, p = {r.p:.4f}"
        )
    out.append(f"  conservative (largest) p: {study.replication_p:.4f}"
               if study.replication_p is not None else "  conservative p: n/a")
    out.append(f"  trajectories available for a fit: {study.trajectories_available}")
    return "\n".join(out)


def main() -> None:
    study = collect()
    print(render(study))
    OUT.write_text(
        json.dumps(json.loads(study.model_dump_json()), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
