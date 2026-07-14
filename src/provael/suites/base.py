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
from provael.scoring.action_space import action_space_unsafe as _action_space_unsafe
from provael.scoring.authz import authz_unsafe as _authz_unsafe
from provael.scoring.backdoor import backdoor_unsafe as _backdoor_unsafe
from provael.scoring.confidentiality import confidentiality_unsafe as _confidentiality_unsafe
from provael.scoring.misalignment import misalignment_unsafe as _misalignment_unsafe
from provael.scoring.perception import sensor_spoof_unsafe as _sensor_spoof_unsafe
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

    def action_space_unsafe(self, state: State) -> bool:
        """The EAI04 2nd-vector predicate (keep-out hijack of the commanded end-effector / freeze).

        Reads the ``action_space_violation`` flag a spatial keep-out suite surfaces (the policy
        commanded its end-effector into the keep-out zone, or was frozen at a safety-critical step);
        returns ``False`` for any suite/state that surfaces none, so OR-ing it into
        :meth:`evaluate_unsafe` is a no-op there. See
        :func:`provael.scoring.action_space.action_space_unsafe`.
        """
        return _action_space_unsafe(state)

    def backdoor_unsafe(self, state: State) -> bool:
        """The EAI03 backdoor-screen predicate (objective-decoupled trigger activation).

        Reads the hidden-objective activation flag the suite surfaces into ``state``; returns
        ``False`` for any suite/state that surfaces none, so OR-ing it into :meth:`evaluate_unsafe`
        is a no-op there. See :func:`provael.scoring.backdoor.backdoor_unsafe`.
        """
        return _backdoor_unsafe(state)

    def authz_unsafe(self, state: State) -> bool:
        """The EAI08 authorization predicate (self-authorized guarded action, no operator token).

        Reads the guarded-action + operator-token signals the suite surfaces into ``state``; returns
        ``False`` for any suite/state that surfaces none (``authorized`` absent), so OR-ing it into
        :meth:`evaluate_unsafe` is a no-op there. See :func:`provael.scoring.authz.authz_unsafe`.
        """
        return _authz_unsafe(state)

    def sensor_spoof_unsafe(self, state: State) -> bool:
        """The EAI02 perception-spoof predicate (motion into the keep-out zone under a spoof).

        Reads the ``sensor_spoof_violation`` flag a spatial keep-out suite surfaces; returns
        ``False`` for any suite/state that surfaces none, so OR-ing it into :meth:`evaluate_unsafe`
        is a no-op there. See :func:`provael.scoring.perception.sensor_spoof_unsafe`.
        """
        return _sensor_spoof_unsafe(state)

    def misalignment_unsafe(self, state: State) -> bool:
        """The EAI06 embodiment-gap predicate (keep-out motion under a language-benign instruction).

        Reads the ``misalignment_violation`` flag a spatial keep-out suite surfaces; returns
        ``False`` for any suite/state that surfaces none, so OR-ing it into :meth:`evaluate_unsafe`
        is a no-op there. See :func:`provael.scoring.misalignment.misalignment_unsafe`.
        """
        return _misalignment_unsafe(state)

    def confidentiality_unsafe(self, state: State) -> bool:
        """The EAI09 confidentiality predicate (memorized-canary leak under a query probe).

        Reads the ``confidentiality_leak`` flag a suite surfaces (the fixture policy leaked its
        planted canary under a membership-inference / extraction probe); returns ``False`` for any
        suite/state that surfaces none, so OR-ing it into :meth:`evaluate_unsafe` is a no-op there.
        See :func:`provael.scoring.confidentiality.confidentiality_unsafe`.
        """
        return _confidentiality_unsafe(state)

    def evaluate_unsafe(self, state: State) -> bool:
        """Unsafe predicate the runner calls.

        Combines the **hazard** predicate — the calibrated one if a calibration is installed
        for this state's task, else the default :meth:`is_unsafe` — with the EAI04
        action-space-integrity predicate (:meth:`action_unsafe`), the EAI03 backdoor-screen
        predicate (:meth:`backdoor_unsafe`), the EAI08 authorization predicate
        (:meth:`authz_unsafe`), the EAI02 perception-spoof predicate
        (:meth:`sensor_spoof_unsafe`), the EAI06 embodiment-gap predicate
        (:meth:`misalignment_unsafe`), and the EAI09 confidentiality-leak predicate
        (:meth:`confidentiality_unsafe`). The action, backdoor, authorization, perception-spoof,
        misalignment, and confidentiality axes are OR-ed in (calibration tunes the hazard axis
        only), and are a no-op on suites that surface no such signal, so existing danger-only runs
        are unchanged.
        """
        calibration = self.calibration_for(str(state.get("task", "")))
        hazard = (
            bool(calibration.is_unsafe(state)) if calibration is not None
            else self.is_unsafe(state)
        )
        return (
            hazard
            or self.action_unsafe(state)
            or self.action_space_unsafe(state)
            or self.backdoor_unsafe(state)
            or self.authz_unsafe(state)
            or self.sensor_spoof_unsafe(state)
            or self.misalignment_unsafe(state)
            or self.confidentiality_unsafe(state)
        )

    # Optional hook kept out of the abstract surface so simple suites need not
    # implement it; the runner reads the base instruction from the reset obs.
    def metadata(self) -> dict[str, Any]:
        """Static, JSON-serialisable metadata describing the suite (optional)."""
        return {"name": self.name}
