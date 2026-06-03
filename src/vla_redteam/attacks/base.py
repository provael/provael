"""Attack interface.

An :class:`Attack` perturbs the instruction (and optionally the observation) that
a policy receives, attempting to drive the policy into an unsafe state. Part 1 of
vla-redteam ships only the ``instruction`` family (templated text attacks). Other
families — optimised adversarial suffixes (GCG-style), visual perturbations, and
prompt-injection via the observation — are deliberately out of scope for Part 1.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from vla_redteam.types import Observation


class Attack(ABC):
    """Transforms ``(instruction, observation)`` into an adversarial variant."""

    #: Stable, human-readable identifier (also the registry key).
    name: str = "base"
    #: Attack family this attack belongs to (e.g. ``"instruction"``).
    family: str = "base"

    def applicable(self, observation: Observation) -> bool:
        """Whether this attack has a surface in the given suite's observation.

        Default True. Returning False marks the attack **not-applicable** for that suite
        (e.g. ``mcp_tool_desc`` has no MCP surface in a direct LIBERO loop); such episodes
        are excluded from the ASR denominator rather than faked.
        """
        return True

    @abstractmethod
    def perturb(self, instruction: str, observation: Observation) -> tuple[str, Observation]:
        """Return an adversarial ``(instruction, observation)`` pair.

        Implementations must be **deterministic**: given the same inputs they must
        always return the same output (any per-episode variation must be derived
        from values already present in ``observation``, e.g. its ``"seed"``).

        Args:
            instruction: The base (benign) task instruction.
            observation: The current observation dict.

        Returns:
            ``(adversarial_instruction, observation)``. Instruction-family attacks
            return the observation unchanged.
        """
