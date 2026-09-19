# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""`coverage` and `watch`: what this install knows about itself, and how current it is."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from provael import __version__
from provael.cli._shared import _err, _fail, _git_commit, _out, app
from provael.coverage import coverage, coverage_json, coverage_line
from provael.report import load_report
from provael.watch import (
    STALE_DAYS,
    age_days,
    append_measurement,
    latest_measurement,
    write_badge,
)


@app.command("coverage")
def coverage_cmd(
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit JSON instead of the one-line form.")
    ] = False,
) -> None:
    """Print the coverage counts, straight from the registries and the committed runs.

    One place computes these so every other surface can render rather than retype — the README,
    the docs, the Space and the website all restate them, and a restated number drifts.

    It never prints a bare total. `families=16` alone reads as sixteen MEASURED families; the
    `real_policy` / `stub_only` pair is what stops that, and it travels in the same output so a
    consumer cannot pick up only the flattering half. Note also that `attacks` and `families` are
    different numbers: 39 adversarial attacks group into 17 adversarial families, and reading the
    registry dict's length as a family count overstates coverage by 14.

    From a pip-installed wheel the evidence fields read `unscanned` rather than `0`. A wheel does
    not package `results/`, so there is nothing to derive them from — and `real_policy=0` would
    read as "no family has ever been measured", contradicting a published claim rather than
    reporting a local fact. Registry counts are properties of the package, correct either way.
    """
    # Plain print, NOT the rich console: rich soft-wraps to the terminal width, which split the
    # "one machine-readable line" across two lines and corrupted the JSON mid-string. Machine
    # output must not be laid out for a human reader. A test asserts the JSON parses.
    print(coverage_json() if as_json else coverage_line())
    cov = coverage()
    if not cov.evidence_scanned:
        # stderr, so the machine-readable line on stdout stays exactly one line and pipes clean.
        _err.print(
            "note: no results/ directory here, so real_policy / stub_only / hardware read "
            "'unscanned' rather than 0 — this is an installed package, not a checkout. The "
            "published counts are derived in the repo: "
            "https://github.com/provael/provael#coverage",
            style="dim",
        )


@app.command("watch")
def watch_cmd(
    run_dir: Annotated[
        Path | None,
        typer.Option(
            "--record",
            help="Record this run directory's report.json as a measurement (append to the ledger). "
            "Omit to only refresh the badge from what is already recorded.",
        ),
    ] = None,
    watch_dir: Annotated[
        Path, typer.Option("--dir", help="Where the ledger and badge live.")
    ] = Path("watch"),
    commit: Annotated[
        str | None, typer.Option("--commit", help="Source commit to record with the measurement.")
    ] = None,
) -> None:
    """Record a measurement and refresh the freshness badge (the continuous-assurance signal).

    Two modes, and the second is the one that matters: `--record` appends a completed run to the
    trial ledger and the run-level watch log; with no arguments it only RECOMPUTES the badge from
    what is already recorded. That second mode is why the badge can go red on its own — a cheap
    CPU cron refreshes the age even when no measurement happened, so measurements stopping is
    visible instead of freezing the badge on its last green.
    """
    if run_dir is not None:
        try:
            report = load_report(run_dir)
        except (FileNotFoundError, ValidationError) as exc:
            _fail(f"{run_dir} holds no readable report.json: {exc}")
            return
        record = append_measurement(
            watch_dir, report, commit=commit or _git_commit() or f"v{__version__}"
        )
        _out.print(
            f"[green]recorded[/green] {record.policy} × {record.suite} "
            f"({record.successes}/{record.attempts}) measured with provael {record.tool_version}"
        )

    path, payload = write_badge(watch_dir)
    latest = latest_measurement(watch_dir)
    age = age_days(latest)
    _out.print(f"badge: [cyan]{path}[/cyan]  {payload['label']}: {payload['message']}")
    if age is None:
        _err.print(
            "[yellow]no measurement recorded yet[/yellow] — the badge reads 'never' and is an "
            "error state on purpose: a freshness badge with nothing behind it must not read green."
        )
    elif payload.get("isError"):
        # NAMES THE CAUSE, not just the symptom. This used to read "the README's
        # continuous-verification claim is not currently true", which is accurate and useless: it
        # tells a reader the claim is broken without telling them why. It then over-corrected into
        # asserting the lane had NEVER been configured, which was true when written and stopped
        # being true the day it was enabled. Both failure modes age the badge identically, so the
        # message must not guess between them. See docs/standards/last-measured.md.
        _err.print(
            f"[red]stale[/red]: the newest measurement is {int(age)} days old (over "
            f"{STALE_DAYS}).\n"
            "Either the scheduled measurement lane is not configured, or it is configured and "
            "its recent runs did not record. `gpu-scheduled.yml` needs the repo variable "
            "ENABLE_GPU_SCHEDULED=true and the MODAL_TOKEN_ID / MODAL_TOKEN_SECRET secrets, and "
            "it records only on success — so a failing run ages this badge exactly like an "
            "absent one. Check its recent runs before assuming it was never switched on. "
            "See docs/standards/last-measured.md."
        )
