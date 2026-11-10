# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Every rate carries its counts, its interval's method and level, and what it left out (P1.6).

A rate published as a bare float invites a reader to rebuild the numerator from a rounded number,
and an interval that names no method cannot be compared with another. `RateStat` refuses the
inconsistent cases at construction; `report_rates` is the one resolver every emitter reads, and on
an older report it rebuilds the block from what the report stored, so nothing it says moves.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from provael.attest import _REPORT_FIELDS_ADDED_IN, _report_digest, report_projection
from provael.calibration import wilson_ci
from provael.config import RunConfig
from provael.report import load_report, to_markdown
from provael.runner import run
from provael.scoring.asr import (
    INTERVAL_LEVEL,
    WILSON_EPISODE_LEVEL,
    clean_task_success_rate,
    compute_rates,
    matched_benign_fpr,
    rate_stat,
    report_rates,
)
from provael.scoring.safety_cost import unsafe_success_unobservable
from provael.types import AttackResult, RateInterval, RateStat

ROOT = Path(__file__).resolve().parents[1]


def _interval(low: float = 0.1, high: float = 0.9) -> RateInterval:
    return RateInterval(method=WILSON_EPISODE_LEVEL, level=0.95, low=low, high=high)


def test_rate_stat_carries_the_wilson_interval_by_name() -> None:
    stat = rate_stat(42, 50, n_unjudged=3)
    assert (stat.successes, stat.trials, stat.n_unjudged) == (42, 50, 3)
    assert stat.rate == pytest.approx(0.84)
    assert stat.interval is not None
    assert (stat.interval.method, stat.interval.level) == (WILSON_EPISODE_LEVEL, INTERVAL_LEVEL)
    assert (stat.interval.low, stat.interval.high) == wilson_ci(42, 50)
    empty = rate_stat(0, 0, n_unjudged=2)
    assert empty.rate is None and empty.interval is None, "an empty slice is N/A, not 0%"


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"successes": 6, "trials": 5, "rate": 1.2, "interval": None}, "exceed trials"),
        ({"successes": 1, "trials": 4, "rate": 0.25 + 2e-6, "interval": _interval()},
         "disagrees"),
        ({"successes": 0, "trials": 0, "rate": 0.0, "interval": None}, "no rate"),
        ({"successes": 1, "trials": 4, "rate": 0.25, "interval": None}, "carries both"),
        ({"successes": 1, "trials": 4, "rate": 0.25, "interval": _interval(0.3, 0.9)},
         "outside its interval"),
    ],
)
def test_the_validators_refuse_an_inconsistent_rate(
    fields: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        RateStat(**fields)  # type: ignore[arg-type]


def test_a_rate_within_the_tolerance_is_accepted_and_an_interval_must_be_ordered() -> None:
    RateStat(successes=1, trials=3, rate=0.3333333, interval=_interval())
    with pytest.raises(ValidationError, match="above high"):
        _interval(0.9, 0.1)


def test_a_schema_9_run_stores_the_block_and_it_agrees_with_every_float_beside_it() -> None:
    report = run(RunConfig(policy="stub", suite="stub", attacks=["none", "instruction", "control"],
                           episodes=4))
    rates = report.rates
    assert rates is not None and report_rates(report) is rates
    assert (rates.adversarial.successes, rates.adversarial.trials) == (
        report.adversarial_successes, report.adversarial_attempts)
    assert (rates.all_episodes.successes, rates.all_episodes.trials) == (
        report.successes, report.attempts)
    assert rates.all_episodes.interval is not None and report.ci95 == (
        rates.all_episodes.interval.low, rates.all_episodes.interval.high)
    assert rates.benign_floor is not None and rates.benign_floor.rate == report.benign_fpr
    assert rates.matched_benign_floor is not None
    assert rates.matched_benign_floor.rate == report.matched_benign_fpr
    assert rates.clean_task_success is not None
    assert rates.clean_task_success.rate == report.clean_task_success_rate
    assert rates.succ_but_unsafe is not None
    assert rates.succ_but_unsafe.rate == report.succ_but_unsafe
    assert {k: (v.successes, v.trials) for k, v in rates.by_attack.items()} == {
        k: (v.successes, v.attempts) for k, v in report.by_attack.items()}
    assert {k: (v.successes, v.trials) for k, v in rates.by_task.items()} == {
        k: (v.successes, v.attempts) for k, v in report.by_task.items()}
    assert all(stat.n_unjudged == 0 for stat in rates.by_attack.values())


def test_the_block_is_registered_and_stripped_below_schema_9() -> None:
    assert "rates" in _REPORT_FIELDS_ADDED_IN[9]
    report = run(RunConfig(policy="stub", suite="stub", attacks=["none", "roleplay"], episodes=2))
    older = report.model_copy(update={"schema_version": 8})
    assert "rates" not in report_projection(older)
    assert _report_digest(older) == _report_digest(older.model_copy(update={"rates": None}))


def test_a_libero_run_cannot_report_succ_but_unsafe_in_the_block_either() -> None:
    """E-2026-21 reaches the RateStat too: on a first-event LIBERO run it is None, not 0/n."""
    report = run(RunConfig(policy="stub", suite="stub", attacks=["none"], episodes=2))
    assert compute_rates(report.results, suite="libero").succ_but_unsafe is None
    assert compute_rates(report.results, suite="stub").succ_but_unsafe is not None


def _committed_reports() -> list[Path]:
    return sorted((ROOT / "results").rglob("report.json"))


@pytest.mark.parametrize("path", _committed_reports(), ids=lambda p: str(p.relative_to(ROOT)))
def test_every_committed_report_reads_the_same_through_the_resolver(path: Path) -> None:
    """Older reports load and render the same: the rebuilt block agrees with what they stored."""
    report = load_report(path)
    assert report.rates is None, "no committed report is schema 9 yet"
    rates = report_rates(report)
    _rate, adv_s, adv_n = report.adversarial_headline()
    assert (rates.adversarial.successes, rates.adversarial.trials) == (adv_s, adv_n)
    assert {k: (v.successes, v.trials) for k, v in rates.by_attack.items()} == {
        k: (v.successes, v.attempts) for k, v in report.by_attack.items()}
    if report.benign_fpr is not None and rates.benign_floor is not None:
        assert rates.benign_floor.rate == pytest.approx(report.benign_fpr)
    if not report.results:
        return
    mbf = matched_benign_fpr(report.results)
    assert (rates.matched_benign_floor.rate if rates.matched_benign_floor else None) == mbf
    clean = clean_task_success_rate(report.results)
    assert (rates.clean_task_success.rate if rates.clean_task_success else None) == clean
    if unsafe_success_unobservable(report.suite) is not None:
        assert rates.succ_but_unsafe is None


# --- Per-arm task success and how episodes ended (P2.1) -------------------------------------------


def _signalled(rows: list[AttackResult]) -> tuple[int, int]:
    done = [r for r in rows if r.scored and r.task_success is not None]
    return sum(1 for r in done if r.task_success), len(done)


def test_task_success_is_recorded_per_arm_from_the_same_episodes() -> None:
    report = run(
        RunConfig(policy="stub", suite="stub", attacks=["none", "instruction", "control"],
                  episodes=3, seed=0)
    )
    assert report.rates is not None
    by_arm = report.rates.task_success_by_attack
    assert set(by_arm) == set(report.by_attack)  # the stub surfaces task success on every arm
    for arm, stat in by_arm.items():
        rows = [r for r in report.results if r.attack == arm]
        assert (stat.successes, stat.trials) == _signalled(rows)
        assert stat.interval is not None and stat.interval.method == WILSON_EPISODE_LEVEL


def test_an_older_report_rebuilds_task_success_per_arm_from_its_episodes() -> None:
    shard = ROOT / "results" / "smolvla_libero_object_suite_2026-09-14" / "libero_object_0"
    report = load_report(shard)
    rebuilt = report_rates(report).task_success_by_attack
    assert "mcp_tool_desc" not in rebuilt  # not applicable: absent, never 0/0
    for arm, stat in rebuilt.items():
        rows = [r for r in report.results if r.attack == arm]
        assert (stat.successes, stat.trials) == _signalled(rows)
    assert (rebuilt["none"].successes, rebuilt["none"].trials) == (5, 5)


def test_report_md_prints_each_arm_s_task_success_steps_and_ending() -> None:
    report = run(
        RunConfig(policy="stub", suite="stub", attacks=["none", "roleplay"], episodes=3, seed=0)
    )
    section = to_markdown(report).split("## Task success and how episodes ended, per arm", 1)[1]
    none_row = next(line for line in section.splitlines() if line.startswith("| none |"))
    assert none_row == "| none | benign-control | 3/3 (100.0%) [44–100%] | 8.0 | horizon 3 |"
    roleplay = next(line for line in section.splitlines() if line.startswith("| roleplay |"))
    assert "unsafe_exit" in roleplay


def test_report_md_says_an_older_report_recorded_no_ending() -> None:
    shard = ROOT / "results" / "smolvla_libero_object_suite_2026-09-14" / "libero_object_0"
    md = to_markdown(load_report(shard))
    section = md.split("## Task success and how episodes ended, per arm", 1)[1]
    assert "| none | benign-control | 5/5 (100.0%) [57–100%] |" in section
    assert "not recorded (report schema 5; recorded from schema 9)" in section
    assert "| mcp_tool_desc | adversarial-treatment | N/A | N/A | not applicable on this suite |" in section
