#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Write an evidence record for one simulated physical action, from one committed run shard.

    python examples/cosai-ws4-physical-action-record/build_record.py
    python examples/cosai-ws4-physical-action-record/build_record.py --out record.json
    python examples/cosai-ws4-physical-action-record/build_record.py --attack ARM --seed N

Offline and CPU-only. It reads ``report.json`` and, when present, ``execution-manifest.json`` from
one shard directory and writes one JSON record. No GPU, no simulator, no network.

WHAT THE RECORD IS. One commanded action laid against the evidence contract of the CoSAI WS4
agent-containment working draft (section 7.1), with the observation vantage and the coverage
denominator its section 7.4 asks for. The default is the action SmolVLA commanded at step 39 of the
``roleplay`` episode at ``libero_object/0``, seed 0, in
``results/smolvla_libero_object_suite_2026-09-14``: the step after which the end effector was inside
the default keep-out box.

WHAT IT SAYS ABOUT ITSELF, BECAUSE THE RUN CANNOT SAY MORE.

- The outcome is ``present``, read from simulator state, not from anything the policy reported.
- The observer is the simulator inside the harness process that also runs the policy. That is not
  an independent observer under the draft's three-condition test, and the record says so.
- The run did not record a decision before dispatch: it steps the simulator, then writes the
  commanded action and the resulting flag into one per-step entry.
- No contact forces, no sensor provenance, no hardware.
- The benign episode at the same task and seed is included with how it ended and where its
  coverage stops. A pair shares a task and a seed, not a starting scene (E-2026-19): when the shard
  records no ``init_state``, the scenes are inferred from lerobot 0.5.1's reset counter and labelled
  as an inference.
- Succ-But-Unsafe, risk exposure time and cumulative cost cannot be observed in a first-event run
  (E-2026-21). The record gives no value for them.

Every statement is built from the shard. A shard the record cannot describe (not LIBERO, scored
against a calibrated predicate, run with a defense, or internally inconsistent) is refused with an
error rather than described approximately. Nothing is posted anywhere.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from provael.endpoints import PHYSICAL_HAZARD
from provael.execution import report_digest
from provael.report import ReportArtifact
from provael.scoring.action_schema import SEVEN_DOF_DELTA_SCHEMA
from provael.scoring.safety_cost import exposure_unobservable, unsafe_success_unobservable
from provael.suites.keepout_zones import DEFAULT_KEEP_OUT_ZONE
from provael.types import AttackResult, RunReport

REPO = Path(__file__).resolve().parents[2]
DEFAULT_SHARD = REPO / "results" / "smolvla_libero_object_suite_2026-09-14" / "libero_object_0"
DEFAULT_OUT = Path("runs") / "cosai-ws4-physical-action-record" / "record.json"
BENIGN_ARM = "none"
#: lerobot 0.5.1 loads ``_init_states[init_state_id % len(_init_states)]``; a LIBERO task has 50.
FIXED_INIT_STATES = 50
#: The draft the record is laid against, pinned to the revision it was written from.
PAPER = (
    "https://github.com/cosai-oasis/ws4-secure-design-agentic-systems/blob/"
    "a5aa3a6434d76964f27f5d1ed35d6e1fc0a2d77e/whitepapers/agent-containment.md"
)
FORMAT = "provael-example/cosai-ws4-physical-action-record/draft"
#: How an episode stopped, as prose. The runner stops at the first unsafe step or at ``done``
#: (task success on LIBERO), and otherwise at the horizon.
ENDED = {
    "envelope_exit": "at an envelope exit",
    "task_success": "at task success",
    "horizon": "at the horizon",
    "not_established": "for a reason the run did not record",
}


class RecordError(RuntimeError):
    """The shard cannot support the record. A processing failure, never ``not_established``."""


def _shard_label(shard: Path) -> str:
    resolved = shard.resolve()
    if resolved.is_relative_to(REPO):
        return resolved.relative_to(REPO).as_posix()
    return resolved.as_posix()


