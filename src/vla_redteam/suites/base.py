"""Simulation suite interface.

A :class:`SuiteAdapter` wraps a (simulated) environment that a policy acts in. It
exposes a Gym-like ``reset`` / ``step`` loop plus an :meth:`is_unsafe` predicate
that defines what "the attack succeeded" means for that environment. Observations
returned by ``reset``/``step`` are plain dicts; by convention they carry an
``"instruction"`` key holding the task's natural-language goal, which the runner
feeds to attacks and the policy.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from vla_redteam.types import Action, Observation, State


class SuiteAdapter(ABC):
    """A simulated environment with a defined unsafe outcome."""

    #: Stable, human-readable identifier (also the registry key).
    name: str = "base"

    @abstractmethod
    def tasks(self) -> list[str]:
        """Return the list of task identifiers this suite exposes."""

    @abstractmethod
    def reset(self, task: str, seed: int) -> Observation:
        """Reset to the start of ``task`` with the given ``seed`` and return obs.

        The returned observation must include an ``"instruction"`` key holding the
        task's base (benign) natural-language goal.
        """

    @abstractmethod
    def step(self, action: Action) -> tuple[Observation, bool, State]:
        """Advance one timestep.

        Returns:
            ``(observation, done, state)`` where ``state`` is the env-state dict
            that :meth:`is_unsafe` consumes. ``done`` is True when the episode
            should terminate (e.g. an unsafe state was reached, or a step cap hit).
        """

    @abstractmethod
    def is_unsafe(self, state: State) -> bool:
        """Return True if ``state`` represents an unsafe / attack-successful outcome."""

    # Optional hook kept out of the abstract surface so simple suites need not
    # implement it; the runner reads the base instruction from the reset obs.
    def metadata(self) -> dict[str, Any]:
        """Static, JSON-serialisable metadata describing the suite (optional)."""
        return {"name": self.name}
