"""Per-task reachable-workspace bounds, derived from recorded BENIGN trajectories (#136).

WHAT THIS DELIBERATELY DOES NOT DO. It does not emit a calibrated keep-out zone, and it must not
be extended to until the data exists to argue about. A calibrated zone needs a MARGIN — how far
outside the benign envelope a hazard region starts — and picking one without first looking at real
benign spread is exactly how ``DEFAULT_KEEP_OUT_ZONE`` came to be a hand-picked box that overlaps
the workspace it was supposed to sit outside. That box is the whole of #136. Choosing a second
number the same way would reproduce the bug with more decimal places.

So this emits the observation and stops: per task, the axis-aligned bounds of where the policy
actually went under the benign arm, and HOW MANY episodes fed that estimate. The episode count is
not decoration — bounds from two episodes and bounds from fifty are different objects, and the
one thing a reader must not do is treat a thin estimate as a workspace.

BENIGN ONLY, BY CONSTRUCTION. An adversarial episode is, when the attack works, precisely a
trajectory that leaves the benign envelope. Folding those in would widen the "reachable workspace"
to include the region the predicate is meant to forbid, and the resulting zone would be unable to
fire. The filter is on attack name, not on outcome: a FAILED attack is still an attacked episode
and still not evidence about benign behaviour.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from provael.report import load_report
from provael.types import AttackResult, RunReport

#: The benign arm. `none` is the baseline; the control family is a harmless VARIATION and is
#: excluded too, because "would an innocent reword do this?" is a different question from "where
#: does this policy go when nothing is done to it?".
BENIGN_ATTACKS = frozenset({"none"})


class TaskBounds(BaseModel):
    """Observed extent of the benign end-effector trajectories for one task."""

    task: str
    episodes: int = Field(..., description="Benign episodes that contributed at least one pose.")
    steps: int = Field(..., description="Total poses across those episodes.")
    dims: int = Field(..., description="3 for a spatial suite, 1 for a scalar-danger suite.")
    lower: list[float] = Field(..., description="Per-axis minimum observed.")
    upper: list[float] = Field(..., description="Per-axis maximum observed.")

    @property
    def thin(self) -> bool:
        """Fewer than five contributing episodes. Stated, never silently smoothed over."""
        return self.episodes < 5


def benign_results(report: RunReport) -> list[AttackResult]:
    return [r for r in report.results if r.attack in BENIGN_ATTACKS and r.trajectory is not None]


@dataclass
class _Acc:
    """Running per-task extent. A dataclass rather than a dict so mypy checks the arithmetic."""

    episodes: int
    steps: int
    lower: list[float]
    upper: list[float]

    def add(self, poses: list[list[float]]) -> None:
        for pose in poses:
            for i, v in enumerate(pose):
                self.lower[i] = min(self.lower[i], v)
                self.upper[i] = max(self.upper[i], v)
        self.episodes += 1
        self.steps += len(poses)


def bounds_from_reports(reports: Iterable[RunReport]) -> list[TaskBounds]:
    """Axis-aligned benign bounds per task, sorted by task id."""
    acc: dict[str, _Acc] = {}
    for report in reports:
        for result in benign_results(report):
            trajectory = result.trajectory
            if trajectory is None:  # pragma: no cover - benign_results filters these out
                continue
            poses = trajectory.decode()
            if not poses:
                continue
            entry = acc.get(result.task)
            if entry is None:
                entry = _Acc(0, 0, list(poses[0]), list(poses[0]))
                acc[result.task] = entry
            entry.add(poses)

    return [
        TaskBounds(
            task=task,
            episodes=e.episodes,
            steps=e.steps,
            dims=len(e.lower),
            lower=list(e.lower),
            upper=list(e.upper),
        )
        for task, e in sorted(acc.items())
    ]


def bounds_from_paths(paths: Iterable[Path]) -> list[TaskBounds]:
    """Load every run directory / report.json in ``paths`` and derive the bounds."""
    from provael.leaderboard import find_reports

    found = find_reports([str(p) for p in paths])
    return bounds_from_reports([load_report(p) for p in found])


__all__ = [
    "BENIGN_ATTACKS",
    "TaskBounds",
    "benign_results",
    "bounds_from_paths",
    "bounds_from_reports",
]
