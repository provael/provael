"""The AI2 harness bridge is registered scaffolding and must keep saying so.

The risk this guards is specific: a registered suite that returns plausible values instead of
raising is how an unbuilt path produces a number. ``ai2_bridge`` must raise on every contract
method until a benchmark has actually been run through it.
"""

from __future__ import annotations

import pytest

from provael.suites import (
    SCAFFOLDING_SUITES,
    STATUS_SCAFFOLDING,
    available_suites,
    make_suite,
    suite_is_ready,
    suite_scaffolding_note,
)
from provael.suites.ai2_bridge import HARNESS_V040_BENCHMARKS, Ai2BridgeSuite

NAME = "ai2_bridge"


def test_is_registered_and_visible() -> None:
    assert NAME in available_suites()
    assert isinstance(make_suite(NAME), Ai2BridgeSuite)


def test_is_declared_scaffolding() -> None:
    assert NAME in SCAFFOLDING_SUITES
    note = suite_scaffolding_note(NAME)
    assert note is not None and note.startswith("scaffolding:")


def test_is_never_reported_ready() -> None:
    """Registered is not runnable. A reader must not be told a pip install is all that is missing."""
    assert suite_is_ready(NAME) is False


@pytest.mark.parametrize(
    ("method", "args"),
    [("tasks", ()), ("reset", ("t", 0)), ("step", ({},)), ("is_unsafe", ({},))],
)
def test_every_contract_method_raises(method: str, args: tuple[object, ...]) -> None:
    """Raising beats degrading: a suite that returns a plausible default fabricates a measurement."""
    with pytest.raises(NotImplementedError, match="never been run"):
        getattr(Ai2BridgeSuite(), method)(*args)


def test_the_v040_benchmark_list_is_eighteen() -> None:
    """The roadmap's "~18 benchmarks" is a v0.4.0 figure; pin it so the claim stays checkable."""
    assert len(HARNESS_V040_BENCHMARKS) == 18
    assert len(set(HARNESS_V040_BENCHMARKS)) == 18
    assert "libero" in HARNESS_V040_BENCHMARKS


def test_scaffolding_status_reads_differently_from_the_policy_one() -> None:
    """A suite has never run a *benchmark*; a policy has never run a *checkpoint*. Keep them apart."""
    from provael.policies.registry import STATUS_SCAFFOLDING as POLICY_STATUS

    assert STATUS_SCAFFOLDING != POLICY_STATUS
    assert "benchmark" in STATUS_SCAFFOLDING
