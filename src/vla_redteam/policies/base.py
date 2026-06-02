"""Policy adapter interface.

A :class:`PolicyAdapter` wraps anything that maps an observation + instruction to
an action vector: a deterministic stub, or a real VLA policy such as SmolVLA loaded
through LeRobot. The interface is intentionally tiny so new backends are cheap to
add and so the rest of the engine never depends on a specific model framework.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from vla_redteam.types import Action, Observation


class PolicyAdapter(ABC):
    """Maps ``(observation, instruction)`` to an action vector."""

    #: Stable, human-readable identifier (also the registry key).
    name: str = "base"

    @abstractmethod
    def load(self) -> None:
        """Load any weights / processors. Must be called once before :meth:`act`.

        Adapters that need heavy or optional dependencies (e.g. torch, lerobot)
        should perform their imports here and raise a clear, actionable error if a
        dependency is missing — never at module import time.
        """

    @abstractmethod
    def act(self, observation: Observation, instruction: str) -> Action:
        """Return the action the policy takes given the observation and instruction.

        Args:
            observation: The current observation dict from the suite.
            instruction: The (possibly adversarial) natural-language instruction.

        Returns:
            A 1-D ``numpy`` float array — the action vector.
        """
