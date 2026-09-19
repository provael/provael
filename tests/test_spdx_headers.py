# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Every tracked source file carries the SPDX licence header.

WHY. The root LICENSE says Apache-2.0; per-file identifiers are what licence scanners read, and
until 20 September 2026 no file had one. `scripts/add_spdx_headers.py` adds them; this test keeps
new files honest, because a header convention that nothing enforces lasts until the next file is
created. The scope (``.py`` and ``.sh`` under src/, scripts/, tests/, examples/) is the script's
own, imported rather than restated, so the two cannot drift apart.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location("add_spdx_headers", ROOT / "scripts" / "add_spdx_headers.py")
assert _SPEC is not None and _SPEC.loader is not None
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules["add_spdx_headers"] = _mod
_SPEC.loader.exec_module(_mod)


def test_every_tracked_source_file_has_the_header() -> None:
    files = _mod.tracked_source_files(ROOT)
    assert len(files) > 300, "the walk found almost nothing — is this a git checkout?"
    missing = [p.relative_to(ROOT) for p in files if not _mod.has_header(p.read_text(encoding="utf-8"))]
    assert not missing, (
        f"{len(missing)} source file(s) lack the SPDX header; run "
        f"`python scripts/add_spdx_headers.py`: {[str(m) for m in missing[:10]]}"
    )


def test_header_lands_under_a_shebang() -> None:
    text = "#!/usr/bin/env python3\n\"\"\"doc\"\"\"\n"
    out = _mod.with_header(text)
    assert out.splitlines()[0] == "#!/usr/bin/env python3"
    assert out.splitlines()[1] == _mod.LICENSE_LINE
    assert out.splitlines()[2] == _mod.COPYRIGHT_LINE
    assert out.endswith('"""doc"""\n')


def test_adding_twice_changes_nothing() -> None:
    once = _mod.with_header("import os\n")
    assert _mod.with_header(once) == once


@pytest.mark.parametrize("text", ["", "x = 1\n"])
def test_header_goes_first_without_a_shebang(text: str) -> None:
    out = _mod.with_header(text)
    assert out.startswith(_mod.LICENSE_LINE + "\n" + _mod.COPYRIGHT_LINE + "\n")
    assert out.endswith(text)
