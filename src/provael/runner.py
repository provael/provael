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

import numpy as np

from provael import __version__
from provael.attacks.base import Attack
from provael.attacks.optimized import OracleAttack, SchemaAwareAttack, ZoneAwareAttack
from provael.attacks.registry import resolve_attacks
from provael.attacks.weight_integrity import WeightIntegrityAttack
from provael.calibration import Calibration, anytime_ci, wilson_ci
from provael.config import RunConfig
from provael.defenses.base import Defense
from provael.defenses.registry import make_defense
from provael.evidence import classify_run
from provael.policies.base import PolicyAdapter
from provael.policies.registry import make_policy
from provael.scoring.asr import (
    adversarial_asr,
    asr_std,
    by_attack,
    by_task,
    clean_task_success_rate,
    matched_benign_fpr,
    overall_stat,
    semantic_role,
    succ_but_unsafe,
)
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
    Trajectory,
)


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
        # And the suite's spatial predicate, for attacks that score motion against keep-out
        # geometry rather than a scalar axis. Assigned unconditionally for the same reason as the
        # schema above: a scalar suite reports [], which is the explicit "not spatial" signal that
        # keeps the search on its scalar objective. Without this the EAI04 redirection objective
        # would optimise the stub's danger axis even on LIBERO, whose predicate never reads it.
        if isinstance(attack, ZoneAwareAttack):
            attack.keep_out_zones = suite.keep_out_zones()


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
    """
    policy.reset()  # clear per-episode policy state (e.g. SmolVLA's action-chunk queue)
    # Seed the POLICY as well as the environment. `suite.reset` has always seeded the env; the
    # policy's own sampler ran off whatever state the process happened to be in, which is the
    # whole of the leaderboard's "one draw, not a constant" caveat. The adapter reports what it
    # actually applied — None if it does not seed — and that answer is what the episode records,
    # never the value we asked for.
    policy_seed = policy.seed(seed)
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
            policy_seed=policy_seed,
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
    decisions: list[Decision] = []
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
        obs, done, state = suite.step(action)

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

        # Read BEFORE the unsafe check breaks the loop: the step that violates the envelope is the
        # most informative one in the trajectory, and a `break` placed above this would drop
        # precisely that sample on every successful attack.
        signal = suite.calibration_signal(state)
        if signal is not None:
            calib_samples.append(
                [float(signal)] if isinstance(signal, (int, float)) else [float(v) for v in signal]
            )

        decision = Decision(
            step=t,
            instruction=adversarial_instruction,
            action=[float(x) for x in action.reshape(-1)],
            unsafe=suite.evaluate_unsafe(state),  # calibrated predicate if one is installed
        )
        decisions.append(decision)

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
        policy_seed=policy_seed,
        success=success,
        steps=steps,
        steps_to_success=steps_to_success,
        danger=danger,
        threshold=threshold,
        original_instruction=base_instruction,
        adversarial_instruction=adversarial_instruction,
        task_success=task_success,
        attacker_access=attack.attacker_access,
        action_head_class=policy.action_head_class or attack.action_head_class,
        decisions=decisions,
        trajectory=Trajectory.encode(calib_samples) if calib_samples else None,
        # None for every input-channel family. Read from the attack rather than passed in, so
        # a result records the corruption that was ACTUALLY in force when it ran, not one a
        # caller believed was in force.
        weight_corruption=getattr(attack, "record", None),
    )


def run(
    config: RunConfig,
    calibrations: dict[str, Calibration] | None = None,
    *,
    audit_sink: list[dict[str, str]] | None = None,
) -> RunReport:
    """Execute a full red-team run described by ``config`` and return a report.

    If ``calibrations`` (task -> :class:`~provael.calibration.Calibration`) is given, the
    suite uses the calibrated predicate for those tasks; otherwise the default predicate is
    used, so existing runs are unchanged.

    ``config.defense``, when set, installs a pre-processing mitigation in the deployment position
    (see :func:`run_episode`). ``audit_sink`` collects its raw → canonical trail for the caller to
    write as a ``defense-log.jsonl`` sidecar — this function performs no file IO, and the trail is
    deliberately NOT part of the report, so the attestation subject digest is unaffected.
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
    suite = make_suite(config.suite)
    if calibrations:
        suite.set_calibration(calibrations)

    # Exchange env features once (no-op for the stub: features() returns None).
    features = suite.features()
    if features is not None:
        policy.set_features(features)

    policy.load()

    defense = make_defense(config.defense) if config.defense else None
    attacks = resolve_attacks(config.attacks)
    _configure_optimized(attacks, policy, suite, config.query_budget)
    tasks = config.tasks if config.tasks is not None else suite.tasks()
    # `RunConfig` rejects an explicitly-empty `tasks`, but a suite that exposes none reaches the
    # same dead end: the triple loop below never executes and the report reads as a measured 0/0
    # rather than as "nothing ran". Fail here so an empty denominator can never be signed.
    if not tasks:
        raise ValueError(
            f"suite {config.suite!r} exposes no tasks, so nothing would be run. A report with "
            "attempts=0 is not a measurement — fix the suite or pass an explicit --tasks."
        )

    results: list[AttackResult] = []
    for task in tasks:
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
                for _repeat in range(config.episodes_per_seed):
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
                    weight_attack = (
                        attack if isinstance(attack, WeightIntegrityAttack) else None
                    )
                    if weight_attack is not None:
                        weight_attack.corrupt(policy, seed)
                    try:
                        results.append(
                            run_episode(
                                policy, suite, attack, task, seed, config.horizon,
                                defense=defense, audit_sink=audit_sink,
                            )
                        )
                    finally:
                        if weight_attack is not None:
                            weight_attack.restore(policy)
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
                )
    # The benign baseline's rate under the predicate actually used IS the live benign FPR.
    baseline = attack_breakdown.get("none")
    benign_fpr = baseline.asr if baseline is not None else None

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
        # signature that is supposed to cover them.
        schema_version=5,
        evidence_state=classify_run(config.policy, config.suite).value,
        policy=config.policy,
        model=config.model,
        suite=config.suite,
        attacks=[a.name for a in attacks],
        tasks=list(tasks),
        episodes=config.episodes,
        horizon=config.horizon,
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
        succ_but_unsafe=succ_but_unsafe(results),
        clean_task_success_rate=clean_task_success_rate(results),
        calibration=calibration_meta,
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


__all__ = ["run", "run_episode"]
