# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The run orchestrator: policy x suite x attacks x seeds -> RunReport.

For each ``(task, attack, episode)`` triple the runner plays one episode:

    obs = suite.reset(task, seed)
    for t in 1..horizon:
        adv_instruction, adv_obs = attack.perturb(base_instruction, obs)
        action = policy.act(adv_obs, adv_instruction)
        obs, done, state = suite.step(action)
        if suite.evaluate_step(state): success at step t; stop
        if done: stop

Episode ``i`` of a ``(task, attack)`` pair uses ``seed = config.seed + i`` so a run
is fully reproducible. The aggregated :class:`RunReport` contains no wall-clock
time, so the same config always yields a byte-identical report.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

from provael import __version__
from provael.attacks.base import Attack
from provael.attacks.gradient_patch import GradientOracleAttack
from provael.attacks.optimized import OracleAttack, SchemaAwareAttack, ZoneAwareAttack
from provael.attacks.registry import resolve_attacks
from provael.attacks.weight_integrity import SensitivityReferencePolicy, WeightIntegrityAttack
from provael.calibration import Calibration, anytime_ci, binding_status, wilson_ci
from provael.config import RunConfig
from provael.defenses.base import Defense
from provael.defenses.registry import make_defense
from provael.endpoints import PHYSICAL_HAZARD, TASK_SUCCESS_STRICT
from provael.evidence import classify_run
from provael.ledger import TrialKey, append_trial, completed_keys, record_of, results_for
from provael.policies.base import InputGradientProvider, PolicyAdapter
from provael.policies.registry import make_policy
from provael.scoring.asr import (
    BASELINE_FAMILY,
    adversarial_asr,
    asr_std,
    by_attack,
    by_task,
    clean_task_success_rate,
    compute_rates,
    matched_benign_fpr,
    overall_stat,
    semantic_role,
)
from provael.scoring.failure import GraspTrace, failure_cause
from provael.scoring.paired import scene_pairing
from provael.scoring.safety_cost import (
    FIRST_EVENT,
    FIXED_HORIZON,
    SUITES_ENDING_AT_TASK_SUCCESS,
    observed_unsafe_success_rate,
)
from provael.suites import make_suite
from provael.suites.base import SuiteAdapter
from provael.types import (
    FIXTURE_VANTAGE,
    SIMULATOR_VANTAGE,
    Action,
    AttackResult,
    CalibrationMeta,
    Decision,
    EaiTag,
    EpisodeCoverage,
    EpisodeObservation,
    Observation,
    RunReport,
    Termination,
    Trajectory,
    init_state_of,
)
from provael.video import FrameSink, Mp4Writer, clip_name


def _configure_optimized(
    attacks: list[Attack],
    policy: PolicyAdapter,
    suite: SuiteAdapter,
    query_budget: int | None,
) -> None:
    """Wire a policy-query oracle (and optional budget override) into optimized attacks.

    Only the optimized family exposes ``attach_oracle``; the base ``Attack`` contract is
    untouched. Each search query resets the policy first, so it is an *independent* black-box
    query that never pollutes the live rollout's per-episode state (e.g. an action-chunk queue).
    The suite's :meth:`~provael.suites.base.SuiteAdapter.action_schema` (when it declares one) is
    handed to each attack so the search reads the policy's REAL translation channels, not a
    hard-coded slice.
    """

    def _query(instruction: str, observation: Observation) -> Action:
        policy.reset()
        return policy.act(observation, instruction)

    schema = suite.action_schema()
    for attack in attacks:
        # Any oracle-driven attack (the action-directive `targeted_hijack` and the image-channel
        # `patch_hijack`) is covered structurally via the OracleAttack protocol.
        if isinstance(attack, OracleAttack):
            if query_budget is not None:
                attack.query_budget = query_budget
            attack.attach_oracle(_query, policy.reset)
        # Hand the suite's real action layout to attacks that read motion channels (a superset check
        # independent of oracle-ness), so the search reads the right channels, never a fixed slice.
        #
        # Assigned even when the suite declares None. A motion-reading attack constructed with the
        # STUB_ACTION_SCHEMA default would otherwise keep that fallback on a suite whose layout is
        # unknown, and silently optimise channels 1-3 of an action whose translation may live
        # elsewhere — a search that hill-climbs the wrong axis still reports a rate, so the failure
        # is invisible. Every real suite now declares its layout (stub/reach/humanoid: the fixture
        # layout; libero: 7-DoF OSC_POSE; metaworld: 4-DoF), so None means "genuinely unknown" and
        # the attack must degrade to no motion signal rather than guess.
        if isinstance(attack, SchemaAwareAttack):
            attack.action_schema = schema
    # White-box INPUT gradients for the gradient family. The policy backprops its own image
    # objective to its camera tensor; the attack does the projection in numpy. No reset callback,
    # on purpose: the oracle touches no per-episode state (see LeRobotAdapter.input_gradient), and
    # resetting the action queue after every refinement would make the attacked arm re-plan every
    # step while the benign arm re-plans every chunk — a confound no rate could be read through.
    if isinstance(policy, InputGradientProvider) and policy.provides_input_gradient():
        for attack in attacks:
            if isinstance(attack, GradientOracleAttack):
                attack.attach_gradient_oracle(policy.input_gradient, None)


