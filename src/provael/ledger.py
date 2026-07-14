"""Append-only, resumable trial ledger (E3).

A budget-capped GPU run is spread across cheap, **preemptible** spot instances: one seed × one
task × one attack is a "trial," and a run is thousands of them. If the box is reclaimed mid-run, you
must resume from where you stopped rather than pay to re-measure everything — that is what makes the
roadmap's ≥5-seed budget affordable (ROADMAP E3).

This module is that ledger: an **append-only JSONL** file with one :class:`TrialRecord` per done
trial, keyed by ``(attack, task, seed)``. Appending never rewrites earlier lines (crash-safe), and
:func:`pending_trials` returns exactly the planned trials a fresh run still owes. It is
**deterministic** — no wall-clock, no randomness — so a resumed run reproduces the same records, and
a corrupt trailing line (a trial killed mid-write) is skipped, not fatal.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, Field

from provael.types import AttackResult

#: One trial's identity: the (attack, task, seed) triple. Distinct per trial within a run.
TrialKey = tuple[str, str, int]


class TrialRecord(BaseModel):
    """One completed trial in the ledger — the resumable unit of a red-team run."""

    attack: str
    family: str
    task: str
    seed: int
    trial_index: int = Field(..., description="Ordinal of this trial within the run (episode i).")
    success: bool
    applicable: bool = Field(True, description="False if the attack was N/A for this suite.")

    @property
    def key(self) -> TrialKey:
        """The ``(attack, task, seed)`` identity used for resume/dedup."""
        return (self.attack, self.task, self.seed)


def record_of(result: AttackResult, *, trial_index: int) -> TrialRecord:
    """Build a :class:`TrialRecord` from a finished :class:`~provael.types.AttackResult`."""
    return TrialRecord(
        attack=result.attack,
        family=result.family,
        task=result.task,
        seed=result.seed,
        trial_index=trial_index,
        success=result.success,
        applicable=result.applicable,
    )


def _line(record: TrialRecord) -> str:
    """One canonical, sort-keys-stable JSONL line for ``record`` (deterministic bytes)."""
    return json.dumps(json.loads(record.model_dump_json()), sort_keys=True)


def append_trial(path: Path, record: TrialRecord) -> None:
    """Append one trial to the ledger at ``path`` (created with parents). Never rewrites."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(_line(record) + "\n")


def append_results(path: Path, results: Iterable[AttackResult], *, base_index: int = 0) -> int:
    """Append a run's ``results`` to the ledger in order; return the number of trials written."""
    written = 0
    for offset, result in enumerate(results):
        append_trial(path, record_of(result, trial_index=base_index + offset))
        written += 1
    return written


def read_ledger(path: Path) -> list[TrialRecord]:
    """Load every valid trial from ``path`` (missing file → empty; a corrupt line is skipped)."""
    if not path.is_file():
        return []
    records: list[TrialRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            records.append(TrialRecord.model_validate_json(stripped))
        except ValueError:
            continue  # a trial killed mid-write leaves a partial trailing line — skip it
    return records


def completed_keys(path: Path) -> set[TrialKey]:
    """The set of ``(attack, task, seed)`` trials already recorded in the ledger at ``path``."""
    return {record.key for record in read_ledger(path)}


def pending_trials(planned: Iterable[TrialKey], path: Path) -> list[TrialKey]:
    """The planned trials not yet in the ledger, in ``planned`` order (dedup-preserving).

    A resumed run computes its full plan, then runs only these — so a preempted job never
    re-measures a completed trial, and re-running to completion is idempotent (returns ``[]``).
    """
    done = completed_keys(path)
    seen: set[TrialKey] = set()
    pending: list[TrialKey] = []
    for key in planned:
        if key in done or key in seen:
            continue
        seen.add(key)
        pending.append(key)
    return pending


__all__ = [
    "TrialKey",
    "TrialRecord",
    "record_of",
    "append_trial",
    "append_results",
    "read_ledger",
    "completed_keys",
    "pending_trials",
]
