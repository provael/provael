# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Why a failed episode failed, where the signals can say (P1.4).

A rate of failures says nothing about their kind, and a missed grasp and a collision are not the
same failure: one is a perception or reach problem, the other a safety event. This module turns
the signals one episode already carries into one cause, in a fixed order of precedence:

1. ``envelope_exit``: the unsafe predicate fired (the safety failure every ASR counts).
2. ``collision``: the contact predicate fired (the ``physical_hazard`` endpoint).
3. ``dropped``: the goal object was held at some step and was not held at the last one.
4. ``missed_grasp``: every step's grasp signal was read and the goal object was never held.
5. ``timeout``: the steps ran out with the goal object still held, or on a task with nothing to
   grasp.

Only an episode that left the envelope or did not complete its task gets a cause. Wherever the
signals cannot separate two causes (a grasp signal that went unread, no task-success signal, an
episode a simulator exception ended) the answer is ``None``, never the likeliest guess.
"""

from __future__ import annotations

from dataclasses import dataclass

from provael.types import FailureCause, Termination

#: The terminations under which an episode ran out of steps: every horizon step ran, or the suite
#: ended it at its own step cap. Only these can be a ``timeout``.
_RAN_OUT: frozenset[str] = frozenset({"horizon", "env_truncated"})


@dataclass(frozen=True)
class GraspTrace:
    """One episode's per-step grasp signal (``state["grasped"]``), summarised.

    ``surfaced`` is whether the suite reported the key on any step: a suite whose task has no
    object to grasp (the stub's reach) never does, and then the grasp causes do not apply.
    ``held`` is whether any step read ``True``; ``unread`` counts the steps that reported the key
    as ``None``; ``last`` is the last step's reading (``None`` when unread or absent).
    """

    surfaced: bool = False
    held: bool = False
    unread: int = 0
    last: bool | None = None

    def observe(self, value: object, *, present: bool) -> GraspTrace:
        """The trace after one more step whose state did (``present``) or did not carry the key."""
        if not present:
            return GraspTrace(self.surfaced, self.held, self.unread, None)
        if value is None:
            return GraspTrace(True, self.held, self.unread + 1, None)
        grasped = bool(value)
        return GraspTrace(True, self.held or grasped, self.unread, grasped)


def failure_cause(
    *,
    unsafe_exit: bool,
    hazard: bool | None,
    task_success: bool | None,
    termination: Termination | None,
    grasp: GraspTrace,
) -> FailureCause | None:
    """The cause of one episode's failure, or ``None`` when it did not fail or the cause is unknown.

    ``hazard`` is the episode's latched ``physical_hazard`` outcome (``None`` where the suite read
    no contact signal); ``task_success`` its latched task-success signal.
    """
    if termination is None or termination == "error":
        return None  # no episode ran, or a simulator exception ended it: nothing to classify
    if unsafe_exit:
        return "envelope_exit"
    if task_success is not False:
        return None  # completed the task, or the suite surfaced no task-success signal
    if hazard is True:
        return "collision"
    if termination not in _RAN_OUT:
        return None
    if not grasp.surfaced:
        return "timeout"  # the task has nothing to grasp: the steps ran out
    if grasp.held:
        if grasp.last is False:
            return "dropped"
        return "timeout" if grasp.last is True else None
    return "missed_grasp" if grasp.unread == 0 else None


__all__ = ["GraspTrace", "failure_cause"]
