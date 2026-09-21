# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Core data types for the provael engine.

Observations and environment state flow through the pipeline as plain ``dict``
objects (see the ABC signatures in :mod:`provael.policies.base`,
:mod:`provael.suites.base`, and :mod:`provael.attacks.base`). The aliases
below name those dicts; the pydantic models capture the *results* of a run, which
are serialised to ``report.json``.

Determinism contract: none of these models embed wall-clock time, absolute
timestamps, or process-varying values. A :class:`RunReport` is a pure function of
``(RunConfig, registered policy/suite/attacks)`` so that the same seed always
produces a byte-identical report.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, Field

# A policy observation (what a suite hands to a policy) and an environment state
# snapshot (what ``SuiteAdapter.step`` returns as its info dict) are both plain
# string-keyed dicts. They are kept as aliases — not models — so adapters around
# real simulators (e.g. LIBERO) can pass their native dicts through untouched.
type Observation = dict[str, Any]
type State = dict[str, Any]

# An action vector emitted by a policy / consumed by a suite.
type Action = npt.NDArray[np.float32]

#: Canonical top-level observation key carrying the primary camera image (the target of
#: image-space attacks). Suites that expose a real image populate this key.
IMAGE_KEY = "image"


@dataclass(frozen=True)
class SuiteFeatures:
    """Environment metadata a real policy adapter needs to consume a suite's obs.

    Exchanged once per run via ``SuiteAdapter.features()`` -> ``PolicyAdapter.set_features``.
    The ``stub`` suite returns ``None`` (no exchange); the ``libero`` suite returns this
    with ``env_config`` set to the real (opaque) LeRobot env config so the SmolVLA adapter
    can build the verified env pre/post processors.
    """

    action_dim: int
    fps: int = 30
    camera_keys: tuple[str, ...] = ()
    image_key: str | None = None  # top-level obs key carrying the primary camera image
    task_suite: str | None = None
    env_config: Any = None  # opaque LeRobot env config (None outside the gated path)


class Decision(BaseModel):
    """One policy decision at a single timestep within an episode."""

    step: int = Field(..., description="1-based timestep index within the episode.")
    instruction: str = Field(
        ..., description="The (possibly adversarial) instruction given to the policy."
    )
    action: list[float] = Field(
        ..., description="The action vector the policy emitted, as a list of floats."
    )
    unsafe: bool = Field(..., description="Whether the resulting environment state was unsafe.")


class Trajectory(BaseModel):
    """The per-step calibration signal of one episode, stored compactly.

    WHY THIS EXISTS AT ALL. Calibrating a keep-out zone needs the BENIGN end-effector envelope —
    where the policy actually goes when nobody is attacking it — and that is the one input the
    runner computed on every step and then threw away. :meth:`Suite.calibration_signal` has always
    returned exactly this signal, and nothing ever persisted it, so every finished run left the
    calibration no more possible than before it started. That is why issue #136 is *unfixable*
    rather than merely unfixed: the blocker is not GPU budget for the fit, it is that the data the
    fit consumes was never written down.

    WHY NOT JUST REUSE ``decisions``. ``Decision`` is a per-step JSON object and the ten-task suite
    already sheds 1.9 MB per task of it before anything is committed. A second per-step JSON field
    would be the same mistake twice. This is a homogeneous numeric array, so it is stored as one
    base64 blob of zlib-compressed float32 — a few hundred poses collapse to a few hundred bytes,
    and the shape is carried explicitly so a reader never has to infer the stride.

    DETERMINISM. zlib at a fixed level over identical float32 bytes is byte-stable, so a report
    carrying trajectories stays a pure function of its inputs and the attestation subject is
    unchanged in kind.
    """

    encoding: Literal["float32-zlib-b64"] = Field(
        "float32-zlib-b64", description="Wire format of `data`. One value today, named so a future "
        "format is a new value rather than a silent reinterpretation of these bytes."
    )
    shape: tuple[int, int] = Field(
        ..., description="(steps, dims). dims is 3 for a spatial suite (x, y, z) and 1 for a "
        "scalar-danger suite, so a reader can tell the two apart without guessing."
    )
    data: str = Field(..., description="base64(zlib(float32 little-endian, C-order)).")

    @classmethod
    def encode(cls, samples: Sequence[Sequence[float]]) -> Trajectory:
        """Pack per-step samples. Every row must share a width; a ragged trajectory is a bug."""
        import base64
        import zlib

        import numpy as np

        widths = {len(row) for row in samples}
        if len(widths) > 1:
            raise ValueError(
                f"trajectory must be 2-D (steps, dims); rows have differing widths {sorted(widths)}"
            )
        arr = np.asarray(samples, dtype="<f4")
        if arr.ndim != 2:
            raise ValueError(f"trajectory must be 2-D (steps, dims); got shape {arr.shape}")
        blob = zlib.compress(arr.tobytes(order="C"), 6)
        return cls(
            shape=(int(arr.shape[0]), int(arr.shape[1])),
            data=base64.b64encode(blob).decode(),
        )

    def decode(self) -> list[list[float]]:
        """Unpack back to plain floats. Raises if the payload disagrees with the declared shape."""
        import base64
        import zlib

        import numpy as np

        raw = zlib.decompress(base64.b64decode(self.data))
        arr = np.frombuffer(raw, dtype="<f4")
        want = self.shape[0] * self.shape[1]
        if arr.size != want:
            raise ValueError(f"trajectory payload has {arr.size} values, shape declares {want}")
        return [[float(v) for v in row] for row in arr.reshape(self.shape)]


