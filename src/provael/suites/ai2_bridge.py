# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""AI2 ``vla-evaluation-harness`` bridge — **registered scaffolding, never run**.

This module is the same honesty scope ``groot``, ``openvla`` and ``openpi`` state in
:data:`~provael.policies.registry.SCAFFOLDING_POLICIES`: it is registered and structurally
unit-tested, and **no benchmark has ever been run through it**. Nothing here may be presented as
suite coverage, and the ~18 benchmarks the harness exposes are not Provael's until one of them has
actually produced a run.

WHY IT IS SCAFFOLDING RATHER THAN AN ADAPTER. Provael scores
:meth:`~provael.suites.base.SuiteAdapter.is_unsafe` on a per-step env ``State``, and this module
was written for a caller-side route: the harness's ``get_step_result`` returns ``{"success": ...}``,
so a bridge built that way would report task success and call it safety. The premise that the pose
could not be had was wrong, and the harness maintainer said so
(allenai/vla-evaluation-harness#127): with ``send_state`` the end-effector state reaches the
model-server side every step, and ``StepRecorder`` is the public hook for a second writer. The
supported route is a model-server proxy, roadmap work after the calibrated predicate and the
hardware run, and not this adapter.

Full interface notes, and the correction at the top of them, in
``docs/studies/ai2-bridge-notes.md``.

WHAT IS ALREADY KNOWN TO WORK. The benign control arm — the thing this project will not publish a
rate without — *is* expressible: work items are a deterministic ``task x episode`` enumeration, so
the same benchmark run twice at one seed visits the same initial states. That answer is positive and
recorded; it is the predicate, not the control, that blocks this.

The harness is on PyPI as **``vla-eval``** (``vla-evaluation-harness`` is not a package name).
"""

from __future__ import annotations

from typing import NoReturn

from provael.suites.base import SuiteAdapter
from provael.types import Action, Observation, State

#: PyPI distribution name. Recorded because the obvious guess is wrong and would send a reader to a
#: 404: the repo is ``vla-evaluation-harness``, the package is ``vla-eval``, the import
#: ``vla_eval``.
HARNESS_DISTRIBUTION = "vla-eval"

#: Benchmarks the harness exposed at v0.4.0 — the figure the roadmap's "~18" refers to. Read from
#: the tag, not the README. v0.5.0 adds ``robocasa365`` and ``robodojo``. Listed so the count is
#: checkable rather than restated, and NOT as a claim that Provael runs any of them.
HARNESS_V040_BENCHMARKS: tuple[str, ...] = (
    "behavior1k", "calvin", "duobench", "kinetix", "libero", "libero_mem", "libero_plus",
    "libero_pro", "maniskill2", "mikasa", "molmospaces", "rlbench", "robocasa", "robocerebra",
    "robomme", "robotwin", "simpler", "vlabench",
)

_UNBUILT = (
    "the AI2 vla-evaluation-harness bridge is registered scaffolding and has never been run. "
    "It was written against a reading the harness maintainer corrected in "
    "allenai/vla-evaluation-harness#127: with send_state the end-effector state reaches the "
    "model-server side every step and StepRecorder is the hook for a second writer, so the "
    "supported route is a model-server proxy (roadmap, after the calibrated predicate and the "
    "hardware run), not this caller-side adapter. See docs/studies/ai2-bridge-notes.md."
)


def _unbuilt() -> NoReturn:
    raise NotImplementedError(_UNBUILT)


class Ai2BridgeSuite(SuiteAdapter):
    """Placeholder for the harness bridge. Every method raises.

    It is registered so ``provael list-suites`` shows it as scaffolding — an unbuilt bridge that a
    reader can see is unbuilt is more useful than one that is absent and rediscovered. It raises
    rather than degrading to a fixture, because a suite that quietly returns plausible values is how
    an unbuilt path produces a number.
    """

    name = "ai2_bridge"
    calibration_kind = "spatial"

    def tasks(self) -> list[str]:
        """Would flatten ``Benchmark.get_tasks()``; unbuilt."""
        _unbuilt()

    def reset(self, task: str, seed: int) -> Observation:
        """Unbuilt. Note the harness has no per-episode ``seed=`` on its runner API."""
        _unbuilt()

    def step(self, action: Action) -> tuple[Observation, bool, State]:
        """Unbuilt. The harness surfaces no per-step ``State`` to return here."""
        _unbuilt()

    def is_unsafe(self, state: State) -> bool:
        """Unbuilt — and the blocker: the harness provides no state to evaluate."""
        _unbuilt()
