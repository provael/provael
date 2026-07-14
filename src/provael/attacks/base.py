"""Attack interface.

An :class:`Attack` perturbs the instruction (and optionally the observation) that a
policy receives, attempting to drive the policy into an unsafe state. Three families
ship today: ``instruction`` (templated text reframings), ``visual`` (camera-image
perturbations), and ``injection`` (indirect / embodied prompt injection). Optimised
adversarial suffixes (GCG-style) and transferable pixel attacks remain deferred (see
CHANGELOG ``[Unreleased]``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from provael.types import Observation


class Attack(ABC):
    """Transforms ``(instruction, observation)`` into an adversarial variant."""

    #: Stable, human-readable identifier (also the registry key).
    name: str = "base"
    #: Attack family this attack belongs to (e.g. ``"instruction"``).
    family: str = "base"
    #: Embodied AI Security Top-10 risk id this attack maps to (e.g. ``"EAI01"``).
    #: ``None`` for the baseline control, which is not an attack technique.
    eai_id: str | None = None
    #: Human-readable name of that risk (mirrors :data:`provael.eai.CATALOG`).
    eai_name: str | None = None
    #: INV-4 threat-model metadata: the attacker's access class, one of
    #: ``"white-box-gradient"`` / ``"black-box-query"`` / ``"in-scene-physical"``.
    #: ``None`` where not asserted (e.g. the stub-scaffolding families that make no
    #: real-access claim). Recorded on every :class:`~provael.types.AttackResult` so a
    #: result is self-describing and no freeze/token attack is silently assumed to transfer.
    attacker_access: str | None = None
    #: INV-4 threat-model metadata: the policy action-head class the attack was measured
    #: against — ``"token"`` (discrete autoregressive) or ``"flow"`` (flow-matching). ``None``
    #: where not asserted. A stub-only attack does not claim a head class; a real-transfer
    #: attack records the one it actually ran against (see ROADMAP D3/INV-4).
    action_head_class: str | None = None

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
