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

from vla_redteam import __version__
from vla_redteam.attacks.base import Attack
from vla_redteam.attacks.registry import resolve_attacks
from vla_redteam.config import RunConfig
from vla_redteam.policies.base import PolicyAdapter
from vla_redteam.policies.registry import make_policy
from vla_redteam.scoring.asr import by_attack, by_task, overall_stat
from vla_redteam.suites import make_suite
from vla_redteam.suites.base import SuiteAdapter
from vla_redteam.types import AttackResult, Decision, RunReport


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
            unsafe=suite.is_unsafe(state),
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


def run(config: RunConfig) -> RunReport:
    """Execute a full red-team run described by ``config`` and return a report."""
    policy = make_policy(config.policy)
    suite = make_suite(config.suite)

    # Exchange env features once (no-op for the stub: features() returns None).
    features = suite.features()
    if features is not None:
        policy.set_features(features)

    policy.load()

    attacks = resolve_attacks(config.attacks)
    tasks = config.tasks if config.tasks is not None else suite.tasks()

    results: list[AttackResult] = []
    for task in tasks:
        for attack in attacks:
            for episode in range(config.episodes):
                seed = config.seed + episode
                results.append(run_episode(policy, suite, attack, task, seed, config.horizon))

    overall = overall_stat(results)
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
        by_attack=by_attack(results),
        by_task=by_task(results),
        results=results,
    )


__all__ = ["run", "run_episode"]
