# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The `calibrate` command.

Fits the per-task unsafe predicate from benign rollouts, and — with `--attack` — chooses the
hazard face against attacked ones."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from provael import __version__
from provael.calibration import (
    calibrate_suite,
    save_calibration,
)
from provael.cli._shared import _err, _fail, _out, _split_csv, app
from provael.policies.lerobot_adapter import IncompatiblePolicyError, MissingLeRobotError


@app.command()
def calibrate(
    policy: Annotated[str, typer.Option(help="Registered policy name.")] = "stub",
    suite: Annotated[str, typer.Option(help="Registered suite name.")] = "stub",
    tasks: Annotated[
        str | None, typer.Option(help="Comma-separated task subset (default: all).")
    ] = None,
    seeds: Annotated[
        int,
        typer.Option(
            min=2,
            help="Number of benign rollouts (split two ways into fit / tuning; there is no "
            "untouched evaluation split on this path).",
        ),
    ] = 20,
    seed: Annotated[int, typer.Option(min=0, help="Base seed; rollout i uses seed + i.")] = 0,
    horizon: Annotated[int, typer.Option(min=1, help="Max timesteps per benign rollout.")] = 8,
    target_fpr: Annotated[
        float,
        typer.Option(
            "--target-fpr", min=0.0, max=1.0,
            help="Max benign FPR on the tuning split (the split the predicate is selected "
            "against — a target it is made to satisfy, not an untouched evaluation).",
        ),
    ] = 0.05,
    model: Annotated[
        str | None, typer.Option(help="Checkpoint override (real policies).")
    ] = None,
    attack: Annotated[
        str | None,
        typer.Option(
            help="Attack for the ADVERSARIAL arm, run at the tuning seeds. Without it a spatial "
            "fit cannot choose which face of the benign envelope to guard, and the artifact says "
            "so — see `provael doctor`.",
        ),
    ] = None,
    out: Annotated[
        Path, typer.Option(help="Output directory for calibration artifacts.")
    ] = Path("calib"),
) -> None:
    """Calibrate the per-task unsafe predicate from benign (and optionally attacked) rollouts."""
    seed_list = list(range(seed, seed + seeds))
    try:
        calibrations = calibrate_suite(
            policy, suite, _split_csv(tasks), seed_list,
            target_fpr=target_fpr, horizon=horizon, tool_version=__version__, model=model,
            attack_name=attack,
        )
    except (MissingLeRobotError, IncompatiblePolicyError) as exc:
        _fail(str(exc))
        return
    except KeyError as exc:
        _fail(str(exc).strip('"'))
        return
    except (NotImplementedError, ValueError) as exc:
        _fail(str(exc))
        return

    table = Table(title="Provael — calibration", title_style="bold")
    table.add_column("task", style="cyan", no_wrap=True)
    table.add_column("predicate", style="magenta")
    table.add_column("n benign", justify="right")
    table.add_column("target FPR", justify="right")
    table.add_column("benign FPR", justify="right", style="bold")
    # BOTH ARMS, side by side, because a benign rate alone is exactly what made the ten
    # libero_object zones unreadable: five of the six candidate faces give a 0.0 benign FPR, so
    # that column on its own cannot tell a well-placed boundary from one nothing ever reaches.
    table.add_column("detection", justify="right", style="bold")
    table.add_column("face")
    table.add_column("boundary")
    written: list[Path] = []
    unselected: list[str] = []
    for task, cal in calibrations.items():
        boundary = (
            f"danger > {cal.threshold:.3f}"
            if cal.kind == "scalar"
            else f"{len(cal.keep_out_zones)} keep-out zone(s)"
        )
        fit = cal.spatial_fit
        if fit is None or fit.detection_rate is None:
            detection = "[yellow]not measured[/yellow]"
        elif fit.detection_rate == 0.0:
            detection = f"[red]0.0% (0/{fit.n_adversarial})[/red]"
        else:
            hits = round(fit.detection_rate * fit.n_adversarial)
            detection = (
                f"[green]{100.0 * fit.detection_rate:.1f}%[/green] "
                f"({hits}/{fit.n_adversarial})"
            )
        if fit is None:
            face = "[dim]n/a[/dim]"
        elif fit.face_selected_from_data:
            face = fit.face
        else:
            face = f"[yellow]{fit.face} (default)[/yellow]"
            unselected.append(task)
        table.add_row(
            task, cal.kind, str(cal.n_benign),
            f"{100.0 * cal.target_fpr:.1f}%", f"{100.0 * cal.benign_fpr:.1f}%",
            detection, face, boundary,
        )
        written.append(save_calibration(cal, out))
    _out.print(table)
    for path in written:
        _out.print(f"Wrote [cyan]{path}[/cyan]")
    if unselected:
        # Said once, loudly, rather than left to be inferred from a column. This is the state all
        # ten committed libero_object zones are in, and reading their 0.0 benign FPR as evidence
        # the boundary was well placed is precisely the mistake it caused.
        _err.print(
            f"\n[yellow]note:[/yellow] {len(unselected)} calibration(s) kept the DEFAULT hazard "
            "face because no adversarial arm ran. A benign-only fit sees every face as equally "
            "clean — each one is outside the benign envelope by construction — so a low benign "
            "FPR here is not evidence the boundary is well placed. Re-run with "
            "[bold]--attack <name>[/bold] before adopting these."
        )
    _out.print(
        f"\nApply it: [bold]provael attack --policy {policy} --suite {suite} "
        f"--calib {out}[/bold]"
    )
