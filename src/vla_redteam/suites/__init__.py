"""Simulation suites and a small name -> suite factory.

The ``stub`` suite is always available (pure CPU, no deps). Real suites such as a
full LIBERO ``SuiteAdapter`` are planned for Part 2; see
:mod:`vla_redteam.policies.lerobot_adapter` for the documented ``lerobot-eval``
path in the meantime.
"""

from __future__ import annotations

from collections.abc import Callable

from vla_redteam.suites.base import SuiteAdapter
from vla_redteam.suites.stub import StubSuite

#: Registry of suite factories keyed by name.
SUITES: dict[str, Callable[[], SuiteAdapter]] = {
    "stub": StubSuite,
}


def available_suites() -> list[str]:
    """Names of all registered suites."""
    return sorted(SUITES)


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


__all__ = ["SUITES", "SuiteAdapter", "StubSuite", "available_suites", "make_suite"]
