"""Eval-rigor primitives: BH-FDR (C1), Succ-But-Unsafe (C2), resumable trial ledger (E3).

Each is pinned by *running it*: the BH correction and the exact binomial tail against known values,
the Succ-But-Unsafe metric's honest N/A on the signal-less stub, and the ledger's append / resume /
crash-skip / determinism semantics.
"""

from __future__ import annotations

from pathlib import Path

from provael.config import RunConfig
from provael.ledger import (
    append_results,
    append_trial,
    completed_keys,
    pending_trials,
    read_ledger,
    record_of,
)
from provael.report import to_markdown
from provael.runner import run
from provael.scoring.asr import (
    benjamini_hochberg,
    binom_test_greater,
    clean_task_success_rate,
    fdr_by_attack,
    succ_but_unsafe,
)
from provael.types import AttackResult


def _res(attack: str, seed: int, success: bool, *, task: str = "reach",
         task_success: bool | None = None, applicable: bool = True) -> AttackResult:
    return AttackResult(
        task=task, attack=attack, family="instruction", seed=seed, success=success,
        steps=1, steps_to_success=1 if success else None, danger=0.0, threshold=0.5,
        original_instruction="reach", adversarial_instruction="reach",
        applicable=applicable, task_success=task_success,
    )


# --------------------------------------------------------------------------------------------
# C1 — exact one-sided binomial p-value + Benjamini-Hochberg FDR
# --------------------------------------------------------------------------------------------

def test_binom_test_greater_matches_known_tails() -> None:
    assert abs(binom_test_greater(10, 10, 0.5) - 0.5 ** 10) < 1e-12  # all-successes tail
    assert abs(binom_test_greater(5, 10, 0.5) - 638 / 1024) < 1e-12  # P(X>=5 | 10, .5)
    assert binom_test_greater(0, 10, 0.5) == 1.0  # no successes -> no evidence
    assert binom_test_greater(3, 0, 0.5) == 1.0  # no attempts -> no evidence
    # Monotone: a higher observed count is at least as surprising (smaller p).
    assert binom_test_greater(9, 10, 0.5) <= binom_test_greater(8, 10, 0.5)


def test_benjamini_hochberg_known_examples_and_order() -> None:
    assert benjamini_hochberg([]) == ([], [])
    # The textbook p = 0.01..0.05 case: every q collapses to 0.05, all rejected at alpha=0.05.
    q, reject = benjamini_hochberg([0.01, 0.02, 0.03, 0.04, 0.05], alpha=0.05)
    assert all(abs(v - 0.05) < 1e-12 for v in q) and all(reject)
    # One strong signal among nulls: only it survives; q-values map back to INPUT order.
    q2, reject2 = benjamini_hochberg([0.5, 0.001, 0.5, 0.5, 0.5], alpha=0.05)
    assert reject2 == [False, True, False, False, False]
    assert abs(q2[1] - 0.005) < 1e-12 and all(abs(q2[i] - 0.5) < 1e-12 for i in (0, 2, 3, 4))


def test_fdr_by_attack_needs_a_control_and_flags_significance() -> None:
    # No benign baseline -> nothing to test against -> None (never a fabricated significance).
    no_ctrl = run(RunConfig(policy="stub", suite="stub", attacks=["roleplay"], episodes=10))
    assert fdr_by_attack(no_ctrl) is None
    # With the `none` control the strongly-succeeding stub attacks are BH-significant.
    report = run(RunConfig(
        policy="stub", suite="stub", attacks=["none", "instruction"], episodes=10, seed=0
    ))
    fdr = fdr_by_attack(report)
    assert fdr is not None and "none" not in fdr  # the control is not tested against itself
    assert all(sig for _q, sig in fdr.values())  # roleplay/goal_substitution/paraphrase all clear
    assert "Benjamini-Hochberg FDR" in to_markdown(report)  # surfaced in the report


# --------------------------------------------------------------------------------------------
# C2 — Succ-But-Unsafe (schema scaffold; honest N/A on the stub)
# --------------------------------------------------------------------------------------------

def test_succ_but_unsafe_is_none_without_a_task_success_signal() -> None:
    # Pure function: with no task-success signal on any episode, the quadrant is honestly N/A.
    assert succ_but_unsafe([_res("roleplay", 0, True), _res("roleplay", 1, False)]) is None


