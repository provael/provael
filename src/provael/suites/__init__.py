"""Simulation suites and a small name -> suite factory.

The ``stub`` suite is always available (pure CPU, no deps). The ``libero`` suite wraps
a real LeRobot LIBERO environment; constructing it is cheap and never imports lerobot
(the optional dependency is only touched in ``reset``/``step``, which raise a clear,
actionable error if the ``[lerobot]`` extra is absent).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from provael.suites.ai2_bridge import Ai2BridgeSuite
from provael.suites.base import SuiteAdapter
from provael.suites.humanoid import HumanoidSuite
from provael.suites.reach import ReachSuite
from provael.suites.stub import StubSuite


def _make_libero(tasks: Sequence[str] | None = None) -> SuiteAdapter:
    # Imported here (not at module top) only for symmetry; the adapter module itself
    # imports no optional deps at module scope, so this stays CPU-safe either way.
    from provael.suites.libero import LiberoSuiteAdapter, suite_and_ids_from_tasks

    if not tasks:
        return LiberoSuiteAdapter()
    task_suite, task_ids = suite_and_ids_from_tasks(tasks)
    return LiberoSuiteAdapter(task_suite=task_suite, task_ids=task_ids)


def _make_metaworld() -> SuiteAdapter:
    from provael.suites.metaworld import MetaworldSuiteAdapter

    return MetaworldSuiteAdapter()


#: Registry of suite factories keyed by name. ``stub`` (scalar), ``reach`` (spatial), and
#: ``humanoid`` (whole-body / locomotion, spatial) are pure-CPU; ``libero`` and ``metaworld`` wrap
#: real simulators behind the ``[lerobot]`` extra.
SUITES: dict[str, Callable[[], SuiteAdapter]] = {
    "stub": StubSuite,
    "reach": ReachSuite,
    "humanoid": HumanoidSuite,
    "libero": _make_libero,
    "metaworld": _make_metaworld,
    "ai2_bridge": Ai2BridgeSuite,
}

#: suite name -> why it is scaffolding rather than a runnable suite. Mirrors
#: :data:`~provael.policies.registry.SCAFFOLDING_POLICIES` deliberately: a suite listed here is
#: registered and structurally unit-tested, but **no benchmark has ever been run through it**, so
#: nothing may present it as coverage. The policy side learned in 0.26.0 that this must be
#: DECLARED rather than probed for on the filesystem — ``docs/`` and ``results/`` are not packaged,
#: so a probe answers differently in a checkout and in a wheel, and it fails toward "measured".
SCAFFOLDING_SUITES: dict[str, str] = {
    "ai2_bridge": (
        "scaffolding: the AI2 harness returns per-episode success only — no per-step state for "
        "is_unsafe() and no end-effector pose reaches a caller; no benchmark has been run here"
    ),
}

#: Suites that are implemented and runnable from the Python API but cannot complete a run from
#: the CLI as shipped. Rendered in ``list-suites`` and ``doctor`` beside the suite so "runnable" is
#: never read as "one command away". Meta-World: the adapter refuses LIBERO's default keep-out box
#: because it lies behind the Sawyer arm (``MetaworldSuiteAdapter._ensure_zone_is_reachable``), the
#: CLI has no option to pass another zone, and no Meta-World calibration is committed — so
#: ``--suite metaworld`` raises at reset until a zone derived from the suite's own benign envelope
#: is supplied in code.
SUITE_GATING_NOTES: dict[str, str] = {
    "metaworld": (
        "runnable from the Python API with a keep_out_zone derived from the suite's benign "
        "envelope; from the CLI it raises at reset (no zone option, no committed calibration)"
    ),
}


def suite_gating_note(name: str) -> str | None:
    """Why a runnable suite still cannot complete a CLI run, or ``None`` if it can."""
    return SUITE_GATING_NOTES.get(name)


#: Status label rendered for a scaffolded suite. Kept as a constant so the CLI, the tests and any
#: future emitter say the same words, exactly as ``STATUS_SCAFFOLDING`` does for policies.
STATUS_SCAFFOLDING = "scaffolding — no benchmark ever run"

#: Suites that require the optional ``[lerobot]`` extra (and a real simulator).
REQUIRES_LEROBOT: frozenset[str] = frozenset({"libero", "metaworld"})

#: Suites that are deterministic in-process **fixtures**, not real simulators — declared by the
#: suite classes themselves (``SuiteAdapter.is_fixture``) rather than name-matched here, so adding
#: a fixture suite cannot silently earn it a real-evidence label. Read by
#: :func:`provael.evidence.classify_run`: a run on a fixture is never ``real-episode``, because a
#: pure-arithmetic environment embodies nothing regardless of which policy drives it.
FIXTURE_SUITES: frozenset[str] = frozenset(
    name for name, factory in SUITES.items() if getattr(factory, "is_fixture", False)
)


#: Suite kind labels rendered by ``list-suites``. A fixture and a simulator produce numbers that
#: mean different things — the first is deterministic arithmetic that embodies nothing, the second
#: is a physics rollout — so the board, the evidence classifier and the CLI all name the difference
#: in the same words rather than leaving a reader to infer it from the suite's name.
KIND_FIXTURE = "CPU fixture"
KIND_SIMULATOR = "real simulator"


def available_suites() -> list[str]:
    """Names of all registered suites."""
    return sorted(SUITES)


def suite_kind(name: str) -> str:
    """Whether ``name`` is a deterministic CPU fixture or a real simulator.

    Read from :data:`FIXTURE_SUITES`, which the suite classes declare themselves via
    ``SuiteAdapter.is_fixture`` — so a new fixture suite cannot earn a "real simulator" label by
    being absent from a hand-maintained list here.
    """
    return KIND_FIXTURE if name in FIXTURE_SUITES else KIND_SIMULATOR


def suite_scaffolding_note(name: str) -> str | None:
    """Why ``name`` is scaffolding rather than a runnable suite, or ``None`` if it is real.

    :func:`suite_is_ready` answers "is the declared dependency importable here", which is a strictly
    weaker claim than "this suite has been run". Both are surfaced by ``list-suites`` so a reader is
    never told a suite is ready when all that was verified is an import — the same distinction
    :func:`provael.policies.registry.policy_scaffolding_note` exists to keep.
    """
    return SCAFFOLDING_SUITES.get(name)


def suite_is_ready(name: str) -> bool:
    """Whether ``name`` can run in the current environment right now."""
    if name in SCAFFOLDING_SUITES:
        return False  # importable is not runnable: nothing has ever been driven through it
    if name in REQUIRES_LEROBOT:
        import importlib.util

        return importlib.util.find_spec("lerobot") is not None
    return name in SUITES


#: Suites whose construction depends on WHICH tasks a run asks for. LIBERO is four task suites
#: behind one adapter (``libero_object``, ``libero_spatial``, ``libero_goal``, ``libero_10``), and
#: the adapter is built for exactly one of them. Until 14 September 2026 the CLI always built the
#: default (``libero_object``) and :meth:`~provael.suites.libero.LiberoSuiteAdapter.reset` then
#: *discarded* the suite it parsed out of a ``"libero_spatial/3"`` task name — rolling out an
#: object-suite environment under a spatial-suite label. The run's own tasks are the only place the
#: intended suite is stated, so the factory reads them.
_TASK_AWARE: dict[str, Callable[[Sequence[str] | None], SuiteAdapter]] = {
    "libero": _make_libero,
}


def make_suite(name: str, *, tasks: Sequence[str] | None = None) -> SuiteAdapter:
    """Instantiate a suite by name.

    ``tasks`` is the run's requested task list (``RunConfig.tasks``). A task-aware suite (see
    :data:`_TASK_AWARE`) is built to match it — LIBERO derives its task suite and task ids from
    the ``"<suite>/<id>"`` names — and every other suite ignores it.

    Raises:
        KeyError: if ``name`` is not a registered suite.
        ValueError: if ``tasks`` name more than one LIBERO task suite, or a suite LIBERO lacks.
    """
    if name not in SUITES:
        raise KeyError(f"unknown suite {name!r}; available: {available_suites()}")
    task_aware = _TASK_AWARE.get(name)
    if task_aware is not None:
        return task_aware(tasks)
    return SUITES[name]()


__all__ = [
    "SUITES",
    "SCAFFOLDING_SUITES",
    "STATUS_SCAFFOLDING",
    "suite_scaffolding_note",
    "SUITE_GATING_NOTES",
    "suite_gating_note",
    "REQUIRES_LEROBOT",
    "FIXTURE_SUITES",
    "KIND_FIXTURE",
    "KIND_SIMULATOR",
    "SuiteAdapter",
    "StubSuite",
    "available_suites",
    "suite_is_ready",
    "suite_kind",
    "make_suite",
]
