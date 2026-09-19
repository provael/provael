# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The `crosswalk` command: render the standards crosswalk in a chosen target and format."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape

from provael.cli._shared import CrosswalkFormat, CrosswalkTarget, _out, app
from provael.crosswalk import (
    ATLAS_JSON,
    CROSSWALK_JSON,
    FORESIGHT_JSON,
    SAFEVLA_JSON,
    VLA_ARENA_JSON,
    to_atlas_json,
    to_atlas_markdown,
    to_crosswalk_json,
    to_crosswalk_markdown,
    to_foresight_json,
    to_foresight_markdown,
    to_safevla_json,
    to_safevla_markdown,
    to_vla_arena_json,
    to_vla_arena_markdown,
)
from provael.report import load_report


@app.command("crosswalk")
def crosswalk_cmd(
    target: Annotated[
        CrosswalkTarget, typer.Option(help="Taxonomy to map the Top 10 against.")
    ] = CrosswalkTarget.robojailbench,
    fmt: Annotated[
        CrosswalkFormat, typer.Option("--format", help="Output format.")
    ] = CrosswalkFormat.json,
    in_dir: Annotated[
        Path | None,
        typer.Option(
            "--in",
            help="Run directory containing report.json. Only `--target foresight` reads it, to "
            "add this run's CC / RET / USR. Omit for the pure taxonomy mapping.",
        ),
    ] = None,
    out: Annotated[
        Path | None,
        typer.Option(
            help="Where to write the crosswalk. An EXISTING DIRECTORY receives the target's "
            "canonical filename (e.g. crosswalk.foresight.json); any other path is written as a "
            "file. Omit for stdout."
        ),
    ] = None,
) -> None:
    """Emit an Embodied AI Security Top 10 taxonomy crosswalk (deterministic).

    ``--target robojailbench`` maps RoboJailBench's 18 harm categories to the EAI id(s) and provael
    attack family/families that cover them, with an honest coverage state per category. Sim-only;
    no RoboJailBench benchmark is run and no comparative scores are produced.

    ``--target atlas`` maps all ten EAI risks to MITRE ATLAS tactic → technique phrasing, each with
    its coverage state. Proposed mapping, not endorsed by MITRE, and deliberately free of
    ``AML.TXXXX`` ids.

    ``--target foresight`` maps ForesightSafety-VLA's 13 diagnostic categories (arXiv:2606.27079),
    quoted verbatim, and states plainly where that benchmark's headline finding DISAGREES with
    provael's one real measurement. With ``--in`` it also reports this run's cumulative cost, risk
    exposure time and unsafe success rate — in their vocabulary, in provael's units, with the
    incomparability warning attached.

    ``--target vla_arena`` maps VLA-Arena's five safety suites (arXiv:2512.22539), identifiers
    verbatim, and carries the fact that their safety axis is **non-adversarial** as a
    machine-readable field: their suites place a hazard in the scene, none perturbs the instruction,
    so the corresponding provael arm is the benign control rather than any attack family.

    ``--target safevla`` maps SafeVLA-Bench (arXiv:2606.00773) structurally and records why no
    numeric comparison is emitted — provael's ``succ_but_unsafe`` shares a name with their SBU and
    has not been shown to share units, on an uncalibrated predicate.

    Neither ``vla_arena`` nor ``safevla`` accepts a measured comparison, so ``--in`` has no effect
    on them. That is a property of the mapping, not a missing feature.
    """
    report = load_report(in_dir) if in_dir is not None else None
    if target is CrosswalkTarget.atlas:
        payload = to_atlas_markdown() if fmt is CrosswalkFormat.md else to_atlas_json()
        basename = ATLAS_JSON
    elif target is CrosswalkTarget.foresight:
        payload = (
            to_foresight_markdown(report) if fmt is CrosswalkFormat.md
            else to_foresight_json(report)
        )
        basename = FORESIGHT_JSON
    elif target is CrosswalkTarget.vla_arena:
        # No `report` branch, unlike foresight: this target deliberately emits no provael number.
        # See VLA_ARENA_POSTURE — their safety axis is non-adversarial, so any provael ASR placed
        # beside it would be answering a question their suites do not ask.
        payload = to_vla_arena_markdown() if fmt is CrosswalkFormat.md else to_vla_arena_json()
        basename = VLA_ARENA_JSON
    elif target is CrosswalkTarget.safevla:
        # Also numberless, for a different reason: SAFEVLA_BLOCKER. Same metric name, unproven
        # equivalence, uncalibrated predicate.
        payload = to_safevla_markdown() if fmt is CrosswalkFormat.md else to_safevla_json()
        basename = SAFEVLA_JSON
    else:
        payload = to_crosswalk_markdown() if fmt is CrosswalkFormat.md else to_crosswalk_json()
        basename = CROSSWALK_JSON
    if out is not None:
        # `--out <dir>` is the shape every other run-producing command uses, and the shape a caller
        # naturally reaches for when `--in` and `--out` are the same run directory. Writing a file
        # NAMED like the directory would be the surprising outcome, so an existing directory gets
        # the target's canonical filename instead. Any other path stays a plain file path.
        target_path = out / basename if out.is_dir() else out
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(payload + "\n", encoding="utf-8")
        _out.print(f"[green]Wrote[/green] {escape(str(target_path))}")
    else:
        print(payload)