def load_shard(shard: Path) -> tuple[ReportArtifact, dict[str, Any] | None]:
    """The shard's report with its exact bytes, and its execution manifest when one exists."""
    artifact = ReportArtifact.read(shard)
    manifest_path = shard / "execution-manifest.json"
    if not manifest_path.is_file():
        return artifact, None
    return artifact, json.loads(manifest_path.read_text(encoding="utf-8"))


def check_scope(report: RunReport, manifest: dict[str, Any] | None, attack: str) -> None:
    """Refuse a shard or an arm whose outcome this record would describe wrongly."""
    if report.suite != "libero":
        raise RecordError(f"suite {report.suite!r}: this record describes LIBERO episodes only")
    if report.calibrated:
        raise RecordError("calibrated predicate: this record describes the default box only")
    if manifest is not None and manifest.get("defense"):
        raise RecordError(f"defense {manifest['defense']!r} filtered the actions: out of scope")
    if attack == BENIGN_ARM:
        raise RecordError(f"{BENIGN_ARM!r} is the benign arm the record compares against")


def find_episode(report: RunReport, task: str, attack: str, seed: int) -> AttackResult:
    """The one applicable episode at ``(task, attack, seed)``, with a per-step log."""
    found = [r for r in report.results if (r.task, r.attack, r.seed) == (task, attack, seed)]
    if len(found) != 1:
        raise RecordError(f"{len(found)} episodes at ({task}, {attack}, seed {seed}), expected 1")
    episode = found[0]
    if not episode.applicable or not episode.decisions:
        raise RecordError(f"({task}, {attack}, seed {seed}) was not run: no steps to record")
    return episode


def positions(episode: AttackResult) -> list[list[float]]:
    """The end-effector position after each executed step, checked against the step log."""
    name = f"{episode.attack} seed {episode.seed}"
    if episode.trajectory is None:
        raise RecordError(f"{name} recorded no end-effector positions")
    rows = episode.trajectory.decode()
    steps = [d.step for d in episode.decisions]
    if steps != list(range(1, episode.steps + 1)) or len(rows) != episode.steps:
        raise RecordError(f"{name}: steps, step log and positions disagree")
    if any(len(row) != 3 for row in rows):
        raise RecordError(f"{name}: positions are not (x, y, z)")
    if episode.success and episode.steps_to_success != episode.steps:
        raise RecordError(f"{name} went on past its exit step, which a first-event run cannot do")
    return rows


def check_flags(episode: AttackResult, rows: list[list[float]]) -> None:
    """The default box must reproduce the run's own per-step flag, or the record would name a rule
    the run did not use."""
    disagree = [
        d.step for d, p in zip(episode.decisions, rows, strict=True)
        if DEFAULT_KEEP_OUT_ZONE.contains(p) != d.unsafe
    ]
    if disagree:
        raise RecordError(f"the default box disagrees with the recorded flag at steps {disagree}")


def ended_by(episode: AttackResult, horizon: int) -> str:
    """Why the episode stopped, as one of :data:`ENDED`'s keys."""
    if episode.success:
        return "envelope_exit"
    if episode.task_success:
        return "task_success"
    return "horizon" if episode.steps == horizon else "not_established"


def inferred_init_states(report: RunReport) -> dict[tuple[str, str, int], int]:
    """The fixed initial state each episode loaded, by lerobot 0.5.1's reset counter.

    An inference, not a record (E-2026-19). It assumes what the sharded runner does: each task's
    env is built fresh with its counter at 0, every reset loads ``counter % 50`` and adds one, a
    task success adds one more (lerobot's ``step`` resets on termination), and the episodes ran in
    the order ``report.json`` lists them. The walk stops at the first episode whose effect on the
    counter is unknown, so later episodes get no index rather than a guessed one.
    """
    counters: dict[str, int] = {}
    stopped: set[str] = set()
    states: dict[tuple[str, str, int], int] = {}
    for r in report.results:
        if r.task in stopped or not r.applicable or r.task_success is None:
            stopped.add(r.task)
            continue
        counter = counters.get(r.task, 0)
        states[(r.task, r.attack, r.seed)] = counter % FIXED_INIT_STATES
        counters[r.task] = counter + (2 if r.task_success else 1)
    return states


