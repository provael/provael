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
from typing import TYPE_CHECKING, Any

from provael.scoring.action import action_unsafe as _action_unsafe
from provael.scoring.backdoor import backdoor_unsafe as _backdoor_unsafe
from provael.types import Action, Observation, State, SuiteFeatures

if TYPE_CHECKING:
    from provael.calibration import Calibration


class SuiteAdapter(ABC):
    """A simulated environment with a defined unsafe outcome."""

    #: Stable, human-readable identifier (also the registry key).
    name: str = "base"
    #: How this suite's predicate is calibrated: ``"scalar"`` (a thresholded signal, the
    #: stub) or ``"spatial"`` (an end-effector keep-out region, LIBERO). See
    #: :mod:`provael.calibration`.
    calibration_kind: str = "scalar"

    def features(self) -> SuiteFeatures | None:
        """Env metadata for policies that need it; ``None`` when not applicable.

        The stub returns ``None``; the LIBERO suite returns a populated
        :class:`~provael.types.SuiteFeatures` so a real policy can wire itself to
        the env. Exchanged once per run via :meth:`PolicyAdapter.set_features`.
        """
        return None

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
        """Return the **default (uncalibrated)** unsafe predicate for ``state``."""

    # -- calibration hooks (v0.4) -------------------------------------------
    # Backward-compatible: with no calibration set, evaluate_unsafe() == is_unsafe().

    def calibration_signal(self, state: State) -> float | list[float] | None:
        """Per-step signal a calibrator reads from ``state``.

        Default (``scalar`` suites): the ``"danger"`` level. Spatial suites override this
        to return the end-effector position. ``None`` steps are ignored when fitting.
        """
        danger = state.get("danger")
        return None if danger is None else float(danger)

    def set_calibration(self, calibrations: dict[str, Calibration]) -> None:
        """Install per-task calibrations (keyed by task id) for :meth:`evaluate_unsafe`."""
        self._calibrations: dict[str, Calibration] = dict(calibrations)

    def calibration_for(self, task: str) -> Calibration | None:
        """The installed calibration for ``task``, or ``None``."""
        return getattr(self, "_calibrations", {}).get(task)

    def action_unsafe(self, state: State) -> bool:
        """The EAI04 action-space-integrity predicate (freeze / trajectory hijack).

        Reads the action-integrity signals the suite surfaces into ``state`` (commanded
        motion + heading); returns ``False`` for any suite/state that surfaces none, so
        OR-ing it into :meth:`evaluate_unsafe` is a no-op there. See
        :func:`provael.scoring.action.action_unsafe`.
        """
        return _action_unsafe(state)

    def backdoor_unsafe(self, state: State) -> bool:
        """The EAI03 backdoor-screen predicate (objective-decoupled trigger activation).

        Reads the hidden-objective activation flag the suite surfaces into ``state``; returns
        ``False`` for any suite/state that surfaces none, so OR-ing it into :meth:`evaluate_unsafe`
        is a no-op there. See :func:`provael.scoring.backdoor.backdoor_unsafe`.
        """
        return _backdoor_unsafe(state)

    def evaluate_unsafe(self, state: State) -> bool:
        """Unsafe predicate the runner calls.

        Combines the **hazard** predicate — the calibrated one if a calibration is installed
        for this state's task, else the default :meth:`is_unsafe` — with the EAI04
        action-space-integrity predicate (:meth:`action_unsafe`) and the EAI03 backdoor-screen
        predicate (:meth:`backdoor_unsafe`). The action and backdoor axes are always OR-ed in
        (calibration tunes the hazard axis only), and are a no-op on suites that surface no
        action / backdoor signal, so existing danger-only runs are unchanged.
        """
        calibration = self.calibration_for(str(state.get("task", "")))
        hazard = (
            bool(calibration.is_unsafe(state)) if calibration is not None
            else self.is_unsafe(state)
        )
        return hazard or self.action_unsafe(state) or self.backdoor_unsafe(state)

    # Optional hook kept out of the abstract surface so simple suites need not
    # implement it; the runner reads the base instruction from the reset obs.
    def metadata(self) -> dict[str, Any]:
        """Static, JSON-serialisable metadata describing the suite (optional)."""
        return {"name": self.name}
