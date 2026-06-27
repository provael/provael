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


class ASRStat(BaseModel):
    """Attack-success-rate statistics for a slice of results."""

    attempts: int = Field(..., description="Number of episodes in this slice.")
    successes: int = Field(..., description="Number of episodes that reached an unsafe state.")
    asr: float = Field(..., description="successes / attempts, or 0.0 when attempts == 0.")


class EaiTag(BaseModel):
    """Embodied AI Security Top-10 risk an attack maps to (see :mod:`provael.eai`)."""

    id: str = Field(..., description="Risk id, e.g. 'EAI01'.")
    name: str = Field(..., description="Human-readable risk name.")


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
