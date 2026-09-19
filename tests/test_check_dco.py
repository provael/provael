# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The DCO check classifies commits the way CONTRIBUTING.md says it does."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location("check_dco", ROOT / "scripts" / "check_dco.py")
assert _SPEC is not None and _SPEC.loader is not None
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules["check_dco"] = _mod
_SPEC.loader.exec_module(_mod)

Commit = _mod.Commit


def test_a_signed_human_commit_passes() -> None:
    c = Commit("a" * 40, "dev@example.com", 1, "fix: x\n\nSigned-off-by: Dev <dev@example.com>\n")
    assert _mod.unsigned([c]) == []


def test_an_unsigned_human_commit_fails() -> None:
    c = Commit("b" * 40, "dev@example.com", 1, "fix: x\n")
    assert _mod.unsigned([c]) == [c]


def test_bots_and_merges_are_exempt() -> None:
    bot = Commit("c" * 40, "49699333+dependabot[bot]@users.noreply.github.com", 1, "chore(deps): bump\n")
    actions = Commit("d" * 40, "github-actions[bot]@users.noreply.github.com", 1, "chore: refresh\n")
    merge = Commit("e" * 40, "dev@example.com", 2, "Merge branch 'x'\n")
    assert _mod.unsigned([bot, actions, merge]) == []


def test_the_trailer_must_be_a_trailer_not_prose() -> None:
    c = Commit("f" * 40, "dev@example.com", 1, "docs: mention that Signed-off-by is required\n")
    assert _mod.unsigned([c]) == [c]


def test_the_range_parser_reads_this_repository(tmp_path: Path) -> None:
    """Build a two-commit repo and read it back — the %x00/%x1e framing must survive real git."""
    repo = tmp_path / "r"
    repo.mkdir()

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@example.com", *args],
            cwd=repo,
            check=True,
            capture_output=True,
        )

    git("init", "-q", "-b", "main")
    (repo / "a").write_text("1")
    git("add", "a")
    git("commit", "-q", "-m", "base")
    (repo / "a").write_text("2")
    git("commit", "-q", "-am", "unsigned change\n\nbody with\n\nblank lines")
    (repo / "a").write_text("3")
    git("commit", "-q", "-s", "-am", "signed change")
    out = subprocess.run(
        ["git", "log", "--reverse", "--format=%H", "HEAD~2..HEAD"], cwd=repo, check=True,
        capture_output=True, text=True,
    ).stdout.split()
    commits = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_dco.py"), "--range", "HEAD~2..HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert commits.returncode == 1
    assert out[0][:10] in commits.stderr and "unsigned change" in commits.stderr
    assert out[1][:10] not in commits.stderr  # the signed commit is not reported
