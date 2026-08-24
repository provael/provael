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

    def seed(self, seed: int) -> int | None:  # noqa: B027
        """Seed this policy's OWN sampler for the coming episode; return the seed applied.

        WHAT WAS MISSING. The runner has always seeded the *environment* — ``suite.reset(task,
        seed)`` — and every episode records that seed. Nothing ever seeded the *policy*. A
        flow-matching head like SmolVLA's draws its noise from the ambient torch RNG in whatever
        state the process left it, so two runs at an identical config give different numbers and
        the leaderboard's own caveat says so: "one draw, not a constant". Two rows at the same
        commit were therefore not comparable, which is most of what a leaderboard is for.

        RETURNS WHAT WAS APPLIED, NOT WHAT WAS ASKED. Same discipline as
        :attr:`resolved_device`: an adapter that cannot seed returns ``None`` and the episode
        records ``policy_seed: null``, which is an honest "this was one draw". Returning the
        argument unconditionally would let every report claim a determinism no adapter delivered.

        The default does not seed, because most adapters have nothing to seed — the stub is pure
        numpy and deterministic by construction. An adapter that sets ``stochastic = True`` and
        does NOT override this is the bug, and `tests/test_policy_seeding.py` fails on it by name
        rather than leaving it to be noticed in a result file months later.
        """
        return None

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
