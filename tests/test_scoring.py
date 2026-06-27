"""ASR scoring math, including the empty / zero-division guard."""

from __future__ import annotations

from provael.scoring.asr import (
    attack_success_rate,
    breakdown,
    by_attack,
    by_task,
    overall_stat,
)
from provael.types import AttackResult


def _result(success: bool, attack: str = "roleplay", task: str = "reach", seed: int = 0) -> AttackResult:
    return AttackResult(
        task=task,
        attack=attack,
        family="instruction",
        seed=seed,
        success=success,
        steps=1,
        steps_to_success=1 if success else None,
        danger=0.8 if success else 0.0,
        threshold=0.6,
        original_instruction="reach for the cup on the table",
        adversarial_instruction="...",
    )


def test_empty_results_guard_zero_division() -> None:
    assert attack_success_rate([]) == 0.0
    stat = overall_stat([])
    assert stat.attempts == 0
    assert stat.successes == 0
    assert stat.asr == 0.0


def test_overall_rate() -> None:
    results = [_result(True), _result(False), _result(True), _result(False)]
    assert attack_success_rate(results) == 0.5
    stat = overall_stat(results)
    assert (stat.attempts, stat.successes, stat.asr) == (4, 2, 0.5)


def test_all_success_and_all_failure() -> None:
    assert attack_success_rate([_result(True), _result(True)]) == 1.0
    assert attack_success_rate([_result(False), _result(False)]) == 0.0


def test_breakdown_by_attack_groups_and_sorts() -> None:
    results = [
        _result(True, attack="roleplay"),
        _result(False, attack="roleplay"),
        _result(True, attack="paraphrase"),
    ]
    stats = by_attack(results)
    # Sorted keys for stable output.
    assert list(stats) == ["paraphrase", "roleplay"]
    assert stats["roleplay"].attempts == 2
    assert stats["roleplay"].successes == 1
    assert stats["roleplay"].asr == 0.5
    assert stats["paraphrase"].asr == 1.0


def test_breakdown_by_task() -> None:
    results = [
        _result(True, task="reach"),
        _result(False, task="reach"),
        _result(True, task="open"),
    ]
    stats = by_task(results)
    assert set(stats) == {"reach", "open"}
    assert stats["reach"].asr == 0.5
    assert stats["open"].asr == 1.0


def test_breakdown_is_generic_over_key() -> None:
    results = [_result(True, seed=0), _result(False, seed=1), _result(True, seed=0)]
    stats = breakdown(results, lambda r: str(r.seed))
    assert stats["0"].attempts == 2
    assert stats["0"].successes == 2
    assert stats["1"].asr == 0.0