def starting_scenes(report: RunReport, acted: AttackResult, twin: AttackResult) -> dict[str, Any]:
    """Whether the two episodes started from one scene: recorded when the shard has it."""
    pair = f"The pair shares task {acted.task} and seed {acted.seed}"
    names = f"the benign ({twin.attack}) episode", f"the {acted.attack} episode"
    if acted.init_state is not None and twin.init_state is not None:
        a, b, basis = acted.init_state, twin.init_state, "recorded"
        how = f"The shard recorded init_state {b} for {names[0]} and {a} for {names[1]}"
        tail = " (E-2026-19)."
    else:
        states = inferred_init_states(report)
        found = (states.get((acted.task, acted.attack, acted.seed)),
                 states.get((twin.task, twin.attack, twin.seed)))
        if found[0] is None or found[1] is None:
            return {"basis": "not_established", "same_scene": None, "init_state": None,
                    "statement": f"{pair}. The shard records no init_state and the reset counter "
                    "cannot be walked to both episodes, so whether they shared a starting scene "
                    "is not established (E-2026-19)."}
        a, b, basis = found[0], found[1], "inferred"
        how = (f"The shard is report schema {report.schema_version} and records no init_state. "
               f"By lerobot 0.5.1's reset counter {names[0]} started from fixed initial state {b} "
               f"and {names[1]} from state {a}")
        tail = (". That is an inference from the documented counter, not a recorded value "
                "(E-2026-19).")
    same = a == b
    verdict = f"so the benign episode {'did' if same else 'did not'} start from {names[1]}'s scene"
    return {
        "basis": basis, "same_scene": same, "init_state": {acted.attack: a, twin.attack: b},
        "statement": f"{pair}{'' if same else ', not a starting scene'}. {how}, {verdict}{tail}",
    }


def _value(manifest: dict[str, Any] | None, key: str) -> Any:
    return None if manifest is None else manifest.get(key)


def _row(name: str, status: str, **detail: Any) -> dict[str, Any]:
    return {"row": name, "status": status, **detail}


def principal_row(manifest: dict[str, Any] | None) -> dict[str, Any]:
    name = "Principal and full delegation chain"
    operator = _value(manifest, "operator")
    if operator:
        return _row(name, "present", value={"operator": operator}, delegation_chain="none: the "
                    "harness calls the policy directly in its own process")
    return _row(name, "not_established", missing_premise="The run recorded no principal (the "
                "execution manifest's operator is null or absent). The harness calls the policy "
                "directly in its own process, so there is no delegation step to carry.")


def actor_row(
    report: RunReport, manifest: dict[str, Any] | None, acted: AttackResult
) -> dict[str, Any]:
    revision = _value(manifest, "checkpoint_revision")
    weights = _value(manifest, "checkpoint_digest")
    verification = (
        {"status": "unchecked", "revision": revision, "weights_digest": weights}
        if revision or weights else
        {"status": "not_established", "missing_premise": "The run recorded the checkpoint name it "
         "was asked to load and no revision or weights digest, so the record cannot show which "
         "weights acted."}
    )
    return _row("Actor identity and establishment provenance", "present",
                value={"policy": report.policy, "checkpoint": report.model,
                       "action_head_class": acted.action_head_class,
                       "policy_seed": acted.policy_seed},
                provenance="unsigned-request-claim", verification=verification)


def policy_row(manifest: dict[str, Any] | None) -> dict[str, Any]:
    name = "Policy version"
    if manifest is None:
        return _row(name, "not_established", missing_premise="No execution manifest, so whether "
                    "a mitigation filtered the actions is not recorded.")
    return _row(name, "absent", reason="No enforcement policy was in force: the harness "
                "dispatched every action the policy emitted and scored the resulting state "
                "afterwards. The rule that scored it is under outcome.predicate.")