class BitFlipRecord(BaseModel):
    """What a weight-integrity attack actually did to the loaded parameters.

    Recorded on every :class:`AttackResult` the corruption was live for, so a result carries its
    own corruption parameters rather than deferring them to a config file the report does not
    contain. The three fields that matter to a reader are :attr:`flips` (the budget K),
    :attr:`selection` (how the bits were chosen — the whole point of the family is the gap between
    ``"gradient"`` and ``"random"`` at the SAME K), and :attr:`bit_indices` (exactly which bits,
    so the corruption is replayable without re-running the selection).

    SCOPE, STATED HERE BECAUSE THIS IS WHERE A READER MEETS IT. These are *logical* flips applied
    to weights already loaded in memory. Nothing here models how an attacker would achieve that on
    a real deployment — that is a platform question about DRAM fault injection, ECC and supply
    chain, and this project does not measure it. A high rate here means the policy is fragile to
    corruption, NOT that the corruption is deliverable.
    """

    flips: int = Field(..., ge=0, description="K — the number of bits actually flipped.")
    selection: str = Field(
        ...,
        description="How the K bits were chosen: 'gradient' (ranked by the loss gradient) or "
        "'random' (the equal-count control arm). A gradient result with no random arm at the same "
        "K is not a result — it cannot separate selection from damage-in-general.",
    )
    seed: int = Field(..., description="Seed for the random arm's choice; 0 for the gradient arm.")
    parameter_count: int = Field(..., ge=0, description="Number of quantized parameters exposed.")
    bit_width: int = Field(..., ge=1, description="Bits per parameter (8 for INT8).")
    bit_indices: list[int] = Field(
        default_factory=list,
        description="The flipped bit positions, as flat indices into parameter_count*bit_width, "
        "ascending. Replayable: applying these to the clean parameters reproduces the run.",
    )
    emulated: Literal[True] = Field(
        True,
        description="Always True, and typed so it CANNOT be anything else. Provael flips bits in "
        "loaded weights in memory and has no hardware fault-injection path; the field exists so a "
        "report states that rather than leaving a reader to assume either way.",
    )
    """Structurally True, not True-by-default — and the difference is the safety boundary.

    This was ``bool = Field(True, ...)`` with a docstring that said "Always True". Nothing enforced
    it: ``BitFlipRecord(..., emulated=False)`` constructed happily and serialised
    ``"emulated": false``. A record asserting a NON-emulated bit flip is a record asserting this
    tool performed hardware fault injection, which is out of scope under SAFETY.md and which this
    project does not do. The claim that keeps the family inside that boundary must not rest on a
    default a caller can override.

    ``Literal[True]`` makes pydantic reject ``False`` at construction and mypy reject it statically.
    The serialised value is unchanged (``true``), so canonical JSON, report digests and existing
    attestations are byte-identical — this hardens the type without touching the signature surface.
    """


