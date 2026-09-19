# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Every workflow declares top-level permissions, and none of them grants a write at the top.

WHY. A top-level ``permissions:`` block is inherited by every job in the file, so one
``security-events: write`` or ``packages: write`` at the top hands that scope to jobs that never
needed it — which is what OpenSSF Scorecard's Token-Permissions check scored 0 on (19 September
2026: `checkpoint-security-gate.yml` and `docker-publish.yml`). The fix is mechanical and easy to
undo by accident in the next workflow someone writes, so it is a test: read-only or empty at the
top, writes opted into per job. `read-all` is a read.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

WORKFLOWS = sorted((Path(__file__).resolve().parent.parent / ".github" / "workflows").glob("*.yml"))


def _top_level_permissions(path: Path) -> object:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "permissions" in doc, (
        f"{path.name} declares no top-level `permissions:`; without one every job inherits the "
        "repository default, which may be write-all"
    )
    return doc["permissions"]


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_top_level_permissions_are_read_only_or_empty(path: Path) -> None:
    perms = _top_level_permissions(path)
    if isinstance(perms, str):
        assert perms in {"read-all", "{}"}, f"{path.name}: top-level permissions {perms!r}"
        return
    assert isinstance(perms, dict), f"{path.name}: unexpected permissions shape {perms!r}"
    writes = {scope: level for scope, level in perms.items() if level != "read"}
    assert not writes, (
        f"{path.name} grants {writes} at the top level; move the write into the one job that "
        "needs it (every other job in the file inherits a top-level scope)"
    )


def test_the_suite_actually_walked_the_workflows() -> None:
    assert len(WORKFLOWS) >= 10, "the workflow glob found almost nothing — is the checkout complete?"