def test_succ_but_unsafe_counts_only_the_completed_and_unsafe_quadrant() -> None:
    results = [
        _res("a", 0, success=True, task_success=True),    # completed AND unsafe -> counts
        _res("a", 1, success=False, task_success=True),   # completed, safe -> no
        _res("a", 2, success=True, task_success=False),   # failed task, unsafe -> no
        _res("a", 3, success=True, task_success=None),    # no signal -> excluded from denominator
    ]
    assert succ_but_unsafe(results) == 1 / 3  # 1 of the 3 signal-carrying episodes


# --------------------------------------------------------------------------------------------
# Clean-task-success control (the credibility fix) — competence of the policy, unattacked
# --------------------------------------------------------------------------------------------

def test_clean_task_success_rate_is_over_the_benign_baseline_only() -> None:
    results = [
        _res("none", 0, success=False, task_success=True),    # benign, completed -> counts
        _res("none", 1, success=False, task_success=False),   # benign, failed   -> counts
        _res("roleplay", 2, success=True, task_success=True),  # attacked -> excluded
        _res("none", 3, success=False, task_success=None),     # no signal -> excluded
    ]
    assert clean_task_success_rate(results) == 1 / 2  # only the 2 signal-carrying benign episodes


def test_clean_task_success_rate_is_none_without_a_benign_task_success_signal() -> None:
    # No benign episode carries the signal -> honestly None (disclosed-inert), never fabricated.
    assert clean_task_success_rate([_res("none", 0, success=False, task_success=None)]) is None
    assert clean_task_success_rate([_res("roleplay", 0, success=True, task_success=True)]) is None


def test_stub_surfaces_task_success_and_the_clean_control_is_populated() -> None:
    # The credibility fix on the CPU path: the stub is competent on its benign reach task (100%),
    # `freeze` fails the task, and the whole control is reported without a real model.
    report = run(RunConfig(policy="stub", suite="stub",
                           attacks=["none", "roleplay", "freeze"], episodes=6, seed=0))
    assert report.clean_task_success_rate == 1.0  # benign baseline completes the reach task
    assert report.succ_but_unsafe is not None     # the stub now surfaces a task-success signal
    by_attack: dict[str, set[bool | None]] = {}
    for r in report.results:
        by_attack.setdefault(r.attack, set()).add(r.task_success)
    assert by_attack["none"] == {True}    # benign reach completes
    assert by_attack["freeze"] == {False}  # frozen motion never reaches the goal


def test_clean_task_success_rate_surfaces_in_report_markdown() -> None:
    report = run(RunConfig(policy="stub", suite="stub", attacks=["none", "roleplay"], episodes=4))
    md = to_markdown(report)
    assert "clean-task-success (benign control)" in md


# --------------------------------------------------------------------------------------------
# E3 — append-only resumable trial ledger
# --------------------------------------------------------------------------------------------

def test_ledger_round_trips_and_keys(tmp_path: Path) -> None:
    ledger = tmp_path / "trials.jsonl"
    rec = record_of(_res("roleplay", 7, True), trial_index=0)
    append_trial(ledger, rec)
    loaded = read_ledger(ledger)
    assert loaded == [rec]
    assert rec.key == ("roleplay", "reach", 7)
    assert completed_keys(ledger) == {("roleplay", "reach", 7)}


def test_ledger_resume_is_idempotent_and_skips_completed(tmp_path: Path) -> None:
    ledger = tmp_path / "trials.jsonl"
    plan = [("roleplay", "reach", s) for s in range(5)]
    append_results(ledger, [_res("roleplay", s, s % 2 == 0) for s in range(3)])
    # Only the not-yet-run trials remain, in plan order.
    assert pending_trials(plan, ledger) == [("roleplay", "reach", 3), ("roleplay", "reach", 4)]
    # Finish them, then a re-run owes nothing (idempotent).
    append_results(ledger, [_res("roleplay", s, False) for s in (3, 4)], base_index=3)
    assert pending_trials(plan, ledger) == []


def test_ledger_skips_a_corrupt_trailing_line_and_is_deterministic(tmp_path: Path) -> None:
    ledger = tmp_path / "trials.jsonl"
    append_trial(ledger, record_of(_res("roleplay", 0, True), trial_index=0))
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write('{"attack": "roleplay", "task": "rea')  # a trial killed mid-write
    # The partial line is skipped, not fatal — resume still sees the one good trial.
    assert len(read_ledger(ledger)) == 1
    # Appending the same record twice yields byte-identical lines (no clock, no randomness).
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    rec = record_of(_res("x", 1, False), trial_index=2)
    append_trial(a, rec)
    append_trial(b, rec)
    assert a.read_bytes() == b.read_bytes()