class AttackResult(BaseModel):
    """Outcome of a single episode: one ``(task, attack, seed)`` triple."""

    task: str
    attack: str
    family: str
    seed: int
    success: bool = Field(..., description="True if the policy was driven into an unsafe state.")
    steps: int = Field(..., description="Number of timesteps actually executed.")
    steps_to_success: int | None = Field(
        None, description="1-based step at which the unsafe state first occurred, or None."
    )
    danger: float = Field(..., description="Final value of the env's danger signal.")
    threshold: float = Field(
        ..., description="Per-seed unsafe threshold the danger signal was compared against."
    )
    original_instruction: str
    adversarial_instruction: str
    applicable: bool = Field(
        True, description="False if the attack is N/A for this suite (excluded from ASR)."
    )
    task_success: bool | None = Field(
        None,
        description="C2 (Succ-But-Unsafe): did the policy also COMPLETE the benign task this "
        "episode? Independent of `success` (the safety violation). None where the suite surfaces "
        "no task-success signal — the stub surfaces a deterministic one (benign reach reached), "
        "the real signal is GPU-gated (LIBERO surfaces its native flag).",
    )
    endpoints: dict[str, bool | None] = Field(
        default_factory=dict,
        description="Independent semantic-endpoint outcomes (see provael.endpoints): a suite may "
        "populate 'unauthorized_action' / 'physical_hazard' / etc. here. `success` is the "
        "'unsafe_envelope' endpoint and 'authorized_task_success' derives from task_success; the "
        "rest are N/A (absent) where the suite surfaces no signal — never a fabricated False.",
    )
    attacker_access: str | None = Field(
        None,
        description="INV-4 threat model: 'white-box-gradient' | 'black-box-query' | "
        "'in-scene-physical', or None where not asserted.",
    )
    action_head_class: str | None = Field(
        None,
        description="INV-4 threat model: policy action-head class the attack ran against — "
        "'token' | 'flow', or None where not asserted.",
    )
    decisions: list[Decision] = Field(
        default_factory=list,
        description="Per-episode log: one Decision per executed timestep (P0.4). Deterministic on "
        "the stub; bound by the report.json SHA-256 the attestation subject records.",
    )
    trajectory: Trajectory | None = Field(
        None,
        description="Per-step calibration signal for this episode (end-effector pose on a spatial "
        "suite). Recorded for EVERY episode, benign and adversarial alike, and on by default: an "
        "opt-in flag reproduces the pre-0.35.0 situation the first time someone forgets. None only "
        "where the suite surfaced no signal on any step — never where it surfaced one and it was "
        "dropped. See issue #136.",
    )
    weight_corruption: BitFlipRecord | None = Field(
        None,
        description="The weight corruption in force for this episode, or None for every attack "
        "that does not touch parameters (which is all fourteen input-channel families). Present "
        "from schema_version 4.",
    )
    policy_seed: int | None = Field(
        None,
        description="The seed the POLICY's own sampler was set to for this episode, as reported "
        "by the adapter — not as requested by the runner. None means the adapter does not seed "
        "itself, so this episode is one draw and not reproducible run-to-run.\n\nDistinct from "
        "`seed`, which has always been the ENVIRONMENT seed. Recording only the environment seed "
        "is what let two rows at the same commit be non-comparable while both looked fully "
        "specified. Present from schema_version 5.",
    )


class ASRStat(BaseModel):
    """Attack-success-rate statistics for a slice of results."""

    attempts: int = Field(..., description="Number of episodes in this slice.")
    successes: int = Field(..., description="Number of episodes that reached an unsafe state.")
    asr: float = Field(..., description="successes / attempts, or 0.0 when attempts == 0.")

    @property
    def measured_rate(self) -> float | None:
        """The rate as a measured proportion, or None when there were no attempts.

        An empty slice is an N/A, not a measured 0%: the stored ``asr`` is 0.0 there only as a
        serialization sentinel. Read this (not ``asr``) whenever a 0-attempt group must show N/A.
        """
        return self.asr if self.attempts > 0 else None


class EaiTag(BaseModel):
    """Embodied AI Security Top-10 risk an attack maps to (see :mod:`provael.eai`)."""

    id: str = Field(..., description="Risk id, e.g. 'EAI01'.")
    name: str = Field(..., description="Human-readable risk name.")


#: Honest transfer-status labels every family's transfer-test carries (the leaderboard / report
#: wording). Read alongside the attestation pair below — they are deliberately distinct strings.
REAL_TRANSFER = "real-transfer"
STUB_SCAFFOLDING = "stub-scaffolding"

#: Attestation / compliance transfer-status vocabulary — the signed, auditor-facing pair. The
#: attestation statement (:mod:`provael.attest`) and the transfer-aware compliance tier
#: (:mod:`provael.compliance`) share THESE constants so an auditor reads one consistent label and
#: cannot misread stub scaffolding as conformity-relevant evidence (INV-3: extend, never bypass).
MEASURED_REAL_TRANSFER = "measured-real-transfer"
STUB_VALIDATED_SCAFFOLDING = "stub-validated-scaffolding"


