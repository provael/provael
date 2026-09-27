# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Meta-World is not ready on ``lerobot`` alone.

Meta-World is a separate lerobot extra (``lerobot[metaworld]``), and ``provael[lerobot]`` does not
bring it in — the suite's own install hint says so. Until 26 September 2026 both readiness checks
asked only whether ``lerobot`` was importable, so ``list-suites`` told a box with ``provael[lerobot]``
that the suite was ready, and the run then failed inside LeRobot's env factory.

Since 28 September 2026 the suite is also declared scaffolding (no benchmark has ever been run
through it), so ``suite_is_ready`` answers ``False`` for it whatever is installed. The adapter's own
check, ``MetaworldSuiteAdapter.lerobot_available``, still carries the two-module rule, and is what
these tests hold.
"""

from __future__ import annotations

import importlib.util
from typing import Any

import pytest

from provael.policies.lerobot_adapter import MissingLeRobotError
from provael.suites import suite_is_ready
from provael.suites.metaworld import MetaworldSuiteAdapter


def _only(*present: str) -> Any:
    """A ``find_spec`` stand-in under which only ``present`` (of lerobot / metaworld) imports."""
    real = importlib.util.find_spec

    def find_spec(name: str, *args: Any, **kwargs: Any) -> Any:
        if name in ("lerobot", "metaworld"):
            return object() if name in present else None
        return real(name, *args, **kwargs)

    return find_spec


def test_lerobot_alone_does_not_make_metaworld_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(importlib.util, "find_spec", _only("lerobot"))
    assert suite_is_ready("metaworld") is False
    assert MetaworldSuiteAdapter.lerobot_available() is False
    with pytest.raises(MissingLeRobotError, match="lerobot\\[metaworld\\]"):
        MetaworldSuiteAdapter()._ensure_lerobot()


def test_both_present_readies_the_adapter_but_not_the_scaffolded_suite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(importlib.util, "find_spec", _only("lerobot", "metaworld"))
    assert MetaworldSuiteAdapter.lerobot_available() is True
    # Importable is not runnable: a scaffolded suite is never reported ready.
    assert suite_is_ready("metaworld") is False