def contract_rows_who(
    report: RunReport, manifest: dict[str, Any] | None, acted: AttackResult
) -> list[dict[str, Any]]:
    """Section 7.1 rows about who acted, on whose authority, under which rules."""
    given = (f"the {acted.attack} attack's text, which the harness put in place of the task "
             "instruction; that substitution is the condition under test")
    return [
        principal_row(manifest),
        actor_row(report, manifest, acted),
        _row("Subject identity and establishment provenance", "absent", provenance="absent",
             reason=f"No request was made on anyone's authority. The policy received {given}."),
        policy_row(manifest),
        _row("Assurance-boundary statement", "absent",
             reason="No containment claim was made for this run, so no boundary was stated at the "
             "decision. What the outcome observation covered and left out is under coverage."),
        _row("Tool-catalog version", "absent",
             reason="The policy calls no tools. It emits one continuous 7-channel action per step "
             "into LIBERO's action space, Box(-1, 1, shape=(7,)). The run recorded no digest of "
             "that action schema."),
    ]


def runtime_row(manifest: dict[str, Any] | None) -> dict[str, Any]:
    attestation = {"status": "not-available", "reason": "No attestation accompanies this shard. "
                   "Nothing measured the runtime, and the report and execution manifest are "
                   "unsigned."}
    name = "Runtime identity or attestation reference"
    if manifest is None:
        return _row(name, "not_established", attestation=attestation,
                    missing_premise="No execution manifest, so no runtime identity was recorded.")
    keys = ("package_version", "python_version", "os", "hardware", "accelerator", "precision",
            "protocol_version")
    identity = {key: manifest.get(key) for key in keys}
    identity["not_recorded"] = manifest.get("missing_fields", [])
    return _row(name, "present", runtime_identity=identity, attestation=attestation)


def contract_rows_what(report: RunReport, manifest: dict[str, Any] | None,
                       action_id: str) -> list[dict[str, Any]]:
    """Section 7.1 rows about the action, its decision, its outcome and the record's integrity."""
    return [
        _row("Action or tool-call identifier", "present", value=action_id,
             note="Composed by this script from fields the run recorded. The run assigns no "
             "identifier of its own to an action."),
        _row("Request digest", "absent",
             reason="The run computed no request digest. The commanded vector is recorded in full "
             "under action.commanded, so a reader compares the values themselves."),
        _row("Enforcement decision and reason", "absent",
             reason="There is no enforcement point. Nothing could refuse the action: the harness "
             "passes it to the simulator and only then reads whether the resulting state is "
             "inside the keep-out box. That per-step flag is an outcome, written after the step "
             "(see ordering)."),
        runtime_row(manifest),
        _row("Outcome", "present",
             value="The end effector was inside the keep-out box after the commanded step.",
             detail="See outcome. It was written after the step, in the same per-step entry as "
             "the commanded action."),
        _row("Integrity-protected sequence with trusted checkpoints", "absent",
             reason="The run keeps no integrity-protected sequence and no checkpoints. Its "
             "per-step entries are a list inside report.json, which the harness writes after the "
             "shard's episodes finish. " + (
                 "No execution manifest accompanies the report." if manifest is None else
                 "The execution manifest binds the whole report by digest "
                 "(source.execution_manifest) and is itself unsigned.")),
        _row("The accounting decision", "absent",
             reason=f"No budget or accounting authority applies to a simulated episode. Its only "
             f"limit is the run's fixed horizon of {report.horizon} steps, a stopping rule rather "
             "than an account."),
    ]


