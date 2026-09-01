"""AI2 ``vla-evaluation-harness`` bridge — **registered scaffolding, never run**.

This module is the same honesty scope ``groot``, ``openvla`` and ``openpi`` state in
:data:`~provael.policies.registry.SCAFFOLDING_POLICIES`: it is registered and structurally
unit-tested, and **no benchmark has ever been run through it**. Nothing here may be presented as
suite coverage, and the ~18 benchmarks the harness exposes are not Provael's until one of them has
actually produced a run.

WHY IT IS SCAFFOLDING RATHER THAN AN ADAPTER. The blocker is not effort, it is the harness's public
surface. Provael scores :meth:`~provael.suites.base.SuiteAdapter.is_unsafe` on a per-step env
``State``; the harness returns per-episode success and nothing else. LIBERO's ``get_step_result``
returns ``{"success": ...}`` and its recorder is field-filtered to
``frozenset({"reward", "done", "success"})``. The end-effector pose exists inside the harness's
``make_obs`` and flows *outward to the model server* — it never reaches a caller. So the keep-out
predicate, the calibration signal and the EAI02/04/06 spatial predicates are all unreachable through
the published API. A bridge that shipped anyway would report task success and call it safety.

Full interface notes, with the three ways round it and their costs, in
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
    "The harness returns per-episode success only — LIBERO's get_step_result is {'success': ...} "
    "and its recorder is filtered to {reward, done, success} — so there is no per-step state for "
    "is_unsafe() to score, and the end-effector pose never leaves the harness's make_obs. "
    "See docs/studies/ai2-bridge-notes.md."
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
