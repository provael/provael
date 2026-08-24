"""Where the benign control arm fires, task by task — the #136 determination.

WHAT QUESTION THIS ANSWERS. A benign false-positive rate is one number, and one number cannot
distinguish the two things it could mean. Either the policy genuinely left the safe region on
those episodes, or the predicate is drawing the boundary in the wrong place and the "violation"
is an artifact of where the box was put. Those call for opposite responses — the first is a
finding about the policy, the second is a bug in the instrument — and the pooled rate is silent
between them.

The discriminator is **structure**, and it is already sitting in the committed reports. A policy
that occasionally wanders is a stochastic process: its firings scatter across tasks, and across
independent runs they land in different places. A misplaced boundary is a geometric fact about
one scene: it fires on the same tasks every time, whatever the seed. So this module does not
average the firings, it *locates* them — per task, per seed, per run — and reports whether one
run's firing set replicates in another.

WHY REPLICATION AND NOT A CHI-SQUARE ON THE POOLED TABLE. Picking out "the tasks that fired" and
then testing whether those tasks fire more than the others tests a hypothesis chosen by looking
at the data, and the p-value that comes back is not the p-value it appears to be. The honest
version needs the hypothesis to come from somewhere other than the data it is tested on, which is
exactly what a second independent run provides: run A nominates a task set, run B tests it
out-of-sample. :func:`replication_p` is that test and nothing else. The pooled association is
reported too, as :attr:`TaskFiring` counts, but as description rather than inference.

WHAT THIS DELIBERATELY DOES NOT DO. It does not propose a corrected zone. Locating a boundary
error is not the same as knowing where the boundary belongs, and the second needs the benign
end-effector poses — which no committed LIBERO report carries (they all predate report schema 3;
see :class:`provael.types.Trajectory`). Emitting a zone from this evidence would be picking a
constant and calling it a calibration, which is the original bug.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Sequence

from pydantic import BaseModel, Field

from provael.calibration import wilson_ci
from provael.types import RunReport


class Firing(BaseModel):
    """One benign episode that the unsafe predicate flagged."""

    run: str
    task: str
    seed: int
    steps: int = Field(..., description="Episode length; equals steps_to_success on a firing, "
                       "because the predicate terminates the episode.")
    task_success: bool = Field(..., description="Whether the episode also completed its task.")


class TaskFiring(BaseModel):
    """Benign firing count for one task, pooled over the runs supplied."""

    task: str
    successes: int
    attempts: int
    rate: float
    ci95: tuple[float, float]


class RunFiring(BaseModel):
    """The benign arm of one run: its pooled rate and which tasks it fired on."""

    run: str
    successes: int
    attempts: int
    rate: float
    ci95: tuple[float, float]
    tasks_fired: list[str]


class Replication(BaseModel):
    """One out-of-sample test: does ``test_run`` fire only where ``nominating_run`` did?"""

    nominating_run: str
    test_run: str
    nominated_tasks: list[str]
    test_firings: int
    p: float


class BenignFiringStudy(BaseModel):
    """The full determination: per-run arms, per-task counts, and the replication test."""

    runs: list[RunFiring]
    tasks: list[TaskFiring]
    firings: list[Firing]
    pooled_successes: int
    pooled_attempts: int
    pooled_rate: float
    pooled_ci95: tuple[float, float]
    replications: list[Replication] = Field(
        default_factory=list,
        description="Every ordered (nominating run -> test run) pair. Both directions are kept "
        "because which run nominates is arbitrary — the two are independent draws, neither is "
        "the designated hypothesis-generator — and reporting only one direction would be a "
        "choice made after seeing which way came out smaller.",
    )
    replication_p: float | None = Field(
        None,
        description="The CONSERVATIVE headline: the LARGEST p over `replications`, i.e. the "
        "weakest direction of the replication. None when no pair is testable.",
    )
    trajectories_available: bool = Field(
        ..., description="Whether ANY supplied report carries the per-step calibration signal. "
        "False means the poses that would locate the corrected boundary were never recorded, so "
        "a threshold cannot be derived from this evidence however it is analysed.",
    )


#: The benign arm. Matches :meth:`provael.types.RunReport.benign_headline` exactly — the same
#: partition, so a count here can never disagree with the headline it is published beside.
BENIGN_FAMILY = "baseline"


def firings_of(report: RunReport, run: str) -> list[Firing]:
    """Every benign episode in ``report`` that the predicate flagged."""
    return [
        Firing(
            run=run, task=r.task, seed=r.seed, steps=r.steps,
            task_success=bool(r.task_success),
        )
        for r in report.results
        if r.applicable and r.family == BENIGN_FAMILY and r.success
    ]


def replication_p(nominated: Sequence[str], test: Sequence[Firing], n_tasks: int) -> float | None:
    """P(every firing in ``test`` lands in ``nominated``) under uniformity across ``n_tasks``.

    The hypothesis — "these particular tasks are the ones that fire" — is supplied by a
    *different, independent* run, so this tests it out-of-sample rather than reading it off the
    same episodes it is scored on. Returns None when there is nothing to test.
    """
    if not nominated or not test or n_tasks <= 0:
        return None
    share = len(set(nominated)) / n_tasks
    if share >= 1.0:
        return 1.0
    return float(math.pow(share, len(test)))


def build_study(reports: Iterable[tuple[str, RunReport]]) -> BenignFiringStudy:
    """Assemble the determination from ``(run_name, report)`` pairs.

    Reports from the same run name are pooled — a sharded run is ten files and one arm.
    """
    pairs = list(reports)
    runs: dict[str, list[RunReport]] = {}
    for name, report in pairs:
        runs.setdefault(name, []).append(report)

    firings: list[Firing] = []
    run_rows: list[RunFiring] = []
    task_succ: Counter[str] = Counter()
    task_att: Counter[str] = Counter()

    for name in sorted(runs):
        succ = att = 0
        for report in runs[name]:
            _rate, s, n = report.benign_headline()
            succ += s
            att += n
            firings.extend(firings_of(report, name))
            for r in report.results:
                if r.applicable and r.family == BENIGN_FAMILY:
                    task_att[r.task] += 1
                    if r.success:
                        task_succ[r.task] += 1
        run_rows.append(
            RunFiring(
                run=name, successes=succ, attempts=att,
                rate=(succ / att if att else 0.0), ci95=wilson_ci(succ, att),
                tasks_fired=sorted({f.task for f in firings if f.run == name}),
            )
        )

    tasks = [
        TaskFiring(
            task=t, successes=task_succ[t], attempts=task_att[t],
            rate=(task_succ[t] / task_att[t] if task_att[t] else 0.0),
            ci95=wilson_ci(task_succ[t], task_att[t]),
        )
        for t in sorted(task_att)
    ]

    p_succ = sum(r.successes for r in run_rows)
    p_att = sum(r.attempts for r in run_rows)

    reps: list[Replication] = []
    for src in run_rows:
        for dst in run_rows:
            if src.run == dst.run:
                continue
            test = [f for f in firings if f.run == dst.run]
            p = replication_p(src.tasks_fired, test, len(tasks))
            if p is None:
                continue
            reps.append(
                Replication(
                    nominating_run=src.run, test_run=dst.run,
                    nominated_tasks=list(src.tasks_fired), test_firings=len(test), p=p,
                )
            )
    p_rep = max((r.p for r in reps), default=None)

    return BenignFiringStudy(
        runs=run_rows,
        tasks=tasks,
        firings=sorted(firings, key=lambda f: (f.run, f.task, f.seed)),
        pooled_successes=p_succ,
        pooled_attempts=p_att,
        pooled_rate=(p_succ / p_att if p_att else 0.0),
        pooled_ci95=wilson_ci(p_succ, p_att),
        replications=reps,
        replication_p=p_rep,
        trajectories_available=any(
            r.trajectory is not None for _n, rep in pairs for r in rep.results
        ),
    )


__all__ = [
    "BENIGN_FAMILY",
    "Firing",
    "Replication",
    "TaskFiring",
    "RunFiring",
    "BenignFiringStudy",
    "firings_of",
    "replication_p",
    "build_study",
]
