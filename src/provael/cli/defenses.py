# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The `mitigation` command: measure what a defense actually buys."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.table import Table

from provael.cli._shared import _defense_from_manifest, _fail, _git_commit, _out, app
from provael.defenses.measure import (
    MitigationVerdict,
    build_mitigation_report,
    write_mitigation,
)
from provael.report import load_report


@app.command()
def mitigation(
    defended: Annotated[
        Path, typer.Option("--defended", help="Run directory from `attack --defense <name>`.")
    ],
    baseline: Annotated[
        Path, typer.Option("--baseline", help="Run directory from the SAME config, undefended.")
    ],
    out: Annotated[
        Path, typer.Option("--out", help="Directory to write the mitigation report into.")
    ] = Path("runs/mitigation"),
    defense: Annotated[
        str | None,
        typer.Option("--defense", help="Defense name for the report. Read from the defended run's "
                     "execution manifest when omitted."),
    ] = None,
) -> None:
    """Measure a defense: pre/post ASR per family under the docs/defenses.md protocol.

    Exits non-zero on `rejected-benign-cost` so it is usable as a CI gate — a defense that lowers
    ASR by breaking the benign task must fail a pipeline, not be reported and ignored.
    """
    try:
        defended_report = load_report(defended)
        undefended_report = load_report(baseline)
    except FileNotFoundError as exc:
        _fail(str(exc))
        return
    except ValidationError:
        _fail("--defended and --baseline must both be valid Provael run directories")
        return

    name = defense or _defense_from_manifest(defended) or "unknown"
    report = build_mitigation_report(
        defended_report,
        undefended_report,
        defense=name,
        issued_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        commit=_git_commit() or "unknown",
    )

    table = Table(title=f"Mitigation — {name}")
    table.add_column("family", style="cyan", no_wrap=True)
    table.add_column("pre ASR", justify="right")
    table.add_column("pre 95% CI", justify="center")
    table.add_column("post ASR", justify="right")
    table.add_column("post 95% CI", justify="center")
    table.add_column("credited", justify="center")
    for row in report.rows:
        pre = "N/A" if row.pre_asr is None else f"{100 * row.pre_asr:.1f}%"
        post = "N/A" if row.post_asr is None else f"{100 * row.post_asr:.1f}%"
        pre_ci = "N/A" if row.pre_ci95 is None else (
            f"[{100 * row.pre_ci95[0]:.0f}-{100 * row.pre_ci95[1]:.0f}%]"
        )
        post_ci = "N/A" if row.post_ci95 is None else (
            f"[{100 * row.post_ci95[0]:.0f}-{100 * row.post_ci95[1]:.0f}%]"
        )
        table.add_row(row.family, pre, pre_ci, post, post_ci, "yes" if row.credited else "no")
    _out.print(table)
    _out.print(f"Acceptance gate: {report.acceptance_gate}")

    json_path, md_path = write_mitigation(report, out)
    _out.print(f"Wrote [cyan]{json_path}[/cyan] and [cyan]{md_path}[/cyan]")
    _out.print(f"\n[bold]Verdict:[/bold] {report.verdict.value}")

    if report.verdict is MitigationVerdict.rejected_benign_cost:
        _fail(
            "defense REJECTED: it raised the benign FPR or moved clean-task success outside its "
            "CI. Lowering ASR by breaking the task is not a mitigation."
        )
