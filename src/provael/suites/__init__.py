"""Simulation suites and a small name -> suite factory.

The ``stub`` suite is always available (pure CPU, no deps). The ``libero`` suite wraps
a real LeRobot LIBERO environment; constructing it is cheap and never imports lerobot
(the optional dependency is only touched in ``reset``/``step``, which raise a clear,
actionable error if the ``[lerobot]`` extra is absent).
"""

from __future__ import annotations

from collections.abc import Callable

from provael.suites.base import SuiteAdapter
from provael.suites.stub import StubSuite


def _make_libero() -> SuiteAdapter:
    # Imported here (not at module top) only for symmetry; the adapter module itself
    # imports no optional deps at module scope, so this stays CPU-safe either way.
    from provael.suites.libero import LiberoSuiteAdapter

    return LiberoSuiteAdapter()


#: Registry of suite factories keyed by name.
SUITES: dict[str, Callable[[], SuiteAdapter]] = {
    "stub": StubSuite,
    "libero": _make_libero,
}

#: Suites that require the optional ``[lerobot]`` extra (and the LIBERO simulator).
REQUIRES_LEROBOT: frozenset[str] = frozenset({"libero"})


def available_suites() -> list[str]:
    """Names of all registered suites."""
    return sorted(SUITES)


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
    "SuiteAdapter",
    "StubSuite",
    "available_suites",
    "suite_is_ready",
    "make_suite",
]
