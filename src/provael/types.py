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

from dataclasses import dataclass
from typing import Any

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
        None, description="Benign FPR achieved on the calibration holdout split."
    )
    n_benign: int | None = Field(None, description="Benign rollouts used to calibrate.")


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
    """The full, deterministic result of a red-team run."""

    tool_version: str = Field(..., description="provael.__version__ that produced this report.")
    policy: str
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
        "carries the adversarial_* fields (the benign control excluded by role) and the roles map.",
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
        allep = (
            f"all-episode observed-unsafe {100.0 * self.asr:.1f}% "
            f"({self.successes}/{self.attempts})"
        )
        return f"{adv} · {allep}"
