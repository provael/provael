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
from pydantic import BaseModel, ConfigDict, Field, model_validator

# A policy observation (what a suite hands to a policy) and an environment state
# snapshot (what ``SuiteAdapter.step`` returns as its info dict) are both plain
# string-keyed dicts. They are kept as aliases — not models — so adapters around
# real simulators (e.g. LIBERO) can pass their native dicts through untouched.
type Observation = dict[str, Any]
type State = dict[str, Any]


def init_state_of(observation: Observation) -> int | None:
    """The fixed initial state a suite's reset loaded, from the observation the reset returned.

    A suite that walks a list of fixed initial states (LIBERO) puts the one each reset loaded under
    ``"init_state"``; every other suite leaves the key out. Anything but a plain integer reads as
    ``None`` rather than being coerced into a scene nobody recorded.
    """
    loaded = observation.get("init_state")
    return loaded if isinstance(loaded, int) and not isinstance(loaded, bool) else None

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


#: The calibration signal's channels (P1.5): a spatial suite's position, a scalar suite's danger
#: level. A trajectory written before schema 9 names no channels and holds exactly one of these.
POSITION_CHANNELS: tuple[str, ...] = ("x", "y", "z")
DANGER_CHANNELS: tuple[str, ...] = ("danger",)


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

    NAMED CHANNELS (schema 9, P1.5). A suite may record more than its calibration signal: LIBERO
    records the end-effector's orientation and the gripper opening beside its position. ``channels``
    names every column, so a reader never infers the stride, and :meth:`calibration_signal` picks
    the position or danger columns out of whatever else was recorded. A trajectory written before
    schema 9 names none and is read by its width, as it always was.
    """

    encoding: Literal["float32-zlib-b64"] = Field(
        "float32-zlib-b64", description="Wire format of `data`. One value today, named so a future "
        "format is a new value rather than a silent reinterpretation of these bytes."
    )
    shape: tuple[int, int] = Field(
        ..., description="(steps, dims). Without `channels`, dims is 3 for a spatial suite (x, y, "
        "z) and 1 for a scalar-danger suite, so a reader can tell the two apart without guessing."
    )
    data: str = Field(..., description="base64(zlib(float32 little-endian, C-order)).")
    channels: list[str] | None = Field(
        None,
        description="The name of each column, in order, e.g. ['x', 'y', 'z', 'qx', 'qy', 'qz', "
        "'qw', 'gripper_opening'] on LIBERO or ['danger'] on the stub; a column a step could not "
        "read is NaN there. None on a trajectory written before schema 9, where the width says "
        "which signal it is (3: x, y, z; 1: danger).",
    )

    @model_validator(mode="after")
    def _channels_fit(self) -> Trajectory:
        if self.channels is not None:
            if len(self.channels) != self.shape[1]:
                raise ValueError(
                    f"trajectory names {len(self.channels)} channel(s) for {self.shape[1]} "
                    "column(s)"
                )
            if len(set(self.channels)) != len(self.channels):
                raise ValueError(f"trajectory channel names repeat: {self.channels}")
        return self

    @classmethod
    def encode(
        cls, samples: Sequence[Sequence[float]], channels: Sequence[str] | None = None
    ) -> Trajectory:
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
            channels=list(channels) if channels is not None else None,
        )

    def channel_names(self) -> tuple[str, ...]:
        """Every column's name: :attr:`channels`, or for a trajectory before schema 9 its signal.

        Raises ``ValueError`` for an unnamed trajectory of any other width, which no suite wrote.
        """
        if self.channels is not None:
            return tuple(self.channels)
        legacy = {len(POSITION_CHANNELS): POSITION_CHANNELS, len(DANGER_CHANNELS): DANGER_CHANNELS}
        names = legacy.get(self.shape[1])
        if names is None:
            raise ValueError(f"an unnamed trajectory of width {self.shape[1]} has no known layout")
        return names

    def columns(self, *names: str) -> list[list[float]]:
        """The named columns, per step, in the order asked for."""
        index = {name: i for i, name in enumerate(self.channel_names())}
        missing = [name for name in names if name not in index]
        if missing:
            raise ValueError(f"trajectory has no channel(s) {missing}; it has {list(index)}")
        picks = [index[name] for name in names]
        return [[row[i] for i in picks] for row in self.decode()]

    def calibration_signal(self) -> list[list[float]]:
        """The per-step calibration signal: x, y, z on a spatial suite, danger on a scalar one.

        What a keep-out fit or a workspace bound reads, whatever else the trajectory records.
        """
        names = self.channel_names()
        for wanted in (POSITION_CHANNELS, DANGER_CHANNELS):
            if all(name in names for name in wanted):
                return self.columns(*wanted)
        raise ValueError(f"trajectory carries no calibration signal; its channels are {names}")

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


class SceneBody(BaseModel):
    """One non-robot body of a scene right after its reset: where it stood and which way it faced.

    Rounded to six decimals (a micron, a microradian) for reading. The episode's
    ``scene_t0_digest`` is taken over the exact values, so two scenes that round alike and differ
    still digest differently.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="The simulator's body name.")
    pos: tuple[float, float, float] = Field(..., description="World position (x, y, z), metres.")
    yaw: float = Field(
        ..., description="Rotation about the world z axis, radians, from the body's quaternion."
    )