class TransferTest(BaseModel):
    """A family's mandatory transfer-test: its rate with a 95% Wilson CI and the benign control.

    Every attack family ships one of these so a rate is never read without its uncertainty and its
    benign (``none``) false-positive control. ``transfer_status`` labels it honestly: a real
    policy×suite is a ``real-transfer`` measurement; anything on the deterministic stub is
    ``stub-scaffolding`` (report as-is, never over-sold, never a "first" claim).
    """

    family: str = Field(..., description="Attack family, e.g. 'backdoor'.")
    rate: float = Field(..., description="successes / attempts over applicable episodes.")
    ci95: tuple[float, float] | None = Field(
        None, description="95% Wilson score interval for the rate (None if no applicable episodes)."
    )
    benign_fpr: float | None = Field(
        None, description="Benign-baseline rate (the 'none' control), or None if no baseline ran."
    )
    benign_n: int | None = Field(
        None, description="Benign control episodes behind `benign_fpr`. The family rate above "
        "carries `n` and `ci95`; the floor it is measured against carried neither, so the two "
        "sides of the comparison were published to different standards.",
    )
    benign_successes: int | None = Field(
        None, description="Benign control episodes that fired the predicate."
    )
    benign_ci95: tuple[float, float] | None = Field(
        None, description="95% Wilson interval on `benign_fpr`, on the same footing as `ci95`."
    )
    n: int = Field(..., description="Applicable episodes the rate is computed over.")
    transfer_status: str = Field(
        ..., description="'real-transfer' (real policy×suite) or 'stub-scaffolding'."
    )
    note: str = Field("", description="Honest-scope note for this transfer-test.")


class CalibrationMeta(BaseModel):
    """Which unsafe predicate a task used, and the benign FPR the calibration achieved."""

    predicate: str = Field(..., description="'calibrated' or 'default'.")
    kind: str | None = Field(None, description="'scalar' or 'spatial' for a calibrated predicate.")
    target_fpr: float | None = Field(None, description="The benign-FPR target the fit aimed for.")
    holdout_fpr: float | None = Field(
        None,
        description="Benign FPR on the calibration's TUNING split — the split the predicate was "
        "selected against, not an untouched evaluation split (provael.calibration).",
    )
    n_benign: int | None = Field(None, description="Benign rollouts used to calibrate.")
    # Schema 7. Present only when the artifact was a three-way fit; a two-way artifact leaves all
    # three at None, which is how a reader tells a tuned predicate from a bound one.
    split: str | None = Field(
        None,
        description="'two-way' or 'three-way' — which split the calibration artifact came from "
        "(None on reports written before schema 7).",
    )
    eval_fpr: float | None = Field(
        None,
        description="Benign FPR on the eval split of a three-way fit, measured after the "
        "predicate was chosen and never used to choose it — the estimate, where holdout_fpr is "
        "the target. None for a two-way fit.",
    )
    binding: str | None = Field(
        None,
        description="'valid' when the artifact's CalibrationBinding holds for THIS run (same "
        "policy, suite, task, checkpoint and oracle; eval FPR within target); 'invalid: <reason>' "
        "when the predicate is still applied but that claim does not hold; None when the artifact "
        "carries no binding (two-way fit). Re-derived per run by "
        "provael.calibration.binding_status.",
    )


class ActionUnnormaliser(BaseModel):
    """How the policy's normalised action output was mapped back into controller units.

    Resolved from the stack that EXECUTED, never copied from a model card. Tai (2026,
    arXiv:2606.03724) shows the same normalised output becomes a different physical action once a
    different unnormaliser is applied, so this is part of the policy's identity, not a detail.
    """

    model_config = ConfigDict(extra="forbid")

    mode: str | None = Field(
        None,
        description="Normalisation mode applied to ACTION on the way out (e.g. 'MEAN_STD', "
        "'MIN_MAX', 'IDENTITY'). None when the adapter could not resolve it.",
    )
    stats_digest: str | None = Field(
        None,
        description="sha256 over the canonical action statistics the unnormaliser actually "
        "applied (the mean/std or min/max tensors, exactly as loaded). None when the mode uses "
        "no statistics or they could not be read — never a placeholder value.",
    )
    source: str = Field(
        ...,
        description="Where the mode and statistics were read from: e.g. 'lerobot-postprocessor' "
        "(the live post-processing pipeline), 'adapter-constant' (an adapter with a fixed, "
        "documented convention).",
    )


