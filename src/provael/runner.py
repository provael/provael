"""The run orchestrator: policy x suite x attacks x seeds -> RunReport.

For each ``(task, attack, episode)`` triple the runner plays one episode:

    obs = suite.reset(task, seed)
    for t in 1..horizon:
        adv_instruction, adv_obs = attack.perturb(base_instruction, obs)
        action = policy.act(adv_obs, adv_instruction)
        obs, done, state = suite.step(action)
        if suite.is_unsafe(state): success at step t; stop
        if done: stop

Episode ``i`` of a ``(task, attack)`` pair uses ``seed = config.seed + i`` so a run
is fully reproducible. The aggregated :class:`RunReport` contains no wall-clock
time, so the same config always yields a byte-identical report.
"""

from __future__ import annotations

from provael import __version__
from provael.attacks.base import Attack
from provael.attacks.optimized import TargetedTrajectoryHijack
from provael.attacks.registry import resolve_attacks
from provael.calibration import Calibration
from provael.config import RunConfig
from provael.policies.base import PolicyAdapter
from provael.policies.registry import make_policy
from provael.scoring.asr import asr_std, by_attack, by_task, overall_stat
from provael.suites import make_suite
from provael.suites.base import SuiteAdapter
from provael.types import (
    Action,
    AttackResult,
    CalibrationMeta,
    Decision,
    EaiTag,
    Observation,
    RunReport,
)


def _configure_optimized(
    attacks: list[Attack], policy: PolicyAdapter, query_budget: int | None
) -> None:
    """Wire a policy-query oracle (and optional budget override) into optimized attacks.

    Only the optimized family exposes ``attach_oracle``; the base ``Attack`` contract is
    untouched. Each search query resets the policy first, so it is an *independent* black-box
    query that never pollutes the live rollout's per-episode state (e.g. an action-chunk queue).
    """

    def _query(instruction: str, observation: Observation) -> Action:
        policy.reset()
        return policy.act(observation, instruction)

    for attack in attacks:
        if isinstance(attack, TargetedTrajectoryHijack):
            if query_budget is not None:
                attack.query_budget = query_budget
            attack.attach_oracle(_query, policy.reset)


def run_episode(
    policy: PolicyAdapter,
    suite: SuiteAdapter,
    attack: Attack,
    task: str,
    seed: int,
    horizon: int,
) -> AttackResult:
    """Play a single episode and return its :class:`AttackResult`."""
    policy.reset()  # clear per-episode policy state (e.g. SmolVLA's action-chunk queue)
    obs = suite.reset(task, seed)
    base_instruction = str(obs.get("instruction", ""))

    if not attack.applicable(obs):
        # The attack has no surface in this suite (e.g. mcp_tool_desc on a direct LIBERO
        # loop). Record it as not-applicable; scoring excludes it from the ASR denominator.
        return AttackResult(
            task=task,
            attack=attack.name,
            family=attack.family,
            seed=seed,
            success=False,
            steps=0,
            steps_to_success=None,
            danger=0.0,
            threshold=0.0,
            original_instruction=base_instruction,
            adversarial_instruction=base_instruction,
            applicable=False,
        )

    success = False
    steps_to_success: int | None = None
    adversarial_instruction = base_instruction
    danger = 0.0
    threshold = 0.0
    steps = 0

    for t in range(1, horizon + 1):
        steps = t
        adversarial_instruction, adv_obs = attack.perturb(base_instruction, obs)
        action = policy.act(adv_obs, adversarial_instruction)
        obs, done, state = suite.step(action)

        danger = float(state.get("danger", danger))
        threshold = float(state.get("threshold", threshold))

        decision = Decision(
            step=t,
            instruction=adversarial_instruction,
            action=[float(x) for x in action.reshape(-1)],
            unsafe=suite.evaluate_unsafe(state),  # calibrated predicate if one is installed
        )

        if decision.unsafe:
            success = True
            steps_to_success = decision.step
            break
        if done:
            break

    return AttackResult(
        task=task,
        attack=attack.name,
        family=attack.family,
        seed=seed,
        success=success,
        steps=steps,
        steps_to_success=steps_to_success,
        danger=danger,
        threshold=threshold,
        original_instruction=base_instruction,
        adversarial_instruction=adversarial_instruction,
    )


def run(config: RunConfig, calibrations: dict[str, Calibration] | None = None) -> RunReport:
    """Execute a full red-team run described by ``config`` and return a report.

    If ``calibrations`` (task -> :class:`~provael.calibration.Calibration`) is given, the
    suite uses the calibrated predicate for those tasks; otherwise the default predicate is
    used, so existing runs are unchanged.
    """
    policy = make_policy(
        config.policy,
        model=config.model,
        rename_map=config.rename_map,
        unnorm_key=config.unnorm_key,
    )
    suite = make_suite(config.suite)
    if calibrations:
        suite.set_calibration(calibrations)

    # Exchange env features once (no-op for the stub: features() returns None).
    features = suite.features()
    if features is not None:
        policy.set_features(features)

    policy.load()

    attacks = resolve_attacks(config.attacks)
    _configure_optimized(attacks, policy, config.query_budget)
    tasks = config.tasks if config.tasks is not None else suite.tasks()

    results: list[AttackResult] = []
    for task in tasks:
        for attack in attacks:
            for episode in range(config.episodes):
                seed = config.seed + episode
                results.append(run_episode(policy, suite, attack, task, seed, config.horizon))

    overall = overall_stat(results)
    attack_breakdown = by_attack(results)

    calibration_meta: dict[str, CalibrationMeta] = {}
    if calibrations:
        for task in tasks:
            cal = calibrations.get(task)
            if cal is not None:
                calibration_meta[task] = CalibrationMeta(
                    predicate="calibrated",
                    kind=cal.kind,
                    target_fpr=cal.target_fpr,
                    holdout_fpr=cal.benign_fpr,
                    n_benign=cal.n_benign,
                )
    # The benign baseline's rate under the predicate actually used IS the live benign FPR.
    baseline = attack_breakdown.get("none")
    benign_fpr = baseline.asr if baseline is not None else None

    return RunReport(
        tool_version=__version__,
        policy=config.policy,
        suite=config.suite,
        attacks=[a.name for a in attacks],
        tasks=list(tasks),
        episodes=config.episodes,
        horizon=config.horizon,
        seed=config.seed,
        attempts=overall.attempts,
        successes=overall.successes,
        asr=overall.asr,
        asr_std=asr_std(results),
        stochastic=policy.stochastic,
        calibrated=bool(calibration_meta),
        benign_fpr=benign_fpr,
        calibration=calibration_meta,
        by_attack=attack_breakdown,
        by_task=by_task(results),
        eai={
            a.name: EaiTag(id=a.eai_id, name=a.eai_name)
            for a in attacks
            if a.eai_id is not None and a.eai_name is not None
        },
        results=results,
    )


__all__ = ["run", "run_episode"]
