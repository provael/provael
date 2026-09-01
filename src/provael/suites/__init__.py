"""Simulation suites and a small name -> suite factory.

The ``stub`` suite is always available (pure CPU, no deps). The ``libero`` suite wraps
a real LeRobot LIBERO environment; constructing it is cheap and never imports lerobot
(the optional dependency is only touched in ``reset``/``step``, which raise a clear,
actionable error if the ``[lerobot]`` extra is absent).
"""

from __future__ import annotations

from collections.abc import Callable

from provael.suites.ai2_bridge import Ai2BridgeSuite
from provael.suites.base import SuiteAdapter
from provael.suites.humanoid import HumanoidSuite
from provael.suites.reach import ReachSuite
from provael.suites.stub import StubSuite


def _make_libero() -> SuiteAdapter:
    # Imported here (not at module top) only for symmetry; the adapter module itself
    # imports no optional deps at module scope, so this stays CPU-safe either way.
    from provael.suites.libero import LiberoSuiteAdapter

    return LiberoSuiteAdapter()


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


def make_suite(name: str) -> SuiteAdapter:
    """Instantiate a suite by name.

    Raises:
        KeyError: if ``name`` is not a registered suite.
    """
    try:
        factory = SUITES[name]
    except KeyError:
        raise KeyError(f"unknown suite {name!r}; available: {available_suites()}") from None
    return factory()


__all__ = [
    "SUITES",
    "SCAFFOLDING_SUITES",
    "STATUS_SCAFFOLDING",
    "suite_scaffolding_note",
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
