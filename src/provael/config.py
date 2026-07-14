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
        None, description="Subset of suite tasks to run. None means 'all tasks the suite exposes'."
    )
    episodes: int = Field(
        10, ge=1, description="Episodes per (task, attack) pair. Episode i uses seed + i."
    )
    seed: int = Field(0, ge=0, description="Base random seed for reproducibility.")
    horizon: int = Field(8, ge=1, description="Maximum timesteps per episode.")
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
        description="D6: explicit execution device — 'cpu' | 'cuda' | 'mps'. None lets the policy "
        "choose. 'tpu' is a reserved-but-unimplemented slot (ROADMAP §8 / D5).",
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
                "Every current target ships a PyTorch cpu/cuda/mps path — use one."
            )
        allowed = {"cpu", "cuda", "mps"}
        if v not in allowed:
            raise ValueError(
                f"unsupported accelerator {v!r}; expected one of {sorted(allowed)} "
                "(or 'tpu', which is an explicit NotImplementedError slot)"
            )
        return v
