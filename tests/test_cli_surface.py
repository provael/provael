# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""`provael --help` is a published surface, and a refactor must not move it.

WHY THIS EXISTS. Issue #193 asks for `src/provael/cli.py` — three thousand lines and 27 top-level
commands — to be split into modules, and states the acceptance plainly: every `--help` must render
identically before and after, because adopters have pinned these commands and flags in their own
scripts. That acceptance cannot be checked by reading a two-thousand-line file move.

`scripts/gen_cli_surface.py` captures the surface as data — command order, help text, parameter
names, flags, required-ness — and `tests/fixtures/cli-surface.json` is the committed snapshot. The
snapshot is data rather than rendered `--help` text because rendered help wraps to the terminal: a
byte-comparison of it fails on a different `COLUMNS` and passes on a genuinely lost option that
happened to reflow.

WHAT IT CATCHES, verified by mutation rather than asserted:

* two commands reordered — caught. Typer prints in registration order, so a split that re-registers
  in a different order moves what a reader sees while every command still exists. This is the
  regression a file move actually produces.
* an option renamed — caught.
* a help string rewritten — caught.
* a command's PYTHON FUNCTION renamed — deliberately NOT caught, and that is the property the split
  depends on. Every command carries its name explicitly in `@app.command("...")`, so moving and
  renaming the implementation cannot move the surface.

WHEN THIS FAILS AND YOU MEANT IT: run `make gen-cli-surface`, commit the diff, and say in the
commit message what changed about `provael --help`. A diff here is adopter-visible.

IF YOU MUTATION-TEST THIS, CLEAR `__pycache__` BETWEEN MUTATIONS. Restoring `cli.py` with `cp`
gives it a fresh mtime, and CPython still served the mutated bytecode on the next run here — so a
snapshot regenerated after a "restore" captured the mutation instead of the real surface, and the
committed fixture had two commands in the wrong order while every check reported green. `find src
-name __pycache__ -type d -exec rm -rf {} +` between steps, or the guard verifies the mutation
against itself.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GENERATOR = REPO / "scripts" / "gen_cli_surface.py"
SNAPSHOT = REPO / "tests" / "fixtures" / "cli-surface.json"


def _generator():
    spec = importlib.util.spec_from_file_location("gen_cli_surface", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_cli_surface_has_not_moved() -> None:
    assert _generator().main(["--check"]) == 0, (
        "the CLI surface differs from tests/fixtures/cli-surface.json. If you changed `provael "
        "--help` on purpose, run `make gen-cli-surface` and say so in the commit."
    )


def test_the_snapshot_is_not_empty() -> None:
    """A generator that silently produced nothing would make the check above vacuous."""
    import json

    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert len(data["commands"]) >= 25, f"only {len(data['commands'])} commands captured"
    assert sum(len(c["params"]) for c in data["commands"]) >= 100
    assert any("commands" in c for c in data["commands"]), (
        "no sub-group captured, so `provael leaderboard build` and `provael study eai04` are "
        "outside the snapshot entirely"
    )


def test_command_order_is_preserved_verbatim() -> None:
    """Stated as a literal, so a reviewer of the split can read the surface without the fixture."""
    import json

    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert [c["name"] for c in data["commands"]] == [
        "version", "crosswalk",
        "list-policies", "list-suites", "list-attacks", "list-recipes", "list-reproductions",
        "list-defenses",
        "attack", "reproduce", "report", "transfer-test", "export", "compose-video", "dossier",
        "certify",  # hidden, deprecated alias of dossier until 0.46.0 (20 Sep 2026)
        "serve",
        "evidence-manifest", "attest", "calibrate", "workspace-bounds", "coverage", "watch",
        "offline-study", "sim-to-real", "submit", "verify-checkpoint", "mitigation", "doctor",
        "leaderboard", "study",
    ]
