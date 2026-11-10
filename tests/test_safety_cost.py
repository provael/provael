# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Guards for the process-level safety-cost metrics (CC / RET / USR / quadrant).

THE PROPERTY THESE EXIST TO HOLD. Every function here returns ``None`` rather than ``0.0`` when the
signal it needs is absent. That is not a style preference. A safety metric that reports 0.0 for
"we did not look" is indistinguishable, in a table, from one that reports 0.0 for "we looked and
found nothing" — and the first reads as a clean bill of health. The repo already made this decision
for ``benign_unsafe_rate`` and ``succ_but_unsafe``; these tests hold the new module to it, because
the failure is silent and only shows up in a document somebody has already acted on.

The second property is the quadrant partition: the five counts must always sum to the applicable
episode count. Episodes with no task-success signal are counted as ``task_success_unmeasured``
rather than dropped, so a reader can never subtract four numbers from the total and conclude the
remainder was safe.
"""

from __future__ import annotations

import json
from pathlib import Path

from provael.config import RunConfig
from provael.runner import run
from provael.scoring.safety_cost import (
    ENDS_AT_FIRST_UNSAFE_STEP,
    ENDS_AT_SUCCESS_OR_EXIT,
    FIXED_HORIZON,
    QUADRANT_KEYS,
    SAFE_SUCCESS,
    TASK_SUCCESS_UNMEASURED,
    UNSAFE_SUCCESS,
    cumulative_cost,
    exposure_unobservable,
    observed_unsafe_success_rate,
    quadrant_counts,
    risk_exposure_time,
    unsafe_success_rate,
    unsafe_success_unobservable,
)
from provael.types import AttackResult, Decision


def _decision(step: int, *, unsafe: bool) -> Decision:
    return Decision(step=step, instruction="go", action=[0.0], unsafe=unsafe)


def _result(
    *,
    unsafe_steps: int = 0,
    total_steps: int = 0,
    success: bool = False,
    task_success: bool | None = None,
    applicable: bool = True,
    decisions: bool = True,
) -> AttackResult:
    """One synthetic episode. ``decisions=False`` models a run with no per-step log."""
    log = []
    if decisions:
        log = [_decision(i + 1, unsafe=i < unsafe_steps) for i in range(total_steps)]
    return AttackResult(
        task="t", attack="a", family="instruction", seed=0,
        success=success, steps=total_steps, danger=0.0, threshold=0.0,
        original_instruction="o", adversarial_instruction="a",
        applicable=applicable, task_success=task_success, decisions=log,
    )


# --------------------------------------------------------------------------- #
# risk_exposure_time — dwell, not a flag
# --------------------------------------------------------------------------- #


def test_ret_counts_unsafe_steps_not_whether_the_episode_ended_unsafe() -> None:
    """Two episodes that both end unsafe are not equivalent if one dwelt 40x longer."""
    brief = _result(unsafe_steps=1, total_steps=40, success=True)
    sustained = _result(unsafe_steps=30, total_steps=40, success=True)
    assert risk_exposure_time(brief) == 1
    assert risk_exposure_time(sustained) == 30
    # The binary the ASR reads is identical for both — which is the reason RET exists.
    assert brief.success == sustained.success


def test_ret_is_none_without_a_decision_log_never_zero() -> None:
    """No log means unmeasured exposure. Zero would assert the policy was never unsafe."""
    assert risk_exposure_time(_result(decisions=False, total_steps=40, success=True)) is None


def test_ret_is_zero_when_a_log_exists_and_records_no_unsafe_step() -> None:
    """The distinction the previous test protects: this one really is a measured zero."""
    assert risk_exposure_time(_result(unsafe_steps=0, total_steps=10)) == 0


# --------------------------------------------------------------------------- #
# cumulative_cost
# --------------------------------------------------------------------------- #


def test_cc_is_mean_exposure_over_applicable_logged_episodes() -> None:
    results = [
        _result(unsafe_steps=4, total_steps=10),
        _result(unsafe_steps=0, total_steps=10),
    ]
    assert cumulative_cost(results) == 2.0


def test_cc_excludes_not_applicable_episodes() -> None:
    """N/A is not 0 and is not a pass — the repo's rule, applied to the cost metric."""
    results = [
        _result(unsafe_steps=4, total_steps=10),
        _result(unsafe_steps=0, total_steps=10, applicable=False),
    ]
    assert cumulative_cost(results) == 4.0


def test_cc_is_none_when_no_episode_carries_a_log() -> None:
    assert cumulative_cost([_result(decisions=False, total_steps=5)]) is None
    assert cumulative_cost([]) is None


# --------------------------------------------------------------------------- #
# unsafe_success_rate — the quadrant a task-success metric cannot see
# --------------------------------------------------------------------------- #


def test_usr_counts_task_success_that_was_also_unsafe() -> None:
    results = [
        _result(success=True, task_success=True),    # USR
        _result(success=False, task_success=True),   # safe success
        _result(success=True, task_success=False),   # unsafe failure
        _result(success=False, task_success=False),  # safe failure
    ]
    assert unsafe_success_rate(results) == 0.25


def test_usr_is_none_when_no_episode_carries_a_task_success_signal() -> None:
    """The honest state on a suite with no task-success signal — never 0.0."""
    assert unsafe_success_rate([_result(success=True), _result(success=False)]) is None


def test_usr_excludes_unsignalled_episodes_from_the_denominator() -> None:
    """A missing signal is excluded, never counted as a safe episode (which would deflate USR)."""
    results = [
        _result(success=True, task_success=True),
        _result(success=True, task_success=None),
        _result(success=True, task_success=None),
    ]
    assert unsafe_success_rate(results) == 1.0


