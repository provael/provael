# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The `calibrate` command.

Fits the per-task unsafe predicate from benign rollouts, and — with `--attack` — chooses the
hazard face against attacked ones. Three-way by default (fit / tuning / eval): the eval split is
scored only after the predicate is chosen, so its FPR is an estimate and travels in a binding that
fails closed; `--split two-way` keeps the historical fit / tuning path, whose FPR is a tuning
figure."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from provael import __version__
from provael.calibration import (
    Split,
    calibrate_suite,
    save_calibration,
)
from provael.cli._shared import _err, _fail, _out, _split_csv, app
from provael.policies.lerobot_adapter import IncompatiblePolicyError, MissingLeRobotError


class SplitChoice(StrEnum):
    """`--split` values; the strings are the artifact's `split` field verbatim."""

    two_way = "two-way"
    three_way = "three-way"


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
            help="Number of benign rollouts. Split three ways into fit / tuning / eval by default "
            "(needs 3 or more); --split two-way divides them into fit / tuning only.",
        ),
    ] = 20,
    seed: Annotated[int, typer.Option(min=0, help="Base seed; rollout i uses seed + i.")] = 0,
    horizon: Annotated[int, typer.Option(min=1, help="Max timesteps per benign rollout.")] = 8,
    target_fpr: Annotated[
        float,
        typer.Option(
            "--target-fpr", min=0.0, max=1.0,
            help="Max benign FPR on the tuning split (the split the predicate is selected "
            "against — a target it is made to satisfy). A three-way fit then measures the FPR "
            "again on the eval split and records it beside this target, never in its place.",
        ),
    ] = 0.05,
    split: Annotated[
        SplitChoice,
        typer.Option(
            "--split",
            help="three-way (default): fit / tuning / eval — the eval split is scored after the "
            "predicate is chosen and its FPR is bound into the artifact; an eval FPR above target "
            "is recorded as an invalid binding, never re-fitted. two-way: the historical fit / "
            "tuning split; the recorded FPR is a tuning figure and the artifact carries no "
            "binding.",
        ),
    ] = SplitChoice.three_way,
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
    split_value: Split = "three-way" if split is SplitChoice.three_way else "two-way"
    try:
        calibrations = calibrate_suite(
            policy, suite, _split_csv(tasks), seed_list,
            target_fpr=target_fpr, horizon=horizon, tool_version=__version__, model=model,
            attack_name=attack, split=split_value,
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
    table.add_column("tuning FPR", justify="right", style="bold")
    # The eval column is the one that can disagree with the target: the tuning FPR was made to
    # meet it, the eval FPR was measured after the choice and may not.
    table.add_column("eval FPR", justify="right", style="bold")
    # BOTH ARMS, side by side, because a benign rate alone is exactly what made the ten
    # libero_object zones unreadable: five of the six candidate faces give a 0.0 benign FPR, so
    # that column on its own cannot tell a well-placed boundary from one nothing ever reaches.
    table.add_column("detection", justify="right", style="bold")
    table.add_column("face")
    table.add_column("boundary")
    written: list[Path] = []
    unselected: list[str] = []
    unbound: list[str] = []
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
        if cal.eval_fpr is None:
            eval_col = "[dim]none (two-way)[/dim]"
        elif cal.binding is not None and cal.binding.valid()[0]:
            eval_col = f"[green]{100.0 * cal.eval_fpr:.1f}%[/green] (n={len(cal.eval_seeds)})"
        else:
            eval_col = f"[red]{100.0 * cal.eval_fpr:.1f}% over target[/red]"
            unbound.append(task)
        table.add_row(
            task, cal.kind, str(cal.n_benign),
            f"{100.0 * cal.target_fpr:.1f}%", f"{100.0 * cal.benign_fpr:.1f}%", eval_col,
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
    if unbound:
        # A failure on the eval split is reported, not repaired: the artifact is written exactly
        # as the tuning split chose it, and its binding says the FPR claim did not survive. Moving
        # the threshold now would turn the eval split back into tuning data.
        _err.print(
            f"\n[red]eval split:[/red] {len(unbound)} calibration(s) exceeded the target FPR on "
            "the eval split ({', '.join(unbound)}). Written as fitted; nothing was re-fitted on "
            "the eval seeds. Each carries an INVALID binding, and a run under it reports the "
            "predicate as tuned, not bound — add benign rollouts and re-fit, or raise the target "
            "and say so."
        )
    _out.print(
        f"\nApply it: [bold]provael attack --policy {policy} --suite {suite} "
        f"--calib {out}[/bold]"
    )