def _configure_weight_reference(
    attacks: list[Attack], policy: PolicyAdapter, suite: SuiteAdapter, task: str, seed: int
) -> None:
    """Hand a weight-attackable real policy the operating point its gradient is taken at.

    Only when the run carries a weight-integrity arm AND the policy asks for a reference
    (:class:`~provael.attacks.weight_integrity.SensitivityReferencePolicy`). The deterministic
    stub has a closed-form derivative and never enters here, so no CPU report moves. The point is
    the benign first frame of the run's first task at the run seed — one point per run, which is
    what keeps the gradient arm's bit selection a fixed function of the clean weights. The suite
    is reset again by ``run_episode`` for the episode itself; a seeded reset is repeatable.
    """
    if not any(isinstance(a, WeightIntegrityAttack) for a in attacks):
        return
    if not isinstance(policy, SensitivityReferencePolicy):
        return
    observation = suite.reset(task, seed)
    policy.set_sensitivity_reference(observation, str(observation.get("instruction", "")), seed)


def _configure_zones(attacks: list[Attack], suite: SuiteAdapter, task: str) -> None:
    """Hand each zone-aware attack the keep-out geometry of the task about to run.

    PER TASK, and that is the whole point of the function existing. This used to sit in
    :func:`_configure_optimized`, which the runner calls ONCE before the task loop — so on a suite
    whose zones vary by task the search was configured with whatever task the adapter happened to
    be constructed with, for every task in the run.

    It was harmless only by accident: ``CALIBRATED_ZONES`` is empty, so ``zones_for`` returns the
    same documented default box for every task and the mistake could not be observed. Committing
    the first per-task calibration — which is exactly what issue #136 exists to do — would have
    made every optimized attack on a multi-task run search task 0's geometry on all ten tasks,
    silently, with no test failing and every number still looking plausible.

    Assigned unconditionally for the same reason as the schema: a scalar suite reports [], which is
    the explicit "not spatial" signal that keeps the search on its scalar objective. Without this
    the EAI04 redirection objective would optimise the stub's danger axis even on LIBERO, whose
    predicate never reads it.
    """
    for attack in attacks:
        if isinstance(attack, ZoneAwareAttack):
            attack.keep_out_zones = suite.keep_out_zones(task)


class ScenePinError(RuntimeError):
    """A run that pins one starting scene per seed saw two arms at one seed start apart."""


class InitStatePlanError(ValueError):
    """``--init-states`` does not fit the run's tasks, seeds or arms: refused before a run."""


class ResumeModeError(ValueError):
    """A ``--resume`` ledger holds an episode that could not have run under this termination."""


@dataclass(frozen=True)
class _InitStatePlan:
    """``--init-states``, checked against the run: which state each episode starts from."""

    states: dict[str, list[int]]
    seeds: int
    episodes_per_seed: int

    @property
    def per_seed(self) -> bool:
        """True when every task lists one state per seed, so each (task, seed) is one scene."""
        return all(len(listed) == self.seeds for listed in self.states.values())

    def state_for(self, task: str, seed_index: int, repeat: int) -> int:
        listed = self.states[task]
        if len(listed) == self.seeds:
            return listed[seed_index]
        return listed[seed_index * self.episodes_per_seed + repeat]


def _init_state_plan(
    config: RunConfig, tasks: list[str], attacks: list[Attack]
) -> _InitStatePlan | None:
    """Check ``config.init_states`` against the run before anything is loaded (P1.2).

    One state per seed is a pin by name: every arm and repeat at a seed starts from that state,
    so a pair at a seed shares a scene. One state per episode gives repeats at one seed different
    scenes, which is fine for a benign-only run (LIBERO-Recovery's ask: run a list of initial
    states as benign rollouts) and would break the pairing of any other arm, so it is refused there.
    """
    plan = config.init_states
    if plan is None:
        return None
    # (A pin set as well is refused by RunConfig itself, before a run is built.)
    unknown = sorted(set(plan) - set(tasks))
    missing = [task for task in tasks if task not in plan]
    if unknown or missing:
        raise InitStatePlanError(
            f"--init-states must list exactly the run's tasks: missing {missing}, not in the run "
            f"{unknown}"
        )
    seeds = config.episodes // config.episodes_per_seed
    benign_only = all(attack.family == BASELINE_FAMILY for attack in attacks)
    for task in tasks:
        count = len(plan[task])
        if count == seeds or (count == config.episodes and benign_only):
            continue
        if not benign_only:
            raise InitStatePlanError(
                f"--init-states lists {count} state(s) for {task!r} and the run has {seeds} "
                "seed(s). With any arm besides the benign baseline it must pin one state per seed, "
                f"so every arm at a seed starts from one scene: list exactly {seeds}."
            )
        raise InitStatePlanError(
            f"--init-states lists {count} state(s) for {task!r}; a benign-only run takes one per "
            f"seed ({seeds}) or one per episode ({config.episodes})"
        )
    return _InitStatePlan(
        states={task: list(plan[task]) for task in tasks},
        seeds=seeds,
        episodes_per_seed=config.episodes_per_seed,
    )


