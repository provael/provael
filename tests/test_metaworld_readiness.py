# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Meta-World is not ready on ``lerobot`` alone.

Meta-World is a separate lerobot extra (``lerobot[metaworld]``), and ``provael[lerobot]`` does not
bring it in — the suite's own install hint says so. Until 26 September 2026 both readiness checks
asked only whether ``lerobot`` was importable, so ``list-suites`` told a box with ``provael[lerobot]``
that the suite was ready, and the run then failed inside LeRobot's env factory.
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


def test_both_present_is_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(importlib.util, "find_spec", _only("lerobot", "metaworld"))
    assert suite_is_ready("metaworld") is True
    assert MetaworldSuiteAdapter.lerobot_available() is True
