"""Determinism: the same seed produces an identical report; different seeds differ.

The in-process tests below cannot see the whole contract. Two ``run()`` calls in one interpreter
share one ``PYTHONHASHSEED``, one ``id()`` space and one import order, so a report field derived
from ``hash()`` of a str, from unordered ``set`` iteration, or from process state would compare
equal in every one of them while still differing between two ``provael attack`` invocations. The
cross-process test at the bottom is the one that actually pins "a report is a pure function of its
config" — it mirrors ``tests/test_crosswalk.py``'s subprocess + PYTHONHASHSEED pattern.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from provael.config import RunConfig
from provael.report import to_json, write_report
from provael.runner import run


def test_same_seed_identical_report() -> None:
    config = RunConfig(policy="stub", suite="stub", attacks=["instruction"], episodes=10, seed=0)
    first = run(config)
    second = run(config)
    assert first.model_dump() == second.model_dump()
    assert to_json(first) == to_json(second)


def test_different_seed_differs() -> None:
    a = run(RunConfig(episodes=10, seed=0))
    b = run(RunConfig(episodes=10, seed=1))
    assert to_json(a) != to_json(b)


def test_report_bytes_independent_of_output_path(tmp_path: Path) -> None:
    # The report must not embed the output directory (or any wall-clock value),
    # so two identical runs to different folders yield byte-identical report.json.
    config_a = RunConfig(episodes=10, seed=0, out=tmp_path / "a")
    config_b = RunConfig(episodes=10, seed=0, out=tmp_path / "b")
    json_a, _ = write_report(run(config_a), config_a.out)
    json_b, _ = write_report(run(config_b), config_b.out)
    assert json_a.read_text(encoding="utf-8") == json_b.read_text(encoding="utf-8")


def test_repeated_full_runs_are_stable() -> None:
    config = RunConfig(episodes=10, seed=0)
    dumps = {to_json(run(config)) for _ in range(3)}
    assert len(dumps) == 1


# --------------------------------------------------------------------------- #
# cross-process (a fresh interpreter and a different PYTHONHASHSEED per run)
# --------------------------------------------------------------------------- #

#: Run the library, not the console script: this stays independent of whether the package is
#: installed and of any CLI output formatting, while still giving each run its own interpreter.
_EMIT = (
    "from provael.config import RunConfig; from provael.report import to_json; "
    "from provael.runner import run; "
    "import sys; print(to_json(run(RunConfig.model_validate_json(sys.argv[1]))), end='')"
)


def _emit(config: RunConfig, hashseed: str) -> str:
    proc = subprocess.run(
        [sys.executable, "-c", _EMIT, config.model_dump_json()],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONHASHSEED": hashseed},
    )
    return proc.stdout


@pytest.mark.parametrize(
    "config",
    [
        # scalar predicate, single family
        RunConfig(policy="stub", suite="stub", attacks=["instruction"], episodes=6, seed=0),
        # spatial predicate, and a benign control + several families so `by_attack`, `roles` and
        # `eai` (all dict-valued, all built by iterating collections) are exercised too.
        RunConfig(
            policy="stub",
            suite="reach",
            attacks=["none", "instruction", "visual", "action"],
            episodes=4,
            seed=3,
        ),
    ],
    ids=["stub-scalar", "reach-spatial"],
)
def test_report_bytes_are_stable_across_processes(config: RunConfig) -> None:
    # A different PYTHONHASHSEED per interpreter: any field derived from str hashing or from `set`
    # iteration order diverges here while every in-process test above stays green.
    first = _emit(config, "0")
    assert first == _emit(config, "1") == _emit(config, "524287")