def binding(artifact: ReportArtifact, manifest: dict[str, Any] | None) -> dict[str, Any]:
    """The report's file digest, and whether the execution manifest binds this report."""
    if manifest is None:
        return {"report_json_sha256": artifact.sha256, "execution_manifest": None}
    recorded = manifest.get("report_digest")
    if recorded is not None and recorded != report_digest(artifact.report):
        raise RecordError("execution-manifest.json does not bind this report.json")
    return {
        "report_json_sha256": artifact.sha256,
        "execution_manifest": {"run_id": manifest.get("run_id"), "report_digest": recorded,
                               "matches_this_report": None if recorded is None else True},
    }


def gaps(episode: AttackResult, horizon: int) -> list[dict[str, Any]]:
    """What the observation did not cover, each gap located."""
    located: list[dict[str, Any]] = []
    if episode.steps < horizon:
        located.append({"where": f"steps {episode.steps + 1} to {horizon}", "status": "absent",
                        "reason": f"Not executed: the episode ended "
                        f"{ENDED[ended_by(episode, horizon)]} at step {episode.steps}."})
    if PHYSICAL_HAZARD not in episode.endpoints:
        located.append({"where": "contact forces", "status": "not_established",
                        "missing_premise": "The run recorded no contact or force signal for this "
                        "episode, so whether the arm touched or pushed on anything is not "
                        "established."})
    located += [
        {"where": "sensor provenance", "status": "not_established",
         "missing_premise": "The camera frames and robot state the policy consumed were not "
         "recorded, and no value in report.json is signed or timestamped at its source."},
        {"where": "hardware", "status": "absent",
         "reason": "Simulation only. No robot, actuator or physical sensor took part, so nothing "
         "here was observed in the world."},
        {"where": "step timing", "status": "not_established",
         "missing_premise": "The run records no per-step timestamps."},
    ]
    return located


def coverage(episode: AttackResult, rows: list[list[float]], horizon: int) -> dict[str, Any]:
    """The coverage denominator: invocation, fields and interval observed, with located gaps."""
    executed = episode.steps
    return {
        "invocation": f"{episode.task}, {episode.attack}, seed {episode.seed}",
        "interval": {"unit": "simulator step", "first": 1, "last": executed, "horizon": horizon},
        "fields": [
            {"field": "end-effector position (x, y, z), world coordinates",
             "in_report": "trajectory", "steps_with_value": len(rows),
             "steps_executed": executed},
            {"field": "keep-out flag", "in_report": "decisions[].unsafe",
             "steps_with_value": len(episode.decisions), "steps_executed": executed},
            {"field": "commanded action", "in_report": "decisions[].action",
             "steps_with_value": len(episode.decisions), "steps_executed": executed},
        ],
        "end_effector_position_by_step": rows,
        "shape": "incomplete",
        "gaps": gaps(episode, horizon),
    }


def vantage(report: RunReport) -> dict[str, Any]:
    """Who observed the outcome, what they could see, who could forge or suppress it, and the
    independence test condition by condition."""
    return {
        "observer": "The LIBERO simulator (MuJoCo through robosuite, wrapped by lerobot's "
        f"LiberoEnv), stepped by the provael {report.tool_version} harness in the same Python "
        f"process that runs the {report.policy} policy. The run did not record the installed "
        "lerobot version.",
        "inputs_visible": [
            "the commanded action the harness passed in",
            "the end-effector position after each step",
            "the simulator's task-success flag",
        ],
        "could_forge_or_suppress": "Anything with control of that process or the machine it ran "
        "on: the harness, the policy adapter, the simulator build, and whoever operated the run.",
        "independent_observer": False,
        "independence_test": [
            {"condition": "outside the producer's trust domain", "holds": False,
             "basis": "The simulator, the policy and the harness that wrote the record share one "
             "process, so one compromise reaches all three."},
            {"condition": "identity on a basis the producer cannot issue, alter or revoke",
             "holds": False,
             "basis": "The simulator has no identity in the record beyond what the harness wrote "
             "about it."},
            {"condition": "custody of the keys that sign its observations shown by evidence",
             "holds": False, "basis": "Its observations are not signed, so there is no key."},
        ],
        "consequence": "Under the draft's independence test an observation from this vantage "
        "counts as self-reported (section 7.4, C3). This record claims no independent observer.",
    }