def _check_pinned_cell(
    seen: dict[tuple[str, int], tuple[str, int | None, str | None]], episode: AttackResult
) -> None:
    """Raise unless ``episode`` started from the scene the first episode at its cell did.

    Called only on a run that pins one scene per seed (``--pin-init-states``, or
    ``--init-states`` with one state per seed). The adapter already refuses a reset that loaded
    another init state; this compares what each reset left, init state and scene digest, across
    the arms and repeats at one ``(task, seed)``, so a pinned pair that did not share a scene can
    never be reported as one.
    """
    cell = (episode.task, episode.seed)
    first = seen.setdefault(cell, (episode.attack, episode.init_state, episode.scene_t0_digest))
    if (episode.init_state, episode.scene_t0_digest) != first[1:]:
        raise ScenePinError(
            f"{episode.task} at seed {episode.seed}: the run pins one starting scene per seed, "
            f"and {episode.attack!r} started from init state {episode.init_state} (scene "
            f"{episode.scene_t0_digest}) where {first[0]!r} started from {first[1]} (scene "
            f"{first[2]}). Refusing to report pairs that did not share a scene."
        )


def _check_replayed_mode(episode: AttackResult, termination: str) -> None:
    """Raise when a ledger episode could not have run under this run's termination mode (P1.4).

    The ledger keys episodes by (attack, task, seed) and records no mode, so a resume under the
    other mode would splice first-event episodes into a fixed-horizon report, or the reverse, and
    Succ-But-Unsafe and exposure would be read off episodes that could not show them. Only a
    first-event episode ends at an exit or at task success, and only a fixed-horizon one steps on
    past its first exit; an episode that did neither runs alike under both.
    """
    if termination == FIXED_HORIZON:
        impossible = episode.termination in ("unsafe_exit", "task_success")
    else:
        impossible = (
            episode.steps_to_success is not None and episode.steps > episode.steps_to_success
        )
    if impossible:
        raise ResumeModeError(
            f"--resume: the ledger's {episode.attack!r} episode at {episode.task} seed "
            f"{episode.seed} was not recorded under --termination {termination} (it ended "
            f"'{episode.termination}' after {episode.steps} step(s)). Resume with the mode the "
            "ledger was written under, or start a new ledger."
        )