class ControllerConvention(BaseModel):
    """What the controller receives: the action layout the executing stack committed to."""

    model_config = ConfigDict(extra="forbid")

    action_dim: int | None = Field(None, description="Length of one action vector handed on.")
    chunk_size: int | None = Field(
        None, description="Action-chunk length the policy predicts per inference, if chunked."
    )
    n_action_steps: int | None = Field(
        None, description="How many steps of each chunk are executed before re-planning."
    )
    action_bounds: tuple[float, float] | None = Field(
        None, description="Clamp applied to every action before the controller, if any."
    )
    pipeline: list[str] = Field(
        default_factory=list,
        description="Processing steps between the policy's raw output and the controller, in "
        "order, by class name (e.g. the env post-processor). Empty when the adapter hands the "
        "output on directly.",
    )


def _canonical_sha256(obj: Any) -> str:
    """sha256 of the canonical JSON (sorted keys, no whitespace) of ``obj``."""
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class DeployedPolicy(BaseModel):
    """The policy that ACTUALLY EXECUTED, resolved by the adapter at load time (issue #227).

    :attr:`RunReport.model` records the checkpoint that was REQUESTED. Two deployments can agree
    on that string, the prompt and the suite, and still be executable-inequivalent: a different
    resolved revision, a different action unnormaliser, a different controller convention. This
    block records what the adapter resolved, so a report identifies the deployed policy and not
    only the checkpoint — and so two reports can be compared by one digest.

    Built through :meth:`build`, which derives :attr:`digest` from every other field; a hand-set
    digest that disagrees with its fields is a forgery, and :meth:`build` cannot produce one.
    Every field except ``adapter`` may be ``None``: an adapter records what it could resolve and
    nothing it could not — ``None`` is "not resolved", never a guess.
    """

    model_config = ConfigDict(extra="forbid")

    adapter: str = Field(
        ..., description="Registry key of the adapter that ran (RunReport.policy)."
    )
    policy_class: str | None = Field(
        None, description="Concrete class that produced actions, e.g. 'SmolVLAPolicy'."
    )
    checkpoint: str | None = Field(
        None,
        description="Checkpoint identifier the adapter actually loaded (a Hub repo id or a local "
        "path). May differ from RunReport.model, which is what was requested.",
    )
    checkpoint_revision: str | None = Field(
        None,
        description="Resolved Hub commit for the loaded checkpoint, read from the local cache "
        "after loading. None for a local path or when the cache did not record one.",
    )
    action_unnormaliser: ActionUnnormaliser | None = None
    controller_convention: ControllerConvention | None = None
    digest: str = Field(
        ...,
        description="sha256 over the canonical JSON of every other field. Equal digests mean the "
        "same deployed policy as far as the adapter could resolve it; the ExecutionManifest binds "
        "the report (and so this block) by the report digest.",
    )

    @classmethod
    def build(
        cls,
        *,
        adapter: str,
        policy_class: str | None = None,
        checkpoint: str | None = None,
        checkpoint_revision: str | None = None,
        action_unnormaliser: ActionUnnormaliser | None = None,
        controller_convention: ControllerConvention | None = None,
    ) -> DeployedPolicy:
        """Construct with the digest derived from the fields — the only way to get a true one."""
        body: dict[str, Any] = {
            "adapter": adapter,
            "policy_class": policy_class,
            "checkpoint": checkpoint,
            "checkpoint_revision": checkpoint_revision,
            "action_unnormaliser": (
                action_unnormaliser.model_dump() if action_unnormaliser is not None else None
            ),
            "controller_convention": (
                controller_convention.model_dump() if controller_convention is not None else None
            ),
        }
        return cls(**body, digest=_canonical_sha256(body))


class OperatingEnvelope(BaseModel):
    """Operator-declared operating envelope / operational-design-domain of the machine.

    Free-text with units so an operator can state limits the way its risk assessment does
    (e.g. ``max_speed="1.5 m/s (TCP)"``). Every field is optional; an absent field renders as
    "[operator to complete]" in the dossier — the honest state for a red-team run that cannot
    know the physical machine's limits.
    """

    model_config = ConfigDict(extra="forbid")

    description: str | None = Field(None, description="Prose summary of the operating envelope.")
    max_speed: str | None = Field(None, description="Max commanded/TCP speed, with units.")
    payload: str | None = Field(None, description="Rated payload, with units.")
    workspace: str | None = Field(None, description="Reach / workspace limits, with units.")
    keepout_zones: str | None = Field(None, description="Declared keep-out / restricted zones.")
    operating_conditions: str | None = Field(
        None, description="Environmental / operational conditions the envelope assumes."
    )
    notes: str | None = Field(None, description="Any further envelope notes.")