def test_usr_agrees_with_the_succ_but_unsafe_the_repo_already_reports() -> None:
    """Two names, one quantity. If these ever diverge, one document is lying to a reader."""
    from provael.scoring.asr import succ_but_unsafe

    report = run(RunConfig(policy="stub", suite="stub", attacks=["none", "instruction"],
                           episodes=10, seed=0))
    assert unsafe_success_rate(report.results) == succ_but_unsafe(report.results)


# --------------------------------------------------------------------------- #
# quadrant_counts — the partition must close
# --------------------------------------------------------------------------- #


def test_quadrant_partitions_every_applicable_episode() -> None:
    results = [
        _result(success=True, task_success=True),
        _result(success=False, task_success=True),
        _result(success=True, task_success=False),
        _result(success=False, task_success=False),
        _result(success=True, task_success=None),
        _result(success=True, task_success=True, applicable=False),  # excluded entirely
    ]
    counts = quadrant_counts(results)
    assert counts[UNSAFE_SUCCESS] == 1
    assert counts[SAFE_SUCCESS] == 1
    assert counts[TASK_SUCCESS_UNMEASURED] == 1
    # The partition closes over applicable episodes — five of the six above.
    assert sum(counts.values()) == 5


def test_quadrant_always_reports_every_key_even_at_zero() -> None:
    """An absent key reads as an absent category; an explicit 0 reads as an answer."""
    counts = quadrant_counts([])
    assert set(counts) == set(QUADRANT_KEYS)
    assert all(v == 0 for v in counts.values())


def test_quadrant_closes_on_a_real_run() -> None:
    report = run(RunConfig(policy="stub", suite="reach", attacks=["none", "instruction"],
                           episodes=5, seed=0))
    applicable = sum(1 for r in report.results if r.applicable)
    assert sum(quadrant_counts(report.results).values()) == applicable


# ------------------------------------------------------------------------------------------------
# What a run could observe (E-2026-21)
# ------------------------------------------------------------------------------------------------

RESULTS = Path(__file__).resolve().parent.parent / "results"


def test_a_first_event_libero_run_observes_none_of_the_three() -> None:
    assert exposure_unobservable("libero") == ENDS_AT_SUCCESS_OR_EXIT
    assert unsafe_success_unobservable("libero") == ENDS_AT_SUCCESS_OR_EXIT


def test_the_stub_loses_exposure_but_keeps_unsafe_success() -> None:
    """Its episodes stop at the first unsafe step and run on after task success latches."""
    assert exposure_unobservable("stub") == ENDS_AT_FIRST_UNSAFE_STEP
    assert unsafe_success_unobservable("stub") is None


def test_a_fixed_horizon_run_observes_all_three() -> None:
    assert exposure_unobservable("libero", FIXED_HORIZON) is None
    assert unsafe_success_unobservable("libero", FIXED_HORIZON) is None


def test_observed_rate_is_null_on_first_event_libero_and_the_old_value_past_it() -> None:
    results = [_result(success=True, task_success=True), _result(success=False, task_success=True)]
    assert observed_unsafe_success_rate(results, suite="libero") is None
    assert observed_unsafe_success_rate(results, suite="libero", termination=FIXED_HORIZON) == 0.5
    assert observed_unsafe_success_rate(results, suite="stub") == 0.5


def test_a_stub_run_keeps_its_rate_in_the_report() -> None:
    report = run(RunConfig(policy="stub", suite="stub", attacks=["none", "instruction"], episodes=2))
    assert report.succ_but_unsafe == unsafe_success_rate(report.results)


def test_no_committed_real_policy_episode_could_show_what_the_erratum_says_it_cannot() -> None:
    """The evidence behind E-2026-21, recomputed. A fixed-horizon run must filter itself out here."""
    both = logged = unsafe = over_one = 0
    for path in RESULTS.rglob("report.json"):
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("policy") == "stub" or report.get("suite") != "libero":
            continue
        for row in report["results"]:
            both += bool(row.get("success") and row.get("task_success"))
            if row.get("decisions"):
                logged += 1
                count = sum(1 for d in row["decisions"] if d.get("unsafe"))
                unsafe += count > 0
                over_one += count > 1
    assert logged and unsafe, "no real-policy decision log left to check; the guard went vacuous"
    assert both == 0
    assert over_one == 0


def _committed_report_mds() -> list[tuple[Path, str]]:
    found = []
    for path in sorted(RESULTS.rglob("report.md")):
        data = json.loads((path.parent / "report.json").read_text(encoding="utf-8"))
        found.append((path, str(data.get("suite"))))
    return found


def test_no_committed_libero_report_md_prints_these_metrics_as_numbers() -> None:
    """Every committed LIBERO report.md with the table. A number here reads as "looked and found none"."""
    checked = 0
    for path, suite in _committed_report_mds():
        if suite != "libero":
            continue
        text = path.read_text(encoding="utf-8")
        if "## Process-level safety cost" not in text:
            continue
        checked += 1
        for row in ("Succ-But-Unsafe", "cumulative cost (CC counterpart)",
                    "risk exposure time (RET counterpart)", "unsafe success rate (USR)",
                    "unsafe success"):
            assert f"| {row} | N/A ({ENDS_AT_SUCCESS_OR_EXIT}) |" in text, f"{path}: {row}"
    assert checked, "no committed LIBERO report.md was checked"


def test_committed_stub_report_mds_report_no_exposure_as_a_number() -> None:
    checked = 0
    for path, suite in _committed_report_mds():
        text = path.read_text(encoding="utf-8")
        if suite == "libero" or "## Process-level safety cost" not in text:
            continue
        checked += 1
        assert f"| cumulative cost (CC counterpart) | N/A ({ENDS_AT_FIRST_UNSAFE_STEP}) |" in text
    assert checked, "no committed stub report.md was checked"