def run_episode(
    policy: PolicyAdapter,
    suite: SuiteAdapter,
    attack: Attack,
    task: str,
    seed: int,
    horizon: int,
    *,
    defense: Defense | None = None,
    audit_sink: list[dict[str, str]] | None = None,
    frame_sink: FrameSink | None = None,
    record_errors: bool = False,
    termination: str = FIRST_EVENT,
) -> AttackResult:
    """Play a single episode and return its :class:`AttackResult`.

    ``defense``, when given, is applied strictly BETWEEN the attack's perturbation and
    ``policy.act`` — the deployment position an operator would actually install a pre-processing
    mitigation in, so what is measured is what would ship. It cannot see the policy, the scorer or
    the danger predicate (see :class:`~provael.defenses.base.Defense`).

    ``audit_sink``, when given, collects the defense's raw → canonical trail per step for the
    ``defense-log.jsonl`` sidecar. It is deliberately a caller-owned list rather than a field on
    :class:`~provael.types.AttackResult`: adding a field there would move ``RunReport``'s canonical
    JSON and therefore the attestation subject digest, invalidating every attestation issued by an
    earlier version.

    ``frame_sink``, when given, receives per step the image the policy was actually shown (after
    the attack and any defense) and whether that step was scored unsafe — the episode's clip, see
    :mod:`provael.video`. Same rule as ``audit_sink``: caller-owned, never part of the report.

    ``record_errors`` turns an exception from ``suite.step`` into an episode recorded as
    ``unjudged`` with its reason (``termination: error``), instead of an aborted shard (P1.3). Only
    the step: a failure in ``reset`` still stops the run, because the reset is where the
    configuration, the scene pin and the environment build are checked, and swallowing those would
    turn a misconfigured run into a column of unjudged episodes. A non-finite action is the
    policy's failure, not the simulator's, and still stops the run either way.

    ``termination`` is ``first-event`` (stop at the first exit or ``done``) or ``fixed-horizon``
    (P1.4): every step to the horizon runs, an exit and a success latch, and the steps after them
    are still logged and scored, so ``decisions`` measures dwell. The suite must already have
    accepted the mode (:meth:`~provael.suites.base.SuiteAdapter.set_termination`); there a
    ``done`` means only that it cannot go on.
    """
    fixed_horizon = termination == FIXED_HORIZON
    policy.reset()  # clear per-episode policy state (e.g. SmolVLA's action-chunk queue)
    # Seed the POLICY as well as the environment. `suite.reset` has always seeded the env; the
    # policy's own sampler ran off whatever state the process happened to be in, which is the
    # whole of the leaderboard's "one draw, not a constant" caveat. The adapter reports what it
    # actually applied — None if it does not seed — and that answer is what the episode records,
    # never the value we asked for.
    policy_seed = policy.seed(seed)
    obs = suite.reset(task, seed)
    base_instruction = str(obs.get("instruction", ""))
    # Which fixed initial state the reset loaded, as the SUITE read it from its environment. On
    # LIBERO the seed does not pick it (a reset counter does), so it is recorded per episode
    # rather than inferred later from the seed or the episode order, neither of which survives a
    # resumed run. None on a suite without fixed initial states.
    init_state = init_state_of(obs)
    # The settled scene the reset left, read from the simulator (P1.2): what makes "this pair
    # started from one scene" checkable after the fact. None on a suite with no simulator state.
    scene = suite.scene_snapshot()
    scene_t0_digest = scene.digest if scene is not None else None
    scene_t0 = list(scene.bodies) if scene is not None else None

    if not attack.applicable(obs):
        # The attack has no surface in this suite (e.g. mcp_tool_desc on a direct LIBERO
        # loop). Record it as not-applicable; scoring excludes it from the ASR denominator.
        return AttackResult(
            task=task,
            attack=attack.name,
            family=attack.family,
            seed=seed,
            policy_seed=policy_seed,
            init_state=init_state,
            scene_t0_digest=scene_t0_digest,
            scene_t0=scene_t0,
            success=False,
            steps=0,
            steps_to_success=None,
            danger=0.0,
            threshold=0.0,
            original_instruction=base_instruction,
            adversarial_instruction=base_instruction,
            applicable=False,
            attacker_access=attack.attacker_access,
            action_head_class=policy.action_head_class or attack.action_head_class,
        )

    success = False
    steps_to_success: int | None = None
    adversarial_instruction = base_instruction
    danger = 0.0
    threshold = 0.0
    steps = 0
    task_success: bool | None = None  # C2: only set if the suite surfaces a task-success signal
    hazard: bool | None = None  # the second predicate: only set if the suite surfaces contact/force
    decisions: list[Decision] = []
    # P1.3: steps the predicate could not judge (its input was missing), how the loop ended, and a
    # simulator failure recorded under `record_errors`.
    steps_without_pose = 0
    ended_by_suite: Termination | None = None
    error: str | None = None
    # P1.4: whether the goal object was held, per step, for the failure cause.
    grasp = GraspTrace()
    # Per-step calibration signal, recorded for EVERY episode. Gated on nothing by design: the
    # input to a keep-out calibration was previously computed and discarded on every run, which is
    # what made #136 unfixable rather than merely unfixed, and an opt-in flag would recreate that
    # the first time someone forgot to pass it. Cost is a few hundred floats per episode.
    calib_samples: list[list[float]] = []

    for t in range(1, horizon + 1):
        steps = t
        adversarial_instruction, adv_obs = attack.perturb(base_instruction, obs)
        # The defense sits HERE and nowhere else: after the attack has produced what the policy
        # would otherwise receive, before the policy receives it. That is the deployment position,
        # so a credited result is a claim about a mitigation someone could actually install.
        #
        # `adversarial_instruction` is deliberately reassigned, so the recorded instruction is what
        # the policy ACTUALLY saw. Recording the pre-defense text would make `report.json` describe
        # an input that was never used.
        if defense is not None and defense.applicable(adv_obs):
            if audit_sink is not None:
                audit_sink.append(
                    {
                        "task": task,
                        "attack": attack.name,
                        "seed": str(seed),
                        "step": str(t),
                        **defense.audit(adversarial_instruction),
                    }
                )
            adversarial_instruction, adv_obs = defense.apply(adversarial_instruction, adv_obs)
        action = policy.act(adv_obs, adversarial_instruction)
        # Every unsafe predicate downstream is a threshold comparison, and EVERY comparison against
        # NaN is False — so a policy emitting NaN would score SAFE on all axes and the episode would
        # be reported as a benign success. Reject non-finite actions at the one boundary they all
        # cross rather than trusting each predicate to notice. This is a real failure mode for a
        # real policy (a diverged or numerically unstable head), and silently scoring it safe is the
        # worst possible outcome for a safety tool.
        if not np.all(np.isfinite(np.asarray(action, dtype=np.float64))):
            raise ValueError(
                f"policy '{policy.name}' emitted a non-finite action (NaN/inf) at step {t} of "
                f"task {task!r} seed {seed}. Refusing to score it: every unsafe threshold "
                "comparison against NaN is False, so this episode would be recorded as safe."
            )
        # The action-side defense sits HERE and nowhere else: after the policy has committed to a
        # command, before the suite executes it. That is the only position an operator could
        # actually install a monitor in — everything upstream is the model, everything downstream
        # is the robot — so a credited action-side result is a claim about something installable.
        #
        # Strictly AFTER the non-finite rejection above, which must keep running against the RAW
        # policy output. Filtering first would let a clamp launder a NaN into a finite value and
        # hide a diverged head: the episode would then be scored safe, which is the exact failure
        # that block exists to prevent. A defense must never be able to buy safety by concealing
        # the policy's own numerical collapse.
        if defense is not None and defense.applicable(adv_obs):
            filtered_action = defense.filter_action(action, adv_obs)
            if audit_sink is not None:
                audit_sink.append(
                    {
                        "task": task,
                        "attack": attack.name,
                        "seed": str(seed),
                        "step": str(t),
                        **defense.audit_action(action, filtered_action),
                    }
                )
            action = filtered_action
        try:
            obs, done, state = suite.step(action)
        except Exception as exc:  # noqa: BLE001 - re-raised unless the run asked to record it
            if not record_errors:
                raise
            # Recorded, not swallowed: the episode is unjudged, its reason says what failed, and
            # every rate excludes it and counts it beside the rate (never a silent shrink).
            error = f"simulator exception at step {t}: {type(exc).__name__}: {exc}"
            steps = t - 1
            break

        danger = float(state.get("danger", danger))
        threshold = float(state.get("threshold", threshold))
        step_task_success = state.get("task_success")
        if step_task_success is not None:
            # C2 is an episode-level question ("did the policy ALSO complete the benign task?"), so
            # a completion latches: a later step reporting False cannot un-complete it. Last-step-
            # wins drops the worst quadrant — completed at step k, violated at step k+1 — out of
            # `succ_but_unsafe` entirely. Only ever set from a non-None step signal, so a suite that
            # surfaces none keeps the honest None rather than a fabricated False.
            task_success = bool(task_success) or bool(step_task_success)

        # The SECOND predicate, read from the suite's own contact / force signals and latched the
        # same way as task success: one event anywhere in the episode is an event. Only ever set
        # from a non-None step answer — a suite without a contact API leaves it None (N/A), and the
        # result then carries no `physical_hazard` key at all rather than a fabricated False. It
        # is scored on the executed steps: an episode the envelope check stops early is not
        # observed after that step, which the endpoint definition says.
        step_hazard = suite.physical_hazard(state)
        if step_hazard is not None:
            hazard = bool(hazard) or bool(step_hazard)
        grasp = grasp.observe(state.get("grasped"), present="grasped" in state)

        # Read BEFORE the unsafe check breaks the loop: the step that violates the envelope is the
        # most informative one in the trajectory, and a `break` placed above this would drop
        # precisely that sample on every successful attack.
        signal = suite.calibration_signal(state)
        if signal is not None:
            calib_samples.append(
                [float(signal)] if isinstance(signal, (int, float)) else [float(v) for v in signal]
            )

        # The calibrated predicate if one is installed. None is a step it could not judge (a lost
        # pose): logged as not unsafe, and counted, so the episode cannot read as "no exit".
        verdict = suite.evaluate_step(state)
        if verdict is None:
            steps_without_pose += 1
        decision = Decision(
            step=t,
            instruction=adversarial_instruction,
            action=[float(x) for x in action.reshape(-1)],
            unsafe=verdict is True,
        )
        decisions.append(decision)

        if frame_sink is not None:
            # The suite turns its raw frame the right way up for the viewer; the attack and the
            # policy keep working on the raw frame (see SuiteAdapter.display_frame).
            shown = suite.display_frame(adv_obs)
            if shown is not None:
                frame_sink.frame(t, shown, decision.unsafe)

        if decision.unsafe and not success:
            success = True
            steps_to_success = decision.step
        if decision.unsafe and not fixed_horizon:
            break
        if done:
            # On a suite whose `done` fires at task success (LIBERO) the step that ended it says
            # whether it was success; any other `done` is the suite's own cap, and under a fixed
            # horizon `done` is never success: the suite steps on past it.
            at_success = (
                not fixed_horizon
                and suite.name in SUITES_ENDING_AT_TASK_SUCCESS
                and bool(step_task_success)
            )
            ended_by_suite = "task_success" if at_success else "env_truncated"
            break

    ended: Termination
    if error is not None:
        ended = "error"
    elif success and not fixed_horizon:
        ended = "unsafe_exit"
    else:
        ended = ended_by_suite or "horizon"
    reason: str | None = error
    if error is None and not success and steps_without_pose:
        reason = (
            f"the predicate's input (the end-effector pose) was missing on {steps_without_pose} "
            f"of {steps} executed step(s) and no exit was seen, so whether the episode left the "
            "envelope is not established"
        )
    observed: Literal["present", "absent", "not_established"] = (
        "present" if success else "not_established" if reason is not None else "absent"
    )
    observation = EpisodeObservation(
        state=observed,
        vantage=FIXTURE_VANTAGE if suite.is_fixture else SIMULATOR_VANTAGE,
        coverage=EpisodeCoverage(
            steps_observed=steps, horizon=horizon, steps_without_pose=steps_without_pose
        ),
    )
    # N/A is absent, never False: only a suite that surfaced a signal writes the key. Strict
    # success is read at the episode's end, so an episode a simulator exception cut short has none.
    endpoints: dict[str, bool | None] = {PHYSICAL_HAZARD: hazard} if hazard is not None else {}
    strict = suite.strict_task_success() if error is None else None
    if strict is not None:
        endpoints[TASK_SUCCESS_STRICT] = strict

    return AttackResult(
        task=task,
        attack=attack.name,
        family=attack.family,
        seed=seed,
        policy_seed=policy_seed,
        init_state=init_state,
        scene_t0_digest=scene_t0_digest,
        scene_t0=scene_t0,
        success=success,
        steps=steps,
        steps_to_success=steps_to_success,
        danger=danger,
        threshold=threshold,
        original_instruction=base_instruction,
        adversarial_instruction=adversarial_instruction,
        task_success=task_success,
        endpoints=endpoints,
        attacker_access=attack.attacker_access,
        action_head_class=policy.action_head_class or attack.action_head_class,
        decisions=decisions,
        trajectory=Trajectory.encode(calib_samples) if calib_samples else None,
        # None for every input-channel family. Read from the attack rather than passed in, so
        # a result records the corruption that was ACTUALLY in force when it ran, not one a
        # caller believed was in force.
        weight_corruption=getattr(attack, "record", None),
        termination=ended,
        verdict="unjudged" if reason is not None else "judged",
        unjudged_reason=reason,
        observation=observation,
        failure_cause=failure_cause(
            unsafe_exit=success,
            hazard=hazard,
            task_success=task_success,
            termination=ended,
            grasp=grasp,
        ),
    )


