"""Run configuration for a red-team evaluation.

``RunConfig`` is the single source of truth for a run: which policy and suite to
use, which attacks to apply, how many episodes, the base seed, the per-episode
horizon, and where to write reports. It is intentionally small and fully
declarative so a run can be reproduced from the config alone.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
        description="Repeats at the SAME seed, i.e. the same initial state. Default 1 preserves "
        "the original behaviour exactly.\n\n"
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
    horizon: int = Field(8, ge=1, description="Maximum timesteps per episode.")
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
