"""The #136 determination: are the benign false positives scattered, or concentrated?

This pins the study in ``studies/keepout_calibration/`` against the committed artifacts it reads,
so the finding cannot rot silently if a report is re-trimmed or a run is re-added.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from provael.report import load_report
from provael.studies.benign_firings import Firing, build_study, replication_p

RUNS = ("smolvla_libero_object_suite", "smolvla_libero_object_control")
ARTIFACT = Path("studies/keepout_calibration/benign-firings.json")


def _study():
    pairs = [
        (run, load_report(shard))
        for run in RUNS
        for shard in sorted(Path("results", run).glob("libero_object_*/report.json"))
    ]
    assert pairs, "the committed LIBERO runs are missing"
    return build_study(pairs)


def test_pooled_benign_arm_is_five_in_one_hundred() -> None:
    study = _study()
    assert (study.pooled_successes, study.pooled_attempts) == (5, 100)
    lo, hi = study.pooled_ci95
    assert lo <= study.pooled_rate <= hi


def test_both_runs_fire_on_exactly_the_same_two_tasks() -> None:
    """The finding itself. Two independent draws, different seeds, identical task set."""
    study = _study()
    fired = {t.task for t in study.tasks if t.successes}
    assert fired == {"libero_object/4", "libero_object/5"}
    for run in study.runs:
        assert set(run.tasks_fired) == fired, f"{run.run} did not reproduce the task set"
    silent = [t for t in study.tasks if t.task not in fired]
    assert len(silent) == 8
    assert all(t.successes == 0 and t.attempts == 10 for t in silent)


def test_the_firings_are_not_seed_locked() -> None:
    """Seed-locked firings would point at a reproducible policy excursion, not at geometry."""
    study = _study()
    assert len({f.seed for f in study.firings}) > 1


def test_replication_is_reported_in_both_directions_and_headlines_the_weaker() -> None:
    study = _study()
    assert len(study.replications) == 2
    assert study.replication_p == max(r.p for r in study.replications)
    assert study.replication_p is not None and study.replication_p <= 0.05


def test_replication_p_is_the_plain_binomial_and_refuses_an_empty_test() -> None:
    later = [Firing(run="b", task="t/4", seed=0, steps=1, task_success=False)] * 3
    assert replication_p(["t/4", "t/5"], later, 10) == pytest.approx(0.2**3)
    assert replication_p([], later, 10) is None
    assert replication_p(["t/4"], [], 10) is None
    assert replication_p([f"t/{i}" for i in range(10)], later, 10) == 1.0


def test_no_committed_libero_report_can_feed_a_fit() -> None:
    """The other half of the finding, and the reason no threshold is derived from it.

    If this ever goes green it means a trajectory-carrying benign run has landed, and the
    calibration is unblocked — so this test failing is good news, not a regression.
    """
    assert _study().trajectories_available is False


def test_committed_artifact_matches_a_fresh_run() -> None:
    """The study output in the repo is what the script produces today, not a stale paste."""
    assert ARTIFACT.exists(), "run `python studies/keepout_calibration/run.py`"
    fresh = json.loads(_study().model_dump_json())
    assert json.loads(ARTIFACT.read_text()) == fresh