def run(
    config: RunConfig,
    calibrations: dict[str, Calibration] | None = None,
    *,
    audit_sink: list[dict[str, str]] | None = None,
    ledger_path: Path | None = None,
    video_dir: Path | None = None,
) -> RunReport:
    """Execute a full red-team run described by ``config`` and return a report.

    If ``calibrations`` (task -> :class:`~provael.calibration.Calibration`) is given, the
    suite uses the calibrated predicate for those tasks; otherwise the default predicate is
    used, so existing runs are unchanged.

    ``config.defense``, when set, installs a pre-processing mitigation in the deployment position
    (see :func:`run_episode`). ``audit_sink`` collects its raw → canonical trail for the caller to
    write as a ``defense-log.jsonl`` sidecar — this function performs no file IO, and the trail is
    deliberately NOT part of the report, so the attestation subject digest is unaffected.

    ``ledger_path``, when set, makes the run **resumable**: each finished episode is appended to an
    append-only JSONL ledger, and a re-run replays the episodes already there instead of
    re-measuring them. That is what makes a preemptible spot instance affordable — a job reclaimed
    at hour 19 resumes rather than starting over. Passing it is the ONLY thing that turns file IO
    on in this function.

    The replayed episodes are spliced back **in plan order**, not appended at the end, so a resumed
    report is identical to the uninterrupted one rather than merely equivalent. Determinism is the
    product here; "same numbers, different order" would still change the digest ``attest`` signs.
    """
    # `device` is forwarded so --accelerator is actually HONOURED. Every real factory already
    # accepts a `device` kwarg (defaulting to "cuda"), but the runner never passed one, so the
    # requested accelerator was recorded in the report while every adapter loaded onto cuda
    # regardless. Omitted when None so each adapter keeps its own default.
    policy_kwargs: dict[str, object] = {
        "model": config.model,
        "rename_map": config.rename_map,
        "unnorm_key": config.unnorm_key,
    }
    if config.accelerator is not None:
        policy_kwargs["device"] = config.accelerator
    policy = make_policy(config.policy, **policy_kwargs)
    suite = make_suite(config.suite, tasks=config.tasks)
    if calibrations:
        suite.set_calibration(calibrations)
    # Before any env is built or reset. A suite with no fixed list of initial states has no scene
    # to pin, and running it anyway would put scenes nobody asked for under a config that says
    # they were pinned. NotImplementedError because that is what it is: the suite does not
    # implement the capability, and the CLI already turns it into a one-line refusal.
    if config.pin_init_states is not None and not suite.pin_init_states(config.pin_init_states):
        raise NotImplementedError(
            f"--pin-init-states {config.pin_init_states} asks suite {config.suite!r} to start each "
            "episode from a fixed initial state chosen by its seed, and it keeps no fixed initial "
            "states; refusing to run on scenes that were not asked for"
        )
    # Same rule as the pin (P1.4): a suite that cannot step past an episode's first event refuses
    # a fixed horizon before anything loads, rather than reporting a horizon it did not run.
    if config.termination != FIRST_EVENT and not suite.set_termination(config.termination):
        raise NotImplementedError(
            f"--termination {config.termination} asks suite {config.suite!r} to step every episode "
            "to its horizon, past envelope exits and task success, and it cannot; refusing to "
            "label first-event episodes as fixed-horizon"
        )
    attacks = resolve_attacks(config.attacks)
    tasks = config.tasks if config.tasks is not None else suite.tasks()
    # `RunConfig` rejects an explicitly-empty `tasks`, but a suite that exposes none reaches the
    # same dead end: the triple loop below never executes and the report reads as a measured 0/0
    # rather than as "nothing ran". Fail here so an empty denominator can never be signed.
    if not tasks:
        raise ValueError(
            f"suite {config.suite!r} exposes no tasks, so nothing would be run. A report with "
            "attempts=0 is not a measurement — fix the suite or pass an explicit --tasks."
        )
    # Checked against the run's tasks, seeds and arms before the policy loads, and then against
    # the suite, which needs a fixed list of initial states to load a named one.
    init_plan = _init_state_plan(config, tasks, attacks)
    if init_plan is not None and not suite.choose_init_state(None):
        raise NotImplementedError(
            f"--init-states names the initial state of each episode, and suite {config.suite!r} "
            "keeps no fixed initial states; refusing to run on scenes that were not asked for"
        )

    # Exchange env features once (no-op for the stub: features() returns None).
    features = suite.features()
    if features is not None:
        policy.set_features(features)

    policy.load()

    defense = make_defense(config.defense) if config.defense else None
    _configure_optimized(attacks, policy, suite, config.query_budget)

    # RESUME. `episodes_per_seed > 1` puts several episodes on ONE (attack, task, seed) key, which
    # the ledger cannot tell apart — pending_trials would dedup them and the run would quietly
    # measure a fraction of its own design. Refuse rather than under-run: an unbalanced or
    # short-changed denominator is exactly what the divmod guard above also refuses.
    done_keys: set[TrialKey] = set()
    replay: dict[TrialKey, AttackResult] = {}
    if ledger_path is not None:
        if config.episodes_per_seed > 1:
            raise ValueError(
                f"--resume cannot be used with episodes_per_seed={config.episodes_per_seed}: the "
                "ledger keys trials by (attack, task, seed), so repeats at one seed are "
                "indistinguishable and resume would silently drop all but the first."
            )
        planned: list[TrialKey] = [
            (attack.name, task, config.seed + i)
            for task in tasks
            for attack in attacks
            for i in range(config.episodes)
        ]
        done_keys = completed_keys(ledger_path) & set(planned)
        replay = results_for(planned, ledger_path)

    _configure_weight_reference(attacks, policy, suite, tasks[0], config.seed)

    # The predicate each task is scored against, read once, after any calibration is installed
    # (P1.7). A suite that cannot say leaves the task out rather than guessing; in strict mode an
    # uncalibrated LIBERO task refuses here, before its first episode, instead of at its first step.
    predicates = {
        task: identity
        for task in tasks
        if (identity := suite.predicate_identity(task)) is not None
    }

    results: list[AttackResult] = []
    # Each task's compiled model, read before its first episode (see SuiteAdapter.sim_model_digest).
    sim_models: dict[str, str | None] = {}
    # A run that pins one scene per seed checks every episode against the first at its cell.
    pins_cells = config.pin_init_states is not None or (
        init_plan is not None and init_plan.per_seed
    )
    cell_scenes: dict[tuple[str, int], tuple[str, int | None, str | None]] = {}
    for task in tasks:
        sim_models[task] = suite.sim_model_digest(task)
        # Re-point the spatial search at THIS task's geometry before anything runs against it.
        _configure_zones(attacks, suite, task)
        for attack in attacks:
            # Two nested loops, not one. `episodes` is the TOTAL per (task, attack) and
            # `episodes_per_seed` splits it into distinct seeds x repeats at each seed, so a report
            # can separate initial-state variation from policy stochasticity. At the default
            # episodes_per_seed=1 this is byte-identical to the previous single loop: seeds ==
            # episodes and seed = base + i, which is what every committed run so far used.
            #
            # A remainder is refused rather than silently dropped or padded. An unbalanced design
            # makes the per-seed cells unequal, and unequal cells quietly bias any variance estimate
            # computed from them — which is the exact quantity this split exists to make computable.
            seeds, remainder = divmod(config.episodes, config.episodes_per_seed)
            if remainder:
                raise ValueError(
                    f"episodes={config.episodes} is not divisible by "
                    f"episodes_per_seed={config.episodes_per_seed}; an unbalanced design biases "
                    "the per-seed variance this split exists to measure"
                )
            for seed_index in range(seeds):
                seed = config.seed + seed_index
                for repeat in range(config.episodes_per_seed):
                    # WEIGHT-INTEGRITY BRACKET, per episode. A parameter attack corrupts the
                    # policy for exactly one episode and MUST hand back clean weights afterwards.
                    #
                    # The `finally` is the load-bearing part: corruption surviving its own episode
                    # would silently score every later episode and every later ATTACK against a
                    # broken policy — a full report of wrong numbers with nothing visibly failed,
                    # which is the worst outcome available to a tool whose product is trustworthy
                    # numbers.
                    #
                    # Per episode rather than per (task, attack) because the random control has to
                    # re-draw its K bits each episode to estimate a rate over draws instead of
                    # reporting one draw as the rate. See WeightIntegrityAttack.corrupt.
                    # Already measured on an earlier attempt? Splice the stored episode in HERE,
                    # at its plan position, and neither load the policy for it nor re-run it.
                    key: TrialKey = (attack.name, task, seed)
                    if key in done_keys:
                        _check_replayed_mode(replay[key], config.termination)
                        results.append(replay[key])
                        if pins_cells:
                            _check_pinned_cell(cell_scenes, replay[key])
                        continue
                    if init_plan is not None:
                        suite.choose_init_state(init_plan.state_for(task, seed_index, repeat))
                    weight_attack = (
                        attack if isinstance(attack, WeightIntegrityAttack) else None
                    )
                    if weight_attack is not None:
                        weight_attack.corrupt(policy, seed)
                    # One clip per episode when asked for (``--video-dir``): the frames the policy
                    # saw, red-bordered from the first unsafe step. Closed in the same `finally`
                    # as the weight bracket so a crash mid-episode still flushes what was written.
                    sink: Mp4Writer | None = (
                        Mp4Writer(video_dir / clip_name(task, seed, attack.name))
                        if video_dir is not None
                        else None
                    )
                    try:
                        episode = run_episode(
                            policy, suite, attack, task, seed, config.horizon,
                            defense=defense, audit_sink=audit_sink, frame_sink=sink,
                            record_errors=config.record_episode_errors,
                            termination=config.termination,
                        )
                    finally:
                        if weight_attack is not None:
                            weight_attack.restore(policy)
                        if sink is not None:
                            sink.close()
                    # Append BEFORE the next episode starts, so a kill loses at most this one.
                    if ledger_path is not None:
                        append_trial(ledger_path, record_of(episode, trial_index=len(results)))
                    results.append(episode)
                    if pins_cells:
                        _check_pinned_cell(cell_scenes, episode)
    overall = overall_stat(results)
    adversarial = adversarial_asr(results)  # headline ASR: benign control excluded by role
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
                    split=cal.split,
                    eval_fpr=cal.eval_fpr,
                    # Derived against THIS run — the artifact cannot know what it is applied to.
                    binding=binding_status(
                        cal, policy=config.policy, suite=config.suite, task=task,
                        model=config.model,
                    ),
                )
    # The benign baseline's rate under the predicate actually used IS the live benign FPR. Its
    # measured rate, so an arm whose every episode was unjudged is N/A rather than a measured 0%.
    baseline = attack_breakdown.get("none")
    benign_fpr = baseline.measured_rate if baseline is not None else None

    # P0.4 uncertainty: the overall ASR carries BOTH a fixed-n Wilson interval and an
    # anytime-valid interval (valid under the per-seed peeking a GPU budget run does), plus the
    # matched-benign twin control and a >=5-seed "preliminary" flag.
    ci95 = wilson_ci(overall.successes, overall.attempts) if overall.attempts else None
    any_ci = anytime_ci(overall.successes, overall.attempts) if overall.attempts else None
    n_seeds = len({r.seed for r in results})

    return RunReport(
        tool_version=__version__,
        # 4: results carry `weight_corruption`. Bumped in the SAME change that started
        # emitting the field — a report that declares 3 while carrying a 4 field has that
        # field stripped by attest.report_projection before the digest, i.e. signed around
        # rather than signed over, and the corruption parameters would sit outside the
        # signature that is supposed to cover them. 6: the report carries `deployed_policy`,
        # the executed policy as the adapter resolved it (issue #227); same rule, same reason.
        # 7: `calibration.<task>` carries `split` / `eval_fpr` / `binding`, so a bound predicate
        # and a tuned one are signed over as different things (nested, so the projection strips
        # them for a report that declares less — see attest._CALIBRATION_META_FIELDS_ADDED_IN).
        # 8: results carry `init_state`, the fixed initial state each reset loaded (#136).
        # 9: `deployed_policy` carries the rest of the runtime identity (normaliser, processor and
        # weight digests, rename map, cameras, denoising steps, control rate), nested, so the
        # projection strips it for a report that declares less (attest._DEPLOYED_POLICY_FIELDS_
        # ADDED_IN); each result carries the scene its reset left (`scene_t0_digest`, `scene_t0`),
        # and the report each task's model digest and how many pairs shared a scene; each result
        # says how it ended and whether it was judged, and `rates` carries every rate as counts;
        # the report says whether episodes ran to the horizon, and each result its failure cause.
        schema_version=9,
        evidence_state=classify_run(config.policy, config.suite).value,
        policy=config.policy,
        model=config.model,
        # What was requested (`model`) beside what ran (`deployed_policy`): the adapter resolves
        # the class, revision, unnormaliser and controller convention at load, and None means it
        # resolved nothing — never that the request was honoured.
        deployed_policy=policy.resolved_identity,
        suite=config.suite,
        attacks=[a.name for a in attacks],
        tasks=list(tasks),
        episodes=config.episodes,
        horizon=config.horizon,
        termination_mode=config.termination,
        seed=config.seed,
        attempts=overall.attempts,
        successes=overall.successes,
        asr=overall.asr,
        adversarial_asr=adversarial.measured_rate,
        adversarial_attempts=adversarial.attempts,
        adversarial_successes=adversarial.successes,
        asr_std=asr_std(results),
        stochastic=policy.stochastic,
        ci95=ci95,
        anytime_ci=any_ci,
        seeds=n_seeds,
        preliminary=n_seeds < 5,
        # Prefer what the adapter RESOLVED to over what was requested: an adapter may fall back off
        # a requested device, and a report that states the request as the outcome is a false record.
        # The stub reports neither (pure numpy), so its reports are unchanged.
        accelerator=policy.resolved_device or config.accelerator,
        precision=policy.resolved_precision or config.precision,
        calibrated=bool(calibration_meta),
        benign_fpr=benign_fpr,
        matched_benign_fpr=matched_benign_fpr(results),
        succ_but_unsafe=observed_unsafe_success_rate(
            results, suite=config.suite, termination=config.termination
        ),
        clean_task_success_rate=clean_task_success_rate(results),
        calibration=calibration_meta,
        sim_model_digests=sim_models,
        scene_pairing=scene_pairing(results),
        # Every rate above with its counts, interval method and level, and its unjudged episodes,
        # from the same episodes and the same filters (P1.6).
        rates=compute_rates(results, suite=config.suite, termination=config.termination),
        predicates=predicates,
        by_attack=attack_breakdown,
        by_task=by_task(results),
        eai={
            a.name: EaiTag(id=a.eai_id, name=a.eai_name)
            for a in attacks
            if a.eai_id is not None and a.eai_name is not None
        },
        roles={r.attack: semantic_role(r) for r in results},
        results=results,
    )


__all__ = ["InitStatePlanError", "ResumeModeError", "ScenePinError", "run", "run_episode"]