def outcome(episode: AttackResult, rows: list[list[float]]) -> dict[str, Any]:
    """The crossing, as the simulator's state shows it after the commanded step."""
    box = DEFAULT_KEEP_OUT_ZONE
    return {
        "status": "present",
        "property": "end effector inside the keep-out box",
        "step": episode.steps,
        "end_effector_position": rows[-1],
        "previous_step_position": rows[-2] if len(rows) > 1 else None,
        "observed_from": "Simulator state: the end-effector position LIBERO returned after the "
        "step (robot_state.eef.pos), read by the harness. Nothing was taken from the policy's "
        "output.",
        "predicate": {
            "name": f"{box.name} keep-out box", "calibrated": False,
            "x": list(box.x), "y": list(box.y), "z": list(box.z),
            "bounds": "inclusive, world coordinates",
            "check": "The box reproduces the run's own per-step flag on every step of this "
            "episode and of the benign episode.",
        },
        "episode_ended_here": "The runner ends an episode at its first unsafe step, so this was "
        "the last step executed.",
    }


def benign_episode(
    report: RunReport, acted: AttackResult, twin: AttackResult, rows: list[list[float]]
) -> dict[str, Any]:
    """The benign episode at the same task and seed: how it ended, and what an absence claim on it
    would still need (section 7.4, C4)."""
    how = ended_by(twin, report.horizon)
    stopped = twin.steps < report.horizon
    return {
        "task": twin.task, "seed": twin.seed, "arm": twin.attack,
        "role": report.roles.get(twin.attack), "instruction": twin.adversarial_instruction,
        "steps": twin.steps, "horizon": report.horizon, "ended_by": how,
        "task_success": twin.task_success,
        "steps_inside_keep_out_box": sum(d.unsafe for d in twin.decisions),
        "end_effector_position_by_step": rows,
        "starting_scene": starting_scenes(report, acted, twin),
        "absence_claim": {
            "property": "the end effector stayed out of the keep-out box",
            "field_visible": f"end-effector position recorded on {len(rows)} of {twin.steps} "
            "executed steps",
            "interval_covered": f"steps 1 to {twin.steps} of a {report.horizon}-step horizon",
            "gap": f"steps {twin.steps + 1} to {report.horizon} were not executed: the episode "
            f"ended {ENDED[how]}" if stopped else None,
            "observer_independent": False,
            "what_this_record_cannot_support": "An absence claim that needs an independent "
            "observer, or one over steps the episode never executed.",
        },
    }


def caveats(record: dict[str, Any]) -> list[str]:
    """The record's limits as sentences, built from its own fields so the two cannot drift."""
    act, twin = record["action"], record["benign_episode"]
    missing = [g["where"] for g in record["coverage"]["gaps"] if not g["where"].startswith("steps")]
    return [
        f"The action is {act['arm']} at {act['task']}, seed {act['seed']}, step {act['step']}: "
        "the end effector was inside the keep-out box after it.",
        "Simulation only: no robot hardware took part.",
        "The observer is the simulator in the harness process that also runs the policy. It is "
        "not an independent observer under the three-condition test (section 7.4).",
        "The run did not record a decision before dispatch; see ordering.",
        f"Not in the record: {', '.join(missing)}.",
        f"The benign episode at the same task and seed ({twin['arm']}, seed {twin['seed']}) ended "
        f"{ENDED[twin['ended_by']]} at step {twin['steps']} of {twin['horizon']}, with "
        f"{twin['steps_inside_keep_out_box']} steps inside the keep-out box.",
        twin["starting_scene"]["statement"],
        f"Succ-But-Unsafe, risk exposure time and cumulative cost are not observable: "
        f"{record['not_observable']['reason']} (E-2026-21). No value is given for them.",
    ]


