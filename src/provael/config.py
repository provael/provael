# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Run configuration for a red-team evaluation.

``RunConfig`` is the single source of truth for a run: which policy and suite to
use, which attacks to apply, how many episodes, the base seed, the per-episode
horizon, and where to write reports. It is intentionally small and fully
declarative so a run can be reproduced from the config alone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, field_validator, model_validator


class RunConfig(BaseModel):
    """Declarative description of one red-team run."""

    model_config = ConfigDict(extra="forbid")

    policy: str = Field("stub", description="Registered policy name (e.g. 'stub', 'smolvla').")
    model: str | None = Field(
        None, description="Checkpoint override for the policy (e.g. a LIBERO-finetuned SmolVLA)."
    )
    rename_map: dict[str, str] | None = Field(
        None, description="Obs-key rename map forwarded to the policy (mirrors lerobot-eval)."
    )
    unnorm_key: str | None = Field(
        None,
        description="Action-unnormalization stats id for policies that need one (e.g. OpenVLA).",
    )
    suite: str = Field("stub", description="Registered suite name (e.g. 'stub').")
    attacks: list[str] = Field(
        default_factory=lambda: ["instruction"],
        description="Attack names or attack-family names. Families expand to their members.",
    )
    tasks: list[str] | None = Field(
        None,
        min_length=1,
        description="Subset of suite tasks to run. None means 'all tasks the suite exposes'. "
        "An EMPTY list is rejected rather than read as 'none': the runner's triple loop would "
        "never execute, and the report would still advertise `episodes`/`horizon` while carrying "
        "attempts=0 — a run that measured nothing reads as one that measured nothing unsafe.",
    )
    episodes: int = Field(
        10,
        ge=1,
        description="Total episodes per (task, attack) pair. With the default "
        "episodes_per_seed=1 this is also the number of distinct seeds, which is the historical "
        "behaviour and why the CLI treats --seeds and --episodes as aliases.",
    )
    episodes_per_seed: int = Field(
        1,
        ge=1,
        description="Repeats at the SAME seed. That is the same initial state only where the suite "
        "picks the state from the seed; on LIBERO lerobot's reset counter picks it unless the run "
        "pins it (E-2026-19). Default 1 preserves the original behaviour exactly.\n\n"
        "WHY THIS EXISTS. Until now `episodes` was the only knob and the runner did "
        "`seed = base + episode`, so an episode WAS a seed. That makes the per-(attack, seed) "
        "success rate 0 or 1 by construction, which means the seed-to-seed variance of a single "
        "attack is not computable from a report — the one quantity the robot-learning literature "
        "says matters most. OpenVLA publishes LIBERO-Object at 88.4% +/- 0.8% and two independent "
        "parties reproduced ~68% (openvla/openvla#282, #335, the latter still open): the quoted "
        "uncertainty was ~25x smaller than the reproduction gap because it described the wrong "
        "variance component.\n\n"
        "Repeats at a fixed seed isolate POLICY stochasticity; varying the seed isolates "
        "INITIAL-STATE variation. You need both to say which one your error bar describes. On a "
        "deterministic policy the repeats are identical by design and add nothing, which is the "
        "correct behaviour rather than a defect.",
    )
    seed: int = Field(0, ge=0, description="Base random seed for reproducibility.")
    pin_init_states: int | None = Field(
        None,
        ge=0,
        description="On a suite whose scenes come from a fixed list of N initial states (LIBERO), "
        "start the episode at seed s from state (pin_init_states + s) mod N, for every arm and "
        "repeat. None keeps the suite's own order, which on LIBERO is a reset counter the seed "
        "never reaches, so two arms at one seed start from different scenes. A suite without "
        "such a list refuses a pin. Each episode records the state it loaded (`init_state`), so "
        "the report shows the scenes either way and RunReport carries no field for the pin.",
    )
    init_states: dict[str, list[NonNegativeInt]] | None = Field(
        None,
        description="On a suite with a fixed list of initial states (LIBERO), the init-state "
        "indices to start each task's episodes from, per task: one per seed (seed index i starts "
        "from entry i, in every arm and repeat) or, in a run whose only arm is the benign "
        "baseline, one per episode. A run with any other arm must name one state per seed, so "
        "every arm at a seed starts from one scene. Exclusive with pin_init_states; the runner "
        "checks the lists against the run's tasks, seeds and arms before anything runs.",
    )
    horizon: int = Field(8, ge=1, description="Maximum timesteps per episode.")
    termination: Literal["first-event", "fixed-horizon"] = Field(
        "first-event",
        description="'first-event' (the default, and every run before it existed) stops an "
        "episode at its first envelope exit or at the suite's done, which on LIBERO is task "
        "success. 'fixed-horizon' runs every episode to `horizon` in every arm: an exit and a "
        "success both latch and the steps after them are still scored, so Succ-But-Unsafe and "
        "the dwell behind risk exposure time become observable (E-2026-21). A suite that cannot "
        "step past an event refuses it; the report records the mode (`termination_mode`).",
    )
    competence_check: int | None = Field(
        None,
        ge=1,
        description="Run this many benign episodes per task before the arms, at the seeds after "
        "the run's own, and refuse the adversarial arms on a task whose task success falls below "
        "`competence_floor`: an attack rate on a policy that cannot do the task unattacked "
        "measures nothing. The report records each task's pre-run and any refusal (`competence`); "
        "the pre-run's episodes enter no rate. None (the default) runs no check.",
    )
    competence_floor: float = Field(
        0.8,
        ge=0.0,
        le=1.0,
        description="The task success a task's competence pre-run must reach for its adversarial "
        "arms to run. Read only with `competence_check`.",
    )
    record_episode_errors: bool = Field(
        False,
        description="Record an exception from the simulator's step as an unjudged episode with "
        "its reason (termination 'error') instead of stopping the run. Off by default. Every rate "
        "excludes an unjudged episode and counts it beside the rate, so the run cannot shrink "
        "silently; a failure in reset still stops the run.",
    )
    defense: str | None = Field(
        None,
        description="Registered defense name applied as a pre-processing wrapper between the "
        "attack and the policy (e.g. 'instruction_canonicalization'). None runs undefended. The "
        "defense identity is recorded in the EXECUTION MANIFEST, not in report.json — adding a "
        "field to RunReport would move the attestation subject digest.",
    )
    query_budget: int | None = Field(
        None,
        ge=1,
        description="Per-episode policy-query budget for the optimized (search) attack family.",
    )
    out: Path = Field(
        default_factory=lambda: Path("runs/stub"), description="Output directory for reports."
    )
    accelerator: str | None = Field(
        None,
        description="D6: REQUESTED execution device — 'cpu' | 'cuda' | 'mps'. Forwarded to the "
        "policy factory as `device`; None lets the adapter keep its own default. The report "
        "records the device the adapter actually RESOLVED to "
        "(PolicyAdapter.resolved_device), which can differ if the adapter falls back. "
        "'tpu' is a reserved-but-unimplemented slot (ROADMAP §8 / D5).",
    )
    precision: str | None = Field(
        None,
        description="D6: compute-precision hint (e.g. 'fp32', 'bf16', 'fp16'); None lets the "
        "policy choose. Recorded into the report so a result says at what precision it ran.",
    )

    @field_validator("attacks")
    @classmethod
    def _attacks_non_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("at least one attack (or attack family) must be specified")
        return v

    @field_validator("init_states")
    @classmethod
    def _init_states_named(
        cls, v: dict[str, list[int]] | None
    ) -> dict[str, list[int]] | None:
        if v is not None and (not v or any(not states for states in v.values())):
            raise ValueError("init_states must name at least one state for every task it lists")
        return v

    @model_validator(mode="after")
    def _one_scene_chooser(self) -> RunConfig:
        """A pin and a named list both choose each episode's scene; a run takes one of them."""
        if self.init_states is not None and self.pin_init_states is not None:
            raise ValueError(
                "init_states and pin_init_states both choose each episode's starting scene; "
                "pass one of them"
            )
        return self

    @field_validator("accelerator")
    @classmethod
    def _accelerator_supported(cls, v: str | None) -> str | None:
        """Gate the device slot: known devices pass, 'tpu' raises NotImplementedError (D5/§8).

        Raising NotImplementedError (not ValueError) is deliberate — pydantic lets it propagate
        unchanged, so ``accelerator='tpu'`` surfaces the roadmap decision verbatim rather than a
        generic validation error. See ROADMAP §8 for the (both-required) revisit trigger.
        """
        if v is None:
            return v
        if v == "tpu":
            raise NotImplementedError(
                "accelerator='tpu' is a reserved-but-unimplemented slot (ROADMAP §8 / D5). "
                "Revisit trigger: TorchTPU GA AND third-party PyTorch VLA-class inference parity. "
                "Every current target ships a PyTorch cpu/cuda/mps path — use one. "
                "Rationale: https://provael.github.io/provael/accelerators/"
            )
        allowed = {"cpu", "cuda", "mps"}
        if v not in allowed:
            raise ValueError(
                f"unsupported accelerator {v!r}; expected one of {sorted(allowed)} "
                "(or 'tpu', which is an explicit NotImplementedError slot)"
            )
        return v
