# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The `certify` command: build a certification dossier from a run."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from provael import __version__
from provael.calibration import load_calibrations
from provael.certify import CertifyProfile, write_dossier
from provael.cli._shared import (
    _decide,
    _decision_for,
    _err,
    _fail,
    _git_commit,
    _load_protocol,
    _out,
    _split_csv,
    app,
)
from provael.config import RunConfig
from provael.defenses.measure import MitigationReport
from provael.policies.lerobot_adapter import IncompatiblePolicyError, MissingLeRobotError
from provael.report import (
    load_report,
    render_summary,
    write_report,
)
from provael.runner import run
from provael.types import ComponentProfile


@app.command()
def certify(
    in_dir: Annotated[
        Path | None,
        typer.Option("--in", help="Directory with a prior report.json. Omit to run a stub."),
    ] = None,
    profile: Annotated[
        CertifyProfile,
        typer.Option("--profile", help="Which Machinery conformity pack to emit."),
    ] = CertifyProfile.annex_i_part_a,
    component_metadata: Annotated[
        Path | None,
        typer.Option(
            "--component-metadata",
            help="Operator ComponentProfile JSON (identity / intended use / operating envelope).",
        ),
    ] = None,
    policy: Annotated[str, typer.Option(help="Policy to run (when --in is omitted).")] = "stub",
    suite: Annotated[str, typer.Option(help="Suite to run (when --in is omitted).")] = "stub",
    attacks: Annotated[
        str, typer.Option(help="Attacks to run when --in is omitted. Keep 'none' for the control.")
    ] = "none,instruction",
    episodes: Annotated[int, typer.Option(min=1, help="Episodes per (task, attack) pair.")] = 10,
    seed: Annotated[int, typer.Option(min=0, help="Base random seed.")] = 0,
    calib: Annotated[
        Path | None, typer.Option("--calib", help="Calibration dir (from `provael calibrate`).")
    ] = None,
    commit: Annotated[
        str | None, typer.Option("--commit", help="Override the source commit stamp.")
    ] = None,
    out: Annotated[
        Path, typer.Option(help="Output directory for the dossier bundle.")
    ] = Path("runs/certify"),
    include_crosswalk: Annotated[
        bool,
        typer.Option(
            "--include-crosswalk",
            help="Append the EAI ↔ RoboJailBench taxonomy-crosswalk appendix (Annex I Part A).",
        ),
    ] = False,
    mitigation: Annotated[
        Path | None,
        typer.Option(
            "--mitigation",
            help="report.mitigation.json from `provael mitigation`, to state the protective "
            "measure and its measured effect. Omit and the dossier says so explicitly.",
        ),
    ] = None,
    protocol: Annotated[
        Path | None,
        typer.Option(
            "--protocol",
            help="Acceptance protocol (YAML/JSON) the dossier's release decision is made against. "
            "Without it a prior run's report.decision.json is used when present, else the "
            "dossier states the run was not assessed.",
        ),
    ] = None,
) -> None:
    """Emit a Machinery Regulation conformity-assessment evidence dossier (JSON + OSCAL + HTML).

    The dossier is EVIDENCE INPUT to a conformity assessment — it is NOT a conformity assessment,
    and Provael is not a notified body. `--profile annex-i-part-a` (default) targets the Annex I
    Part A route for ML self-evolving-behaviour safety components; `--profile annex-iii` emits the
    Annex III EHSR pack. The HTML is the human artifact: open it and print / save as PDF.
    """
    if in_dir is not None:
        try:
            report = load_report(in_dir)
        except FileNotFoundError as exc:
            _fail(str(exc))
            return
        except ValidationError:
            _fail(f"{in_dir} does not contain a valid Provael report.json")
            return
        decision = _decision_for(in_dir, report, protocol)
    else:
        acceptance = _load_protocol(protocol)
        calibrations = load_calibrations(calib, policy, suite) if calib is not None else None
        try:
            config = RunConfig(
                policy=policy, suite=suite, attacks=_split_csv(attacks) or ["none", "instruction"],
                episodes=episodes, seed=seed, out=out,
            )
            report = run(config, calibrations)
        except (MissingLeRobotError, IncompatiblePolicyError, NotImplementedError) as exc:
            _fail(str(exc))
            return
        except KeyError as exc:
            _fail(str(exc).strip('"'))
            return
        decision = _decide(report, acceptance)
        write_report(report, out, decision)

    component: ComponentProfile | None = None
    if component_metadata is not None:
        try:
            component = ComponentProfile.model_validate_json(
                component_metadata.read_text(encoding="utf-8")
            )
        except FileNotFoundError:
            _fail(f"{component_metadata} not found")
            return
        except ValidationError as exc:
            _fail(f"{component_metadata} is not valid ComponentProfile JSON: {exc}")
            return

    # The protective measure. Absent is FINE and is not silent: the dossier renders a
    # risk_reduction_measures section saying no measure was measured, because an absent section
    # reads as covered.
    mitigation_report: MitigationReport | None = None
    if mitigation is not None:
        try:
            mitigation_report = MitigationReport.model_validate_json(
                mitigation.read_text(encoding="utf-8")
            )
        except FileNotFoundError:
            _fail(f"{mitigation} not found")
            return
        except ValidationError as exc:
            _fail(f"{mitigation} is not a valid report.mitigation.json: {exc}")
            return

    issued_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp = commit or _git_commit() or f"v{__version__}"
    paths = write_dossier(
        report, out, profile=profile, issued_at=issued_at, commit=stamp, component=component,
        include_crosswalk=include_crosswalk, mitigation=mitigation_report, decision=decision,
    )

    render_summary(report, _out)
    _out.print("\n[bold]Conformity-assessment evidence dossier[/bold]")
    _out.print(f"  profile   : {profile.value}")
    _out.print(f"  subject   : {report.policy} x {report.suite}")
    _out.print(f"  issued_at : {issued_at}   commit: {stamp}")
    _out.print("  instrument: EU Machinery Reg 2023/1230 — applies 2027-01-20")
    _out.print(
        f"\nWrote [cyan]{paths['json']}[/cyan], [cyan]{paths['oscal']}[/cyan], "
        f"and [cyan]{paths['html']}[/cyan]"
    )
    _out.print(f"Human artifact: open [bold]{paths['html']}[/bold] and print / save as PDF.")
    _err.print(
        "[yellow]note:[/yellow] evidence input to a conformity assessment — NOT a conformity "
        "assessment; Provael is not a notified body. Do not represent it as certification."
    )
    if component is None:
        _err.print(
            "[yellow]note:[/yellow] no --component-metadata supplied; operator identity / "
            "intended-use / envelope fields are left for the operator to complete."
        )
    if report.policy == "stub" or report.suite == "stub":
        _err.print(
            "[yellow]note:[/yellow] stub numbers are properties of the deterministic fixture, "
            "not a real VLA. Certify a real run for a transfer measurement."
        )