@dataclass(frozen=True)
class SceneSnapshot:
    """What a suite read from its simulator right after a reset: a digest and the bodies."""

    digest: str
    bodies: tuple[SceneBody, ...]


#: How an episode ended (schema 9): the predicate fired (first-event termination stops there), the
#: suite ended it at task success (LIBERO's ``done``), every horizon step ran, the suite ended it
#: for another reason (its own step cap), or a simulator exception recorded under
#: ``--record-episode-errors``.
Termination = Literal["unsafe_exit", "task_success", "horizon", "env_truncated", "error"]

#: How a run ends its episodes (P1.4). ``first-event``, the only mode before schema 9: an episode
#: stops at its first envelope exit and at the suite's ``done`` (on LIBERO, task success).
#: ``fixed-horizon``: an episode runs every ``horizon`` step unless the suite cannot go on; an exit
#: and a success both latch, and the steps after them are still scored, so exposure is dwell.
TerminationMode = Literal["first-event", "fixed-horizon"]

#: Why a failed episode failed, where the run can say (P1.4): it left the envelope, the contact
#: predicate fired (``collision``, the ``physical_hazard`` endpoint), the goal object was never
#: grasped, it was grasped and let go short of the goal (``dropped``), or the steps ran out with the
#: object held or on a task with nothing to grasp (``timeout``). See
#: :func:`provael.scoring.failure.failure_cause`.
FailureCause = Literal["envelope_exit", "collision", "missed_grasp", "dropped", "timeout"]

#: Where the outcome of an episode was read from. Neither is an independent observer: both are
#: the harness reading state it computed or simulated itself, in its own process, and a record
#: that carries one says so rather than implying a third party watched.
SIMULATOR_VANTAGE = "simulator state, read in the harness process"
FIXTURE_VANTAGE = "fixture state, computed in the harness process"


class EpisodeCoverage(BaseModel):
    """How much of an episode the predicate actually saw: the denominator an absence claim needs."""

    model_config = ConfigDict(extra="forbid")

    steps_observed: int = Field(..., ge=0, description="Executed steps whose state was read.")
    horizon: int = Field(..., ge=1, description="The most steps the episode could have run.")
    steps_without_pose: int = Field(
        ...,
        ge=0,
        description="Executed steps the predicate could not judge because its input was missing "
        "(the end-effector pose, on a spatial suite).",
    )


class EpisodeObservation(BaseModel):
    """Whether an envelope exit was seen, from where, and over how much of the episode (P1.3).

    ``present``: an exit was observed. ``absent``: the predicate judged every executed step and saw
    none. ``not_established``: some step could not be judged and no exit was seen, which is never
    the same claim as "no exit".
    """

    model_config = ConfigDict(extra="forbid")

    state: Literal["present", "absent", "not_established"]
    vantage: str = Field(..., description="Where the outcome was read from (SIMULATOR_VANTAGE).")
    coverage: EpisodeCoverage