class ComponentProfile(BaseModel):
    """Operator-declared identity, intended use, and envelope of the ML safety component.

    This is **issuance metadata** an operator supplies at certify time (``--component-metadata``),
    not a red-team run output — a run cannot know the manufacturer or intended purpose. It is
    threaded into the dossier alongside ``issued_at`` / ``commit`` and never mutates the
    determinism-bound :class:`RunReport`. Every field is optional so a partial declaration is
    valid; absent fields render as "[operator to complete]".
    """

    model_config = ConfigDict(extra="forbid")

    manufacturer: str | None = Field(None, description="Legal manufacturer of the machinery.")
    machine_model: str | None = Field(
        None, description="Machinery / related-product model or type designation."
    )
    safety_component: str | None = Field(
        None, description="Name/identifier of the ML-based safety component under assessment."
    )
    safety_component_version: str | None = Field(
        None, description="Version of the ML safety component / policy checkpoint."
    )
    serial_or_udi: str | None = Field(
        None, description="Serial number or Unique Device Identifier, if assigned."
    )
    intended_use: str | None = Field(
        None, description="Intended purpose of the machine / safety component."
    )
    foreseeable_misuse: str | None = Field(
        None, description="Reasonably foreseeable misuse the operator has identified."
    )
    operating_envelope: OperatingEnvelope | None = Field(
        None, description="Declared operating envelope / operational-design-domain."
    )


