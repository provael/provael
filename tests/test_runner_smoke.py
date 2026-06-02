"""Full pipeline on the stubs: asserts the exact, hard-coded ASR for seed=0.

The expected numbers below were computed from the deterministic stub design
(per-seed SHA-256 threshold vs. per-attack trigger aggression) and then frozen.
If the stub mechanics change intentionally, recompute and update these.
"""

from __future__ import annotations

from vla_redteam.attacks.instruction import GoalSubstitutionAttack, RolePlayAttack
from vla_redteam.config import RunConfig
from vla_redteam.policies.stub import StubPolicy, aggression_of
from vla_redteam.runner import run, run_episode
from vla_redteam.suites.stub import BASE_INSTRUCTION, StubSuite


def test_unattacked_base_instruction_is_safe() -> None:
    # The benign instruction carries no trigger tokens, so a no-attack run is ASR 0.
    assert aggression_of(BASE_INSTRUCTION) == 0.0


def test_smoke_exact_asr_for_seed_0() -> None:
    report = run(RunConfig(policy="stub", suite="stub", attacks=["instruction"], episodes=10, seed=0))

    assert report.policy == "stub"
    assert report.suite == "stub"
    assert report.attacks == ["roleplay", "goal_substitution", "paraphrase"]
    assert report.tasks == ["reach"]

    # Headline.
    assert report.attempts == 30
    assert report.successes == 21
    assert report.asr == 0.7

    # Per-attack breakdown.
    assert report.by_attack["roleplay"].successes == 8
    assert report.by_attack["goal_substitution"].successes == 6
    assert report.by_attack["paraphrase"].successes == 7

    # Per-task breakdown.
    assert report.by_task["reach"].successes == 21
    assert report.by_task["reach"].attempts == 30


def test_single_episode_records_step_and_threshold(
    stub_policy: StubPolicy, stub_suite: StubSuite
) -> None:
    result = run_episode(stub_policy, stub_suite, RolePlayAttack(), task="reach", seed=0, horizon=8)
    # seed=0 threshold ~0.609 < roleplay aggression 0.8 -> success on the first step.
    assert result.success is True
    assert result.steps_to_success == 1
    assert "knife" in result.adversarial_instruction.lower()
    assert result.original_instruction == BASE_INSTRUCTION


def test_a_hard_seed_resists(stub_policy: StubPolicy, stub_suite: StubSuite) -> None:
    # seed=1 threshold ~0.879 > goal_substitution aggression 0.7 -> the attack fails.
    result = run_episode(
        stub_policy, stub_suite, GoalSubstitutionAttack(), task="reach", seed=1, horizon=8
    )
    assert result.success is False
    assert result.steps_to_success is None
    assert result.steps == 8