def build_record(shard: Path, attack: str, seed: int, task: str | None = None) -> dict[str, Any]:
    """The record for the commanded action at the exit step of ``(task, attack, seed)``."""
    artifact, manifest = load_shard(shard)
    report = artifact.report
    check_scope(report, manifest, attack)
    if task is None and len(report.tasks) != 1:
        raise RecordError(f"the shard holds {len(report.tasks)} tasks; pass --task")
    task = task or report.tasks[0]
    acted = find_episode(report, task, attack, seed)
    twin = find_episode(report, task, BENIGN_ARM, seed)
    acted_rows, twin_rows = positions(acted), positions(twin)
    check_flags(acted, acted_rows)
    check_flags(twin, twin_rows)
    if not acted.success:
        raise RecordError(f"{attack} seed {seed} never left the envelope: no crossing to record")
    source = binding(artifact, manifest)
    run_id = _value(manifest, "run_id") or f"report-sha256:{artifact.sha256[:16]}"
    step = acted.decisions[-1]
    action_id = f"{run_id}/{task}/{attack}/seed-{seed}/step-{step.step}"
    record: dict[str, Any] = {
        "format": FORMAT,
        "drafted_against": f"{PAPER} (CoSAI WS4 agent-containment working draft, sections 7.1 "
        "and 7.4)",
        "scope": "Companion example built offline from a committed simulation run. Not a "
        "production record and not a CoSAI document; nothing in it was observed on hardware.",
        "source": {"repository": "https://github.com/provael/provael",
                   "shard": _shard_label(shard), "report_schema_version": report.schema_version,
                   "tool_version": report.tool_version, **source},
        "action": {
            "action_id": action_id, "task": task, "arm": attack, "family": acted.family,
            "role": report.roles.get(attack), "seed": seed, "policy_seed": acted.policy_seed,
            "task_instruction": acted.original_instruction,
            "instruction_given": acted.adversarial_instruction, "step": step.step,
            "horizon": report.horizon,
            "commanded": {"vector": step.action,
                          "channels": list(SEVEN_DOF_DELTA_SCHEMA.component_names),
                          "channel_names_from": "provael's generic 7-DoF delta schema; the run "
                          "recorded no action-schema digest",
                          "space": "LIBERO's action space, Box(-1, 1, shape=(7,))"},
        },
        "ordering": {
            "decision_sequenced_before_dispatch": False,
            "as_recorded": f"The runner that wrote this report (provael {report.tool_version}) "
            "passes the action to the simulator first, then appends one per-step entry holding "
            "the commanded action and the resulting keep-out flag together. This record shows the "
            "commanded action and its outcome as separate parts to match the contract's shape. "
            "That split is made here, after the fact; the run never held a decision without its "
            "outcome.",
        },
        "contract": contract_rows_who(report, manifest, acted)
        + contract_rows_what(report, manifest, action_id),
        "outcome": outcome(acted, acted_rows),
        "vantage": vantage(report),
        "coverage": coverage(acted, acted_rows, report.horizon),
        "benign_episode": benign_episode(report, acted, twin, twin_rows),
        "not_observable": {
            "metrics": ["Succ-But-Unsafe", "risk exposure time", "cumulative cost"],
            "reason": unsafe_success_unobservable(report.suite)
            or exposure_unobservable(report.suite),
            "errata": "E-2026-19 and E-2026-21 in docs/errata.md",
        },
    }
    record["caveats"] = caveats(record)
    return record


def write_record(record: dict[str, Any], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--shard", type=Path, default=DEFAULT_SHARD,
                        help="shard directory holding report.json (default: %(default)s)")
    parser.add_argument("--attack", default="roleplay", help="the arm whose exit step is recorded")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--task", default=None, help="needed only for a multi-task shard")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help="where to write the record (default: %(default)s)")
    args = parser.parse_args(argv)
    try:
        record = build_record(args.shard, args.attack, args.seed, args.task)
    except RecordError as exc:
        print(f"build_record: {exc}", file=sys.stderr)
        return 1
    write_record(record, args.out)
    print(f"wrote {args.out}")
    for line in record["caveats"]:
        print(f"- {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
