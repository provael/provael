# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The `workspace-bounds` command: report the benign envelope a suite's tasks occupy."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from provael.cli._shared import _err, _fail, _out, app


@app.command("workspace-bounds")
def workspace_bounds_cmd(
    runs: Annotated[
        list[str], typer.Option("--runs", help="Run dir(s), glob(s), or report.json path(s).")
    ],
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit JSON instead of the table.")
    ] = False,
) -> None:
    """Per-task reachable-workspace bounds, from the BENIGN trajectories in a set of runs.

    This is the INPUT to a keep-out calibration (#136) and deliberately not the calibration. A
    calibrated zone needs a margin - how far outside the benign envelope the hazard region starts -
    and choosing one before looking at real benign spread is exactly how the current default box
    came to overlap the workspace it was meant to sit outside. So this prints the observation and
    stops.

    The episode count per task is part of the answer, not a footnote: bounds from two episodes and
    bounds from fifty are different objects, and a thin estimate is flagged rather than smoothed.
    """
    from provael.workspace import bounds_from_paths

    try:
        bounds = bounds_from_paths([Path(r) for r in runs])
    except FileNotFoundError as exc:
        _fail(str(exc))
        return

    if not bounds:
        _fail(
            "no benign trajectories found. Runs recorded before 0.35.0 (report schema 3) carry no "
            "trajectory at all - that is the gap #136 is about, and those runs cannot feed a "
            "calibration. Re-run the benign arm with a current build."
        )
        return

    if as_json:
        _out.print_json(data=[b.model_dump() for b in bounds])
        return

    table = Table(title="Benign reachable-workspace bounds (observation, NOT a calibration)")
    table.add_column("task")
    table.add_column("episodes", justify="right")
    table.add_column("poses", justify="right")
    table.add_column("lower")
    table.add_column("upper")
    for b in bounds:
        table.add_row(
            b.task,
            f"{b.episodes}" + (" [yellow]thin[/yellow]" if b.thin else ""),
            str(b.steps),
            "[" + ", ".join(f"{x:+.4f}" for x in b.lower) + "]",
            "[" + ", ".join(f"{x:+.4f}" for x in b.upper) + "]",
        )
    _out.print(table)
    thin = [b.task for b in bounds if b.thin]
    if thin:
        _err.print(
            f"[yellow]note:[/yellow] {len(thin)} task(s) estimated from fewer than 5 benign "
            f"episodes ({', '.join(thin[:5])}). Bounds that thin describe the episodes that ran, "
            "not the workspace."
        )
    _out.print(
        "\nOBSERVED bounds only. No calibrated zone is emitted: that needs a margin decision, "
        "and this data is what the decision should be made against (#136)."
    )