class DeliveredInputs(BaseModel):
    """What the policy was actually handed in one episode, and the attack's settings as read (P1.8).

    Taken where every input crosses into the policy, right before ``policy.act`` and after the
    attack and any defense, so it records what was delivered and not what was configured. The
    benign arm takes the same path with nothing declared, so its record is the reference an
    attacked twin's is read against. An attack's search queries are not live steps and are not in
    it.
    """

    model_config = ConfigDict(extra="forbid")

    instruction_sha256: list[str] = Field(
        ...,
        description="sha256 (UTF-8) of each distinct instruction string the policy was handed, "
        "in the order first handed.",
    )
    image_sha256: str | None = Field(
        None,
        description="Rolling sha256 over the primary camera image (`observation['image']`, the "
        "frame every image-channel attack edits) the policy was handed on each step: the step "
        "number, dtype, shape and bytes of each. None when no step handed one (the stub has no "
        "camera).",
    )
    image_steps: int = Field(0, ge=0, description="Steps whose image is in `image_sha256`.")
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="The attack's declared parameters (`Attack.parameters`), each as first read "
        "while the episode ran, as JSON: the realized perturbation settings. {} for an attack "
        "that declares none, the benign arm included. The runner fails a run in which a declared "
        "parameter was never read during an episode the attack ran in.",
    )


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
        "the stub; bound by the attestation subject with the rest of report.json.",
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
    init_state: int | None = Field(
        None,
        description="Which of the task's fixed initial states this episode's reset loaded, read "
        "from the environment after the reset (LIBERO: lerobot's `init_state_id` less the stride "
        "the reset added, modulo the number of states). None where the suite has no fixed "
        "initial states.\n\nThe seed does not pick it under lerobot 0.5.1: a reset counter does, "
        "and a success ends an episode with a second reset, so two episodes at one seed can start "
        "from different scenes and a resumed run restarts the counter. Neither leaves a trace in "
        "`seed`; this field is the record of which scene ran (#136). Present from "
        "schema_version 8.",
    )
    scene_t0_digest: str | None = Field(
        None,
        description="sha256 over the simulator state right after this episode's reset: qpos, "
        "qvel, then every body's name, position and orientation, as float64. Two episodes started "
        "from one scene only if these are equal; `init_state` is the index, this is the scene. "
        "None where the suite exposes no simulator state (the stub) or the read failed. Present "
        "from schema_version 9.",
    )
    scene_t0: list[SceneBody] | None = Field(
        None,
        description="The non-robot bodies of that scene with their positions and yaw, for reading "
        "(rounded to 1e-6; the digest is over the exact values). None where `scene_t0_digest` is. "
        "Present from schema_version 9.",
    )
    termination: Termination | None = Field(
        None,
        description="How the episode ended: 'unsafe_exit', 'task_success', 'horizon', "
        "'env_truncated' or 'error' (see provael.types.Termination). None on a not-applicable "
        "record, where no episode ran. Present from schema_version 9.",
    )
    verdict: Literal["judged", "unjudged"] | None = Field(
        None,
        description="'judged' when the envelope outcome was established, 'unjudged' when it was "
        "not (a simulator exception, or a step the predicate could not judge with no exit seen), "
        "the reason in `unjudged_reason`. An unjudged episode leaves every rate's numerator and "
        "denominator and is counted beside it. None on a not-applicable record; a report before "
        "schema 9 records none and every applicable episode in it counts, as it always did.",
    )
    unjudged_reason: str | None = Field(
        None, description="Why the episode is unjudged; None when it was judged. Schema >= 9."
    )
    observation: EpisodeObservation | None = Field(
        None,
        description="Whether an exit was seen, the vantage it was read from, and the coverage "
        "behind the claim (steps observed, horizon, steps without a pose). Schema >= 9.",
    )
    failure_cause: FailureCause | None = Field(
        None,
        description="Why the episode failed, for one that left the envelope or did not complete "
        "its task: 'envelope_exit', 'collision' (the physical_hazard endpoint), 'missed_grasp', "
        "'dropped' or 'timeout' (see provael.scoring.failure). None for an episode that did not "
        "fail, and wherever the signals cannot say which, never a guess. Schema >= 9.",
    )
    delivered_inputs: DeliveredInputs | None = Field(
        None,
        description="What the policy was handed on the live steps: a sha256 per distinct "
        "instruction, a rolling sha256 over the camera images, and the attack's declared "
        "parameters as read (see DeliveredInputs). None on a not-applicable record. Schema >= 9.",
    )

    @property
    def scored(self) -> bool:
        """Whether this episode counts toward a rate: applicable, and not unjudged.

        Every rate reads this rather than ``applicable``. A report before schema 9 records no
        verdict, so every applicable episode in it is scored exactly as before and no committed
        number moves.
        """
        return self.applicable and self.verdict != "unjudged"


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


#: How far a stored rate may sit from its own successes / trials before a RateStat refuses it.
RATE_TOLERANCE = 1e-6


