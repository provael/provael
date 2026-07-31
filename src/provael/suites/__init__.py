"""Simulation suites and a small name -> suite factory.

The ``stub`` suite is always available (pure CPU, no deps). The ``libero`` suite wraps
a real LeRobot LIBERO environment; constructing it is cheap and never imports lerobot
(the optional dependency is only touched in ``reset``/``step``, which raise a clear,
actionable error if the ``[lerobot]`` extra is absent).
"""

from __future__ import annotations

from collections.abc import Callable

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
}

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


def suite_is_ready(name: str) -> bool:
    """Whether ``name`` can run in the current environment right now."""
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
