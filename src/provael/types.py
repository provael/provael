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
from pydantic import BaseModel, Field

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

    attempts: int
    successes: int
    asr: float = Field(..., description="Overall Attack Success Rate — the headline stat.")
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
    results: list[AttackResult] = Field(default_factory=list)

    def headline(self) -> str:
        """Single-line human summary of the headline ASR (± per-seed std for real policies)."""
        pct = 100.0 * self.asr
        base = f"Attack Success Rate (ASR): {pct:.1f}% ({self.successes}/{self.attempts})"
        if self.stochastic:
            return f"{base} ± {100.0 * self.asr_std:.1f}% (seeded, model-stochastic)"
        return base