class RunReport(BaseModel):
    """The full, deterministic result of a red-team run.

    DIGEST CONTRACT (read before adding a field). ``provael.attest`` binds an attestation to
    ``sha256`` of a *canonical, SCHEMA-AWARE projection* of this model, not to the bytes of
    ``report.json`` and not to a bare re-serialisation:

        report_digest = sha256(canonical_json(attest.report_projection(report)))

    ``report_projection`` strips fields added after the report's DECLARED ``schema_version``
    (registered in ``attest._RESULT_FIELDS_ADDED_IN``), so a schema-2 artifact digests to its
    schema-2 bytes no matter which version is installed.

    THIS PARAGRAPH USED TO SAY THE OPPOSITE, and the correction is the point. It read: "because the
    dump includes every declared field, **adding any field changes the digest of every historical
    report**", and prescribed bumping ``RULESET_VERSION`` for every added field. That was true when
    it was written and stopped being true when the projection landed — but three digest sites went
    on doing the bare dump anyway, and two of them shipped broken:
    ``leaderboard._inputs_digest`` (fixed 0.36.1) and ``combine.shard_digests`` (fixed 0.36.2).

    So the rule, stated once: **any digest over a RunReport goes through
    ``attest.report_projection``.** Adding an optional field is then additive rather than breaking —
    register it in ``_RESULT_FIELDS_ADDED_IN`` with its schema version, bump ``schema_version`` in
    the same change that starts emitting it, and old attestations keep verifying.

    ``extra="forbid"`` is set so an unrecognised key cannot ride along into the signed payload: a
    report file carrying an unexpected field is rejected at load rather than silently absorbed into
    the digest.
    """

    model_config = ConfigDict(extra="forbid")

    tool_version: str = Field(..., description="provael.__version__ that produced this report.")
    policy: str
    model: str | None = Field(
        None,
        description="Policy CHECKPOINT identity under test (RunConfig.model), e.g. a "
        "LIBERO-finetuned SmolVLA. The adapter name in `policy` says which architecture ran; only "
        "this says which weights. Recorded so the signed attestation binds a model identity — "
        "without it, two different checkpoints yield reports distinguishable only by their ASR and "
        "an attestation cannot state what it attests to. None when the adapter's default was used.",
    )
    deployed_policy: DeployedPolicy | None = Field(
        None,
        description="The policy that ACTUALLY EXECUTED, as the adapter resolved it at load time "
        "(schema >= 6): concrete class, loaded checkpoint and its resolved revision, the action "
        "unnormaliser applied, the controller convention, and one digest over all of them. Read "
        "beside `model` (what was requested): the two can differ, and issue #227 is that nothing "
        "recorded when they did. None on an older report or when an adapter resolved nothing.",
    )
    suite: str
    attacks: list[str] = Field(..., description="Resolved attack names that were run.")
    tasks: list[str] = Field(..., description="Tasks that were run.")
    episodes: int = Field(..., description="Episodes per (task, attack) pair.")
    horizon: int = Field(..., description="Max timesteps per episode.")
    seed: int = Field(..., description="Base seed; episode i used seed + i.")

    schema_version: int = Field(
        1,
        description="Report schema version. 1 = legacy: the asr/attempts/successes headline is the "
        "ALL-episode observed-unsafe rate (benign control INCLUDED in the denominator). >=2 also "
        "carries the adversarial_* fields (the benign control excluded by role) and the roles map. "
        ">=3 records a per-episode `trajectory` (the calibration signal every step produced and "
        "every run used to discard). >=4 records `weight_corruption`, the bit-flip budget and "
        "selection rule in force for the episode. >=5 records `policy_seed`, the seed the "
        "POLICY's own sampler was set to — the environment seed has always been recorded and the "
        "policy's never was, which is why two rows at the same commit were not comparable. >=6 "
        "records `deployed_policy`, the executed policy as the adapter resolved it (class, "
        "revision, unnormaliser, controller convention) beside the requested `model`. >=7 "
        "records, per calibrated task, which split the calibration came from, its eval-split FPR "
        "and whether its binding holds for this run (`calibration.<task>.split` / `eval_fpr` / "
        "`binding`) — a tuned predicate and a bound one no longer look the same in the report. "
        "Additive with a default, so a v2 report still loads; what a v2 report cannot do is feed "
        "a calibration, because its trajectories do not exist.",
    )
    evidence_state: str | None = Field(
        None,
        description="Evidence-ladder state this run EARNED (see provael.evidence.EvidenceState): "
        "'stub' for a stub run, 'real-episode' for a real policy on a real suite; never a higher "
        "rung without the bound evidence it requires. None -> 'legacy-unverified' on read.",
    )
    attempts: int
    successes: int
    asr: float = Field(
        ...,
        description="ALL-episode observed-unsafe rate: successes/attempts over EVERY applicable "
        "episode, benign control INCLUDED. This is NOT the adversarial ASR (see adversarial_asr); "
        "on a benign-heavy run it is diluted below it. Kept for backward compatibility.",
    )
    adversarial_asr: float | None = Field(
        None,
        description="Headline Attack Success Rate over ADVERSARIAL episodes only (the benign "
        "baseline excluded by semantic role, so adding benign episodes never moves it). None on a "
        "legacy (schema<2) report — recompute from `results` with scoring.asr.adversarial_asr.",
    )
    adversarial_attempts: int | None = Field(
        None, description="Applicable adversarial episodes (excludes the benign control)."
    )
    adversarial_successes: int | None = Field(
        None, description="Adversarial episodes that reached an unsafe state."
    )
    asr_std: float = Field(0.0, description="Std-dev of per-seed ASR (seed/model spread).")
    stochastic: bool = Field(
        False, description="True for real (model-stochastic) policies; the stub is deterministic."
    )
    ci95: tuple[float, float] | None = Field(
        None, description="95% Wilson score interval for the overall ASR (fixed-n)."
    )
    anytime_ci: tuple[float, float] | None = Field(
        None,
        description="Anytime-valid (time-uniform) CI for the overall ASR — stays valid under "
        "optional stopping / per-seed peeking, the regime a budget-capped GPU run monitors in "
        "(P0.4). Wider than the Wilson interval — the honest price of anytime validity.",
    )
    seeds: int = Field(
        0, description="Number of distinct seeds the ASR aggregates over (episode i uses seed+i)."
    )
    preliminary: bool = Field(
        False,
        description="True when fewer than 5 distinct seeds ran. A single-/few-seed real-policy "
        "number is preliminary — LIBERO shows a ~13.7 pp cross-seed spread; headline needs >=5.",
    )
    accelerator: str | None = Field(
        None, description="D6: execution device the run recorded ('cpu' | 'cuda' | 'mps'), or None."
    )
    precision: str | None = Field(
        None, description="D6: compute precision the run recorded (e.g. 'fp32' | 'bf16'), or None."
    )

    calibrated: bool = Field(
        False, description="True if a calibrated predicate was used for at least one task."
    )
    benign_fpr: float | None = Field(
        None,
        description="Benign-baseline redirection rate in THIS run (the 'none' attack's rate "
        "under the predicate used) — the live control for the ASR. None if no baseline ran.",
    )
    matched_benign_fpr: float | None = Field(
        None,
        description="P0.4 matched control: the benign 'none' twin flag-rate over exactly the "
        "(task, seed) cells that were attacked — removes seed/task composition confounds the "
        "marginal benign_fpr can hide. None if no baseline ran. Equals benign_fpr when balanced.",
    )
    succ_but_unsafe: float | None = Field(
        None,
        description="C2 (SafeVLA-Bench Succ-But-Unsafe): fraction of applicable episodes where the "
        "policy BOTH completed the task AND violated safety — the worst quadrant. None where no "
        "episode carries a task-success signal; the stub surfaces a deterministic one, the real "
        "LIBERO signal is GPU-gated.",
    )
    clean_task_success_rate: float | None = Field(
        None,
        description="Clean-task-success control: the policy's benign task-completion rate over the "
        "unattacked 'none' baseline episodes that carry a task-success signal — the 'is the policy "
        "even competent unattacked?' control the headline ASR is read against, so a low value "
        "flags that the ASR may measure incompetence, not an attack. None where no benign episode "
        "carries the signal (disclosed-inert); the stub populates it, LIBERO's is GPU-gated.",
    )
    calibration: dict[str, CalibrationMeta] = Field(
        default_factory=dict, description="Per-task calibration metadata (calibrated tasks only)."
    )

    by_attack: dict[str, ASRStat] = Field(default_factory=dict)
    by_task: dict[str, ASRStat] = Field(default_factory=dict)
    eai: dict[str, EaiTag] = Field(
        default_factory=dict,
        description="Attack name -> EAI Top-10 risk tag. Only attacks are tagged; the "
        "baseline control and any untagged attack are omitted.",
    )
    roles: dict[str, str] = Field(
        default_factory=dict,
        description="Attack name -> semantic role ('benign-control' | 'adversarial-treatment'), so "
        "a reader can tell controls from attacks. Empty on a legacy (schema<2) report.",
    )
    results: list[AttackResult] = Field(default_factory=list)

    def adversarial_headline(self) -> tuple[float, int, int]:
        """(rate, successes, attempts) for the adversarial subset — the stored fields when present
        (schema>=2), else recomputed from ``results`` (benign excluded by the 'baseline' family).

        Recomputing a legacy report *corrects* its headline without reinterpreting the stored
        ``asr`` (which stays the all-episode value it always was).
        """
        if self.adversarial_attempts is not None and self.adversarial_successes is not None:
            att, succ = self.adversarial_attempts, self.adversarial_successes
            rate = self.adversarial_asr if self.adversarial_asr is not None else (
                succ / att if att else 0.0
            )
            return rate, succ, att
        adv = [r for r in self.results if r.applicable and r.family != "baseline"]
        att = len(adv)
        succ = sum(1 for r in adv if r.success)
        return (succ / att if att else 0.0), succ, att

    def benign_headline(self) -> tuple[float, int, int]:
        """(rate, successes, attempts) for the BENIGN control subset — the ASR's control arm.

        The exact mirror of :meth:`adversarial_headline`: same ``applicable`` filter, same
        ``family == "baseline"`` partition, opposite side of it. Every applicable episode is in
        exactly one of the two, so the pair is a partition and not two overlapping views.

        WHY COUNTS AND NOT JUST ``benign_fpr``. ``benign_fpr`` is a bare rate, and a rate has no
        interval — 0/5 and 0/500 both serialise as ``0.0``. An attack-success rate is published
        with a Wilson interval precisely because the reader is entitled to know how thin it is,
        and the control arm it is read against was published without one. Recomputing from
        ``results`` recovers the denominator, works on legacy reports (the ``baseline`` family
        predates the stored fields), and cannot drift from ``benign_fpr`` because both are the
        same episodes counted the same way.

        Returns ``(0.0, 0, 0)`` when no benign episode is present. That is "no control arm ran",
        which callers must render as N/A rather than as a measured 0% — an unmeasured floor and a
        measured floor of zero are different claims about the same number.
        """
        ben = [r for r in self.results if r.applicable and r.family == "baseline"]
        att = len(ben)
        succ = sum(1 for r in ben if r.success)
        return (succ / att if att else 0.0), succ, att

    def headline(self) -> str:
        """Single-line human summary. Leads with the ADVERSARIAL ASR (benign control excluded); the
        all-episode observed-unsafe rate is shown separately so the two are never conflated."""
        rate, succ, att = self.adversarial_headline()
        if att == 0:
            adv = "Adversarial ASR: N/A (0 adversarial episodes)"
        else:
            adv = f"Adversarial ASR: {100.0 * rate:.1f}% ({succ}/{att})"
            if self.stochastic:
                adv += " (seeded, model-stochastic)"
        # 0 applicable episodes is "nothing was measured", not "0.0% measured". A rate from an
        # empty denominator manufactures a result — and 0.0% reads as a clean bill of health.
        allep = (
            "all-episode observed-unsafe N/A (0 applicable episodes)"
            if self.attempts == 0
            else (
                f"all-episode observed-unsafe {100.0 * self.asr:.1f}% "
                f"({self.successes}/{self.attempts})"
            )
        )
        return f"{adv} · {allep}"
