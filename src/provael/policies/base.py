"""Policy adapter interface.

A :class:`PolicyAdapter` wraps anything that maps an observation + instruction to
an action vector: a deterministic stub, or a real VLA policy such as SmolVLA loaded
through LeRobot. The interface is intentionally tiny so new backends are cheap to
add and so the rest of the engine never depends on a specific model framework.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from provael.types import Action, Observation, SuiteFeatures


class PolicyAdapter(ABC):
    """Maps ``(observation, instruction)`` to an action vector."""

    #: Stable, human-readable identifier (also the registry key).
    name: str = "base"
    #: True if inference is model-stochastic (reports are seeded but not byte-identical).
    #: The deterministic stub is False; real VLA policies are True.
    stochastic: bool = False
    #: The device this adapter ACTUALLY loaded onto, set during :meth:`load` (``"cuda"`` / ``"cpu"``
    #: / ``"mps"``). ``None`` means "not reported": the deterministic stub leaves it None because it
    #: is pure numpy and has no device to speak of.
    #:
    #: :func:`provael.runner.run` records this resolved value in preference to the *requested*
    #: :attr:`~provael.config.RunConfig.accelerator`, because an adapter may legitimately fall back
    #: (a CUDA request on a CPU-only host). Recording the request as though it were the outcome
    #: makes the report assert something that never happened.
    resolved_device: str | None = None
    #: The compute precision this adapter actually used (e.g. ``"bf16"``), set during :meth:`load`.
    resolved_precision: str | None = None
    #: INV-4 threat-model metadata: this policy's action-head class — ``"token"`` (discrete
    #: autoregressive) or ``"flow"`` (flow-matching). ``None`` where not asserted.
    #:
    #: It belongs here, not on the attack. An attack cannot know which head it is running against:
    #: the same patch search hits a flow head on SmolVLA and a token head on OpenVLA, so a constant
    #: on the attack class records a property of whichever policy the author had in mind. The
    #: runner prefers this value when stamping :class:`~provael.types.AttackResult`, so a result is
    #: self-describing about the head it actually ran against.
    action_head_class: str | None = None

    def set_features(self, features: SuiteFeatures) -> None:  # noqa: B027
        """Receive the suite's observation/action features (called once before ``load``).

        Intentionally a non-abstract no-op default: policies that don't need env metadata
        (e.g. the stub) ignore it. Real adapters (e.g. SmolVLA on LIBERO) override it.
        """

    def reset(self) -> None:  # noqa: B027
        """Reset per-episode policy state (e.g. an action-chunk queue).

        Intentionally a non-abstract no-op default; stateful policies override it.
        """

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