class RateInterval(BaseModel):
    """A confidence interval for one rate, named by the method that computed it (schema 9)."""

    model_config = ConfigDict(extra="forbid")

    method: str = Field(
        ..., description="How it was computed, e.g. 'wilson-score (episode-level)'."
    )
    level: float = Field(..., gt=0.0, lt=1.0, description="Nominal coverage, e.g. 0.95.")
    low: float = Field(..., ge=0.0, le=1.0)
    high: float = Field(..., ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _ordered(self) -> RateInterval:
        if self.low > self.high:
            raise ValueError(f"interval low {self.low} is above high {self.high}")
        return self


class RateStat(BaseModel):
    """A rate with the counts it came from, its interval and what it left out (schema 9, P1.6).

    The numerator is never reconstructed from a rounded float: ``successes`` and ``trials`` travel
    with ``rate``, and the validator refuses a rate that disagrees with them by more than 1e-6, a
    numerator above its denominator, a rate on an empty slice, and a rate over trials without its
    interval. ``n_unjudged`` counts the slice's episodes that were not judged and so sit outside
    both counts (P1.3).
    """

    model_config = ConfigDict(extra="forbid")

    successes: int = Field(..., ge=0, description="Episodes in the numerator.")
    trials: int = Field(..., ge=0, description="Episodes in the denominator.")
    rate: float | None = Field(
        ..., description="successes / trials; None when trials is 0 (N/A, not a measured 0%)."
    )
    interval: RateInterval | None = Field(
        ..., description="The rate's interval; None exactly when trials is 0."
    )
    n_unjudged: int = Field(
        0, ge=0, description="Episodes of this slice left out of both counts as unjudged."
    )

    @model_validator(mode="after")
    def _consistent(self) -> RateStat:
        if self.successes > self.trials:
            raise ValueError(f"successes {self.successes} exceed trials {self.trials}")
        if self.trials == 0:
            if self.rate is not None or self.interval is not None:
                raise ValueError("a slice with no trials has no rate and no interval")
            return self
        if self.rate is None or self.interval is None:
            raise ValueError("a rate over trials carries both the rate and its interval")
        if abs(self.rate - self.successes / self.trials) > RATE_TOLERANCE:
            raise ValueError(
                f"rate {self.rate} disagrees with {self.successes}/{self.trials} by more than "
                f"{RATE_TOLERANCE}"
            )
        low, high = self.interval.low - RATE_TOLERANCE, self.interval.high + RATE_TOLERANCE
        if not low <= self.rate <= high:
            raise ValueError(f"rate {self.rate} lies outside its interval")
        return self


class DifferenceInterval(BaseModel):
    """An interval for a difference of two rates, named by its method (schema 9, P2.4)."""

    model_config = ConfigDict(extra="forbid")

    method: str = Field(..., description="How it was computed, e.g. Newcombe's paired score.")
    level: float = Field(..., gt=0.0, lt=1.0, description="Nominal coverage, e.g. 0.95.")
    low: float = Field(..., ge=-1.0, le=1.0)
    high: float = Field(..., ge=-1.0, le=1.0)

    @model_validator(mode="after")
    def _ordered(self) -> DifferenceInterval:
        if self.low > self.high:
            raise ValueError(f"interval low {self.low} is above high {self.high}")
        return self


class PairedDifferenceStat(BaseModel):
    """An arm's rate minus its benign twins' over the cells they share (schema 9, P2.4).

    The whole paired 2x2 table travels with the interval: ``attack_only`` and ``benign_only`` are
    McNemar's discordant counts b and c, and ``pairs`` is n. The validator refuses a table that
    does not add up and an estimate that is not ``(b - c) / n``.
    """

    model_config = ConfigDict(extra="forbid")

    pairs: int = Field(..., ge=1, description="n: the (task, seed) cells both arms share.")
    both: int = Field(..., ge=0, description="Cells where the arm and its twin both left.")
    attack_only: int = Field(..., ge=0, description="b: the arm left, its benign twin did not.")
    benign_only: int = Field(..., ge=0, description="c: the benign twin left, the arm did not.")
    neither: int = Field(..., ge=0, description="Cells where neither left.")
    estimate: float = Field(..., ge=-1.0, le=1.0, description="(b - c) / n.")
    interval: DifferenceInterval

    @model_validator(mode="after")
    def _consistent(self) -> PairedDifferenceStat:
        if self.both + self.attack_only + self.benign_only + self.neither != self.pairs:
            raise ValueError("the paired table's cells do not add up to its pairs")
        expected = (self.attack_only - self.benign_only) / self.pairs
        if abs(self.estimate - expected) > RATE_TOLERANCE:
            raise ValueError(f"estimate {self.estimate} disagrees with (b - c) / n = {expected}")
        low, high = self.interval.low - RATE_TOLERANCE, self.interval.high + RATE_TOLERANCE
        if not low <= self.estimate <= high:
            raise ValueError(f"estimate {self.estimate} lies outside its interval")
        return self


class ReportRates(BaseModel):
    """Every rate a report publishes, each as a :class:`RateStat` (schema 9, P1.6).

    Resolved once, by :func:`provael.scoring.asr.report_rates`, for every emitter. The bare float
    fields beside it (``benign_fpr``, ``matched_benign_fpr``, ``succ_but_unsafe``,
    ``clean_task_success_rate``, ``ci95``) stay for older readers and agree with it.
    """

    model_config = ConfigDict(extra="forbid")

    adversarial: RateStat = Field(..., description="The headline ASR: adversarial arms only.")
    all_episodes: RateStat = Field(
        ..., description="The all-episode observed-unsafe rate (`asr`; benign included)."
    )
    benign_floor: RateStat | None = Field(
        None, description="The benign control arm's rate; None when no benign episode ran."
    )
    matched_benign_floor: RateStat | None = Field(
        None, description="The benign twins of the attacked (task, seed) cells, cell by cell."
    )
    clean_task_success: RateStat | None = Field(
        None, description="Task success on the benign arm; None where no episode carries it."
    )
    succ_but_unsafe: RateStat | None = Field(
        None,
        description="Completed the task and left the envelope; None where the run could not "
        "observe it (E-2026-21) or no episode carries a task-success signal.",
    )
    by_attack: dict[str, RateStat] = Field(default_factory=dict)
    by_task: dict[str, RateStat] = Field(default_factory=dict)
    task_success_by_attack: dict[str, RateStat] = Field(
        default_factory=dict,
        description="Per arm: task success over its episodes that carry a task-success signal. "
        "An arm that leaves the envelope rarely can still stop doing the task, which an unsafe "
        "rate alone cannot show. Arms whose episodes carry no signal are absent, never 0%.",
    )
    clean_task_success_by_task: dict[str, RateStat] = Field(
        default_factory=dict,
        description="Per task: the benign arm's task success (clean task success, task by task), "
        "the competence each task's attack rates are read against. Tasks whose benign episodes "
        "carry no signal are absent, never 0%.",
    )
    paired_difference: dict[str, PairedDifferenceStat] = Field(
        default_factory=dict,
        description="Per arm paired with the benign arm: its rate minus its twins' over the "
        "(task, seed) cells they share, with Newcombe's paired score interval and the table it "
        "came from. Matched on task and seed, which is not a shared starting scene on an unpinned "
        "LIBERO run (E-2026-19). Arms with no shared cell are absent.",
    )


class CompetenceEpisode(BaseModel):
    """One benign episode of the competence pre-run (P2.2): its seed, scene, ending and result."""

    model_config = ConfigDict(extra="forbid")

    seed: int
    init_state: int | None = Field(None, description="The fixed initial state its reset loaded.")
    task_success: bool | None = Field(
        ..., description="Whether it completed the task; None where the suite surfaced no signal."
    )
    termination: Termination | None = Field(None, description="How it ended (schema 9).")
    steps: int = Field(..., ge=0, description="Steps it executed.")


class CompetenceTask(BaseModel):
    """The competence check on one task: the pre-run's task success and what it admitted (P2.2)."""

    model_config = ConfigDict(extra="forbid")

    task_success: RateStat = Field(
        ...,
        description="Pre-run episodes that completed the task over those carrying the signal, "
        "with the Wilson interval. Compared with the floor as a point rate.",
    )
    admitted: bool = Field(
        ..., description="True when task success met the floor, so every arm ran on the task."
    )
    refused: list[str] = Field(
        default_factory=list,
        description="The adversarial arms not run on this task because it fell below the floor. "
        "The benign arm and the harmless-variation controls still ran.",
    )
    episodes: list[CompetenceEpisode] = Field(default_factory=list)


class CompetenceCheck(BaseModel):
    """``--competence-check``: benign episodes per task before the arms, and the floor (P2.2).

    The pre-run asks whether the policy can do the task at all before an attack is read against
    it: a 0% rate on a policy that cannot act measures nothing. Its episodes run at seeds after the
    run's own and enter no rate; a task below the floor has its adversarial arms refused, and the
    refusal is recorded here rather than left as missing rows.
    """

    model_config = ConfigDict(extra="forbid")

    episodes_per_task: int = Field(..., ge=1, description="Benign pre-run episodes per task.")
    floor: float = Field(..., ge=0.0, le=1.0, description="The task-success floor applied.")
    by_task: dict[str, CompetenceTask] = Field(default_factory=dict)


class ScenePairing(BaseModel):
    """Whether each attacked episode started from its benign twin's scene (schema 9, P1.2).

    A pair is an applicable episode of any arm but the benign baseline, with the benign episodes
    at its ``(task, seed)``. On LIBERO the seed does not pick the scene unless the run pins it
    (E-2026-19), so a pair shares a task and a seed and may not share a starting scene; this says
    how many did. A side that recorded nothing is unrecorded, never a match.
    """

    model_config = ConfigDict(extra="forbid")

    pairs: int = Field(..., ge=0, description="Attacked episodes with a benign twin.")
    init_state_matched: int = Field(
        ..., ge=0, description="Pairs whose two sides recorded one equal `init_state`."
    )
    init_state_unrecorded: int = Field(
        ..., ge=0, description="Pairs where either side recorded no `init_state`."
    )
    scene_matched: int = Field(
        ..., ge=0, description="Pairs whose two sides recorded one equal `scene_t0_digest`."
    )
    scene_unrecorded: int = Field(
        ..., ge=0, description="Pairs where either side recorded no `scene_t0_digest`."
    )


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


class InputNormaliser(BaseModel):
    """How the policy's observation inputs were normalised on the way in (schema 9).

    The input-side twin of :class:`ActionUnnormaliser`. The same checkpoint served with different
    state statistics sees a different observation, and a pre-processor whose statistics never
    loaded normalises nothing without saying so (lerobot#4047). Resolved from the pipeline that
    executed, never from a model card.
    """

    model_config = ConfigDict(extra="forbid")

    state_mode: str | None = Field(
        None,
        description="Normalisation mode applied to STATE inputs (e.g. 'MEAN_STD'). None when the "
        "adapter could not resolve it.",
    )
    visual_mode: str | None = Field(
        None,
        description="Normalisation mode applied to VISUAL inputs (e.g. 'IDENTITY'). None when the "
        "adapter could not resolve it.",
    )
    stats_digest: str | None = Field(
        None,
        description="sha256 over the canonical statistics the normaliser applies to observation "
        "features (every statistic except the action's), exactly as loaded. None when it applies "
        "none or they could not be read — never a placeholder value.",
    )
    source: str = Field(
        ...,
        description="Where the modes and statistics were read from, e.g. 'lerobot-preprocessor' "
        "(the live pre-processing pipeline).",
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
    # Schema 9: the rest of what makes two loads of one checkpoint executable-inequivalent. Every
    # one is None where the adapter could not resolve it; registered in
    # `attest._DEPLOYED_POLICY_FIELDS_ADDED_IN`, so a report declaring less digests without them.
    input_normaliser: InputNormaliser | None = Field(
        None,
        description="The observation normaliser the policy's pre-processor applied: STATE and "
        "VISUAL modes and a digest over their statistics (schema >= 9).",
    )
    preprocessor_digest: str | None = Field(
        None,
        description="sha256 over the pre-processor files the adapter loaded: the canonical JSON "
        "list of [filename, sha256] pairs for the pipeline's config file and then each step's "
        "state file, in load order, so a reader can rebuild it from per-file hashes (schema >= 9). "
        "None when the files could not be located without the network.",
    )
    postprocessor_digest: str | None = Field(
        None,
        description="The same digest over the post-processor files (schema >= 9).",
    )
    weights_digest: str | None = Field(
        None,
        description="sha256 of the weight file the policy loaded (lerobot 0.5.1 loads exactly one, "
        "`model.safetensors`), which is what `sha256sum` prints for it. Also fills the execution "
        "manifest's `checkpoint_digest` (schema >= 9).",
    )
    rename_map: dict[str, str] | None = Field(
        None,
        description="The observation-key rename map the pre-processor applied, read from its "
        "rename step: {} when it applies none (schema >= 9). None when unresolved.",
    )
    camera_keys: list[str] | None = Field(
        None,
        description="The camera inputs the policy consumed, in the order it consumes them (its "
        "config's image features, after any rename). [] for a policy that reads no camera "
        "(schema >= 9).",
    )
    denoising_steps: int | None = Field(
        None,
        description="Denoising (flow-integration) steps per predicted chunk, read from the policy "
        "config (SmolVLA `num_steps`, pi0 / pi0.5 `num_inference_steps`). None for a head that has "
        "no such setting or when it was not set explicitly (schema >= 9).",
    )
    control_rate_hz: int | None = Field(
        None,
        description="The environment control rate the adapter was configured with "
        "(SuiteFeatures.fps), in Hz (schema >= 9).",
    )
    temporal_ensemble_coeff: float | None = Field(
        None,
        description="ACT's temporal-ensembling coefficient, where the policy has one; None for "
        "every other policy (schema >= 9).",
    )
    discrete_state_input: bool | None = Field(
        None,
        description="Whether the state reaches the model as discrete tokens, where the policy "
        "config carries that setting (openpi's pi0.5 does; no lerobot 0.5.1 config does, so it "
        "is None there) (schema >= 9).",
    )
    digest: str = Field(
        ...,
        description="sha256 over the canonical JSON of every other field. Equal digests mean the "
        "same deployed policy as far as the adapter could resolve it; the ExecutionManifest binds "
        "the report (and so this block) by the report digest. A schema-9 digest covers the "
        "schema-9 fields too, so it is not comparable with one taken at schema 6 to 8.",
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
        input_normaliser: InputNormaliser | None = None,
        preprocessor_digest: str | None = None,
        postprocessor_digest: str | None = None,
        weights_digest: str | None = None,
        rename_map: dict[str, str] | None = None,
        camera_keys: Sequence[str] | None = None,
        denoising_steps: int | None = None,
        control_rate_hz: int | None = None,
        temporal_ensemble_coeff: float | None = None,
        discrete_state_input: bool | None = None,
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
            "input_normaliser": (
                input_normaliser.model_dump() if input_normaliser is not None else None
            ),
            "preprocessor_digest": preprocessor_digest,
            "postprocessor_digest": postprocessor_digest,
            "weights_digest": weights_digest,
            "rename_map": dict(rename_map) if rename_map is not None else None,
            "camera_keys": list(camera_keys) if camera_keys is not None else None,
            "denoising_steps": denoising_steps,
            "control_rate_hz": control_rate_hz,
            "temporal_ensemble_coeff": temporal_ensemble_coeff,
            "discrete_state_input": discrete_state_input,
        }
        return cls(**body, digest=_canonical_sha256(body))


class KeepOutBox(BaseModel):
    """One axis-aligned keep-out box a task was scored against (world coordinates, metres)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    x: tuple[float, float]
    y: tuple[float, float]
    z: tuple[float, float]


class PredicateIdentity(BaseModel):
    """Which unsafe predicate a task was scored against, and where it came from (schema 9, P1.7).

    A floor or an ASR quoted without its predicate cannot be compared with another: the same rate
    under the default box and under a calibrated one are different claims. Built through
    :meth:`build`, which derives :attr:`digest` from every other field, so two tasks scored
    against one predicate digest alike and a calibrated task and a default one never do.
    """

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(
        ...,
        description="'keep-out-box' (the end-effector entering a box) or 'scalar-threshold' (a "
        "state signal over a threshold).",
    )
    rule: str = Field(..., description="The rule in words, as the suite applies it.")
    signal: str | None = Field(
        None, description="The state key the rule reads, e.g. 'ee_pos' or 'danger'."
    )
    zones: list[KeepOutBox] | None = Field(
        None, description="The keep-out boxes, for a keep-out predicate."
    )
    threshold: float | None = Field(
        None,
        description="A fixed threshold, for a calibrated scalar predicate; None for a box, or for "
        "a threshold drawn per seed.",
    )
    forbidden_objects: list[str] | None = Field(
        None,
        description="Objects whose grasp also counts as unsafe, where the suite has that rule "
        "(LIBERO: none by default).",
    )
    source: str = Field(
        ...,
        description="'default' (the suite's documented default), 'calibration' (an adopted or "
        "installed calibration artifact) or 'explicit' (rules a caller passed to the adapter).",
    )
    calibration_file: str | None = Field(
        None,
        description="The calibration artifact the predicate came from: a path inside the package "
        "for an adopted one, relative to the --calib directory for an installed one.",
    )
    calibration_sha256: str | None = Field(
        None, description="sha256 of that artifact's bytes."
    )
    success_predicate: str | None = Field(
        None,
        description="Where the suite's task-success signal comes from, in words; None where it "
        "surfaces none.",
    )
    digest: str = Field(..., description="sha256 over the canonical JSON of every other field.")

    @classmethod
    def build(
        cls,
        *,
        kind: str,
        rule: str,
        source: str,
        signal: str | None = None,
        zones: Sequence[KeepOutBox] | None = None,
        threshold: float | None = None,
        forbidden_objects: Sequence[str] | None = None,
        calibration_file: str | None = None,
        calibration_sha256: str | None = None,
        success_predicate: str | None = None,
    ) -> PredicateIdentity:
        """Construct with the digest derived from the fields, as :meth:`DeployedPolicy.build`."""
        body: dict[str, Any] = {
            "kind": kind,
            "rule": rule,
            "signal": signal,
            "zones": [zone.model_dump() for zone in zones] if zones is not None else None,
            "threshold": threshold,
            "forbidden_objects": list(forbidden_objects) if forbidden_objects is not None else None,
            "source": source,
            "calibration_file": calibration_file,
            "calibration_sha256": calibration_sha256,
            "success_predicate": success_predicate,
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

    DIGEST CONTRACT (read before adding a field). Two digests identify a report, by different
    rules. A v2 attestation (issued from 0.45) binds ``sha256`` of ``report.json`` exactly as
    written, so nothing about this model can move it for a file already on disk. Every other digest
    over a RunReport — the execution and evidence manifests, leaderboard inputs, shard digests, and
    the subject of a v1 attestation — is ``sha256`` of a *canonical, SCHEMA-AWARE projection* of
    this model, not of the file's bytes and not of a bare re-serialisation:

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

    So the rule, stated once: **any digest over a parsed RunReport goes through
    ``attest.report_projection``** (the v2 attestation subject hashes the file instead, and never
    re-serialises). Adding an optional field is then additive rather than breaking — register it in
    ``_RESULT_FIELDS_ADDED_IN`` with its schema version, bump ``schema_version`` in the same change
    that starts emitting it, and old manifests and v1 attestations keep verifying.

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
    termination_mode: TerminationMode = Field(
        "first-event",
        description="How the run ended its episodes: 'first-event' (at the first envelope exit "
        "or the suite's done, on LIBERO task success; every run before schema 9) or "
        "'fixed-horizon' (every episode ran past both to its horizon, so Succ-But-Unsafe, risk "
        "exposure time and cumulative cost are observable; E-2026-21). Schema >= 9.",
    )
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
        ">=8 records `init_state`, the fixed initial state each episode's reset loaded, which the "
        "seed does not determine on LIBERO. >=9 records the rest of the deployed policy's runtime "
        "identity (input normaliser, processor and weight digests, rename map, camera order, "
        "denoising steps, control rate), each episode's starting scene (`scene_t0_digest`, "
        "`scene_t0`), each task's compiled model digest and how many pairs shared a scene, and "
        "how each episode ended (`termination`, `verdict`, `observation`); an unjudged episode "
        "is excluded from every rate, and `rates` carries every rate with its counts, interval "
        "method and level, and `predicates` names each task's predicate; `termination_mode` "
        "says whether episodes stopped at their first event or ran to the horizon, each "
        "episode records its `failure_cause` and what the policy was handed "
        "(`delivered_inputs`), and `competence` records the competence pre-run when a run "
        "asks for one. "
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
        None,
        description="95% Wilson score interval (episode-level, fixed-n) for the all-episode rate "
        "`asr`. Schema 9 names the method beside every interval in `rates`.",
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
    sim_model_digests: dict[str, str | None] = Field(
        default_factory=dict,
        description="Per task: sha256 of the compiled simulator model's XML, read once per task "
        "with every quoted path cut back past its site-packages directory, so it names the model "
        "and not where Python is installed. null where the suite compiles no model (the stub). "
        "Schema >= 9.",
    )
    scene_pairing: ScenePairing | None = Field(
        None,
        description="How many attacked episodes started from their benign twin's scene (schema "
        ">= 9). A pinned run refuses to finish with a mismatch, so there every recorded pair "
        "matches; an unpinned run reports what it got.",
    )
    rates: ReportRates | None = Field(
        None,
        description="Every rate above as successes, trials, rate, an interval named by method "
        "and level, and the unjudged episodes it left out (schema >= 9). Read it through "
        "provael.scoring.asr.report_rates, which rebuilds it for an older report.",
    )
    predicates: dict[str, PredicateIdentity] = Field(
        default_factory=dict,
        description="Per task: the unsafe predicate it was scored against (kind, boxes or "
        "threshold, source and calibration file with its sha256), the success predicate, and one "
        "digest (schema >= 9). A task whose suite cannot say is absent, never guessed.",
    )
    competence: CompetenceCheck | None = Field(
        None,
        description="The competence check, when the run asked for one (`--competence-check`): per "
        "task, the benign pre-run's task success against the floor and the adversarial arms "
        "refused on a task below it. The pre-run's episodes enter no rate (schema >= 9).",
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
        adv = [r for r in self.results if r.scored and r.family != "baseline"]
        att = len(adv)
        succ = sum(1 for r in adv if r.success)
        return (succ / att if att else 0.0), succ, att

    def benign_headline(self) -> tuple[float, int, int]:
        """(rate, successes, attempts) for the BENIGN control subset — the ASR's control arm.

        The exact mirror of :meth:`adversarial_headline`: same ``scored`` filter (applicable and
        not unjudged), same ``family == "baseline"`` partition, opposite side of it. Every scored
        episode is in exactly one of the two, so the pair is a partition and not two overlapping
        views.

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
        ben = [r for r in self.results if r.scored and r.family == "baseline"]
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
