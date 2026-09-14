"""`report`, `transfer-test` and `export`: turn a finished run into something a reader consumes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.table import Table

from provael.avid import to_avid_json, write_avid
from provael.cli._shared import (
    ExportFormat,
    OutputFormat,
    _err,
    _fail,
    _family_transfer_tests,
    _out,
    _report_baseline,
    app,
)
from provael.compliance import (
    to_compliance_json,
    write_compliance_json,
    write_compliance_markdown,
)
from provael.mlbom import to_ml_bom_json, write_ml_bom
from provael.oscal import to_oscal_json, write_oscal
from provael.regression import DEFAULT_TOLERANCE
from provael.report import (
    load_report,
    render_summary,
)
from provael.sarif import to_sarif_json, write_sarif
from provael.scorecard import to_scorecard_markdown, write_scorecard


@app.command()
def report(
    in_dir: Annotated[Path, typer.Option("--in", help="Directory containing report.json.")],
    fmt: Annotated[
        OutputFormat,
        typer.Option(
            "--format",
            help=(
                "Output: 'table', 'sarif', 'compliance', 'scorecard', 'oscal', 'mlbom', or "
                "'test-report' (ISO/IEC 17025 clause-7.8-shaped Markdown; not accredited)."
            ),
        ),
    ] = OutputFormat.table,
    threshold: Annotated[
        float,
        typer.Option(min=0.0, max=1.0, help="ASR pass/fail threshold for --format scorecard."),
    ] = 0.5,
    out: Annotated[
        Path | None,
        typer.Option(
            "--out",
            help="With --format sarif/compliance, write here instead of stdout. For "
            "compliance, a '.md' suffix writes the human-readable report, else JSON. With "
            "--baseline, writes the diff (a '.md' suffix writes Markdown, else JSON).",
        ),
    ] = None,
    baseline: Annotated[
        Path | None,
        typer.Option(
            "--baseline",
            help="A known-good report.json to diff against (per-checkpoint regression gate). "
            "Exits non-zero if the candidate regressed.",
        ),
    ] = None,
    regression_tolerance: Annotated[
        float,
        typer.Option(
            "--regression-tolerance", min=0.0, max=1.0,
            help="ASR rise allowed before a regression can trip (with --baseline).",
        ),
    ] = DEFAULT_TOLERANCE,
    sarif_out: Annotated[
        Path | None,
        typer.Option("--sarif-out", help="With --baseline, write a regression SARIF here."),
    ] = None,
    attest_out: Annotated[
        Path | None,
        typer.Option(
            "--attest-out",
            help="With --baseline, write a signed regression attestation here — a tamper-evident, "
            "offline-verifiable envelope binding the diff + SARIF + summary under one Ed25519 "
            "signature (the artifact a safety case references).",
        ),
    ] = None,
    key: Annotated[
        Path | None,
        typer.Option(
            "--key",
            help="Ed25519 private-key PEM to sign the regression attestation with. Falls back to "
            "the PROVAEL_SIGNING_KEY env (PEM contents); omit both for an ephemeral key.",
        ),
    ] = None,
    no_sign: Annotated[
        bool,
        typer.Option(
            "--no-sign", help="With --attest-out, emit a digest-only bundle (no signature)."
        ),
    ] = False,
) -> None:
    """Print a summary of a previously written report, or emit it as SARIF / compliance evidence."""
    try:
        loaded = load_report(in_dir)
    except FileNotFoundError as exc:
        _fail(str(exc))
        return
    except ValidationError:
        _fail(f"{in_dir} does not contain a valid Provael report.json")
        return
    if baseline is not None:
        _report_baseline(
            loaded, baseline, regression_tolerance, out, sarif_out, attest_out, key, no_sign
        )
        return
    if fmt is OutputFormat.sarif:
        if out is not None:
            write_sarif(loaded, out)
            _out.print(f"Wrote [cyan]{out}[/cyan]  (SARIF 2.1.0)")
        else:
            print(to_sarif_json(loaded))  # machine-readable SARIF to stdout
        return
    if fmt is OutputFormat.compliance:
        if out is None:
            print(to_compliance_json(loaded))  # machine-readable evidence JSON to stdout
        elif out.suffix.lower() == ".md":
            write_compliance_markdown(loaded, out)
            _out.print(f"Wrote [cyan]{out}[/cyan]  (compliance evidence, Markdown)")
        else:
            write_compliance_json(loaded, out)
            _out.print(f"Wrote [cyan]{out}[/cyan]  (compliance evidence, JSON)")
        return
    if fmt is OutputFormat.scorecard:
        if out is not None:
            write_scorecard(loaded, out, threshold)
            _out.print(f"Wrote [cyan]{out}[/cyan]  (pre-deployment ASR scorecard)")
        else:
            print(to_scorecard_markdown(loaded, threshold))  # one-page Markdown to stdout
        return
    if fmt is OutputFormat.oscal:
        if out is not None:
            write_oscal(loaded, out)
            _out.print(f"Wrote [cyan]{out}[/cyan]  (OSCAL assessment-results)")
        else:
            print(to_oscal_json(loaded))  # machine-readable OSCAL to stdout
        return
    if fmt is OutputFormat.test_report:
        from provael.test_report import load_manifest, to_test_report_markdown, write_test_report

        manifest = load_manifest(in_dir)
        if out is not None:
            write_test_report(loaded, out, manifest)
            note = "with" if manifest is not None else "WITHOUT"
            _out.print(
                f"Wrote [cyan]{out}[/cyan]  (clause-7.8-shaped test report, {note} manifest)"
            )
        else:
            print(to_test_report_markdown(loaded, manifest))
        return
    if fmt is OutputFormat.mlbom:
        if out is not None:
            write_ml_bom(loaded, out)
            _out.print(f"Wrote [cyan]{out}[/cyan]  (CycloneDX ML-BOM)")
        else:
            print(to_ml_bom_json(loaded))  # machine-readable ML-BOM to stdout
        return
    render_summary(loaded, _out)


@app.command("transfer-test")
def transfer_test_cmd(
    in_dir: Annotated[Path, typer.Option("--in", help="Directory containing report.json.")],
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Write a byte-stable transfer-test JSON here, not a table."),
    ] = None,
) -> None:
    """Print each family's transfer-test: rate + 95% Wilson CI + benign control + transfer-status.

    Every family carries its honest ``transfer-status``: ``real-transfer`` for a real policy x
    suite, ``stub-scaffolding`` on the deterministic CPU stub (reported as-is, no cross-model
    claim).
    """
    try:
        loaded = load_report(in_dir)
    except FileNotFoundError as exc:
        _fail(str(exc))
        return
    except ValidationError:
        _fail(f"{in_dir} does not contain a valid Provael report.json")
        return

    tests = _family_transfer_tests(loaded)
    if out is not None:
        payload = {
            "policy": loaded.policy,
            "suite": loaded.suite,
            "tool_version": loaded.tool_version,
            "transfer_tests": [json.loads(t.model_dump_json()) for t in tests],
        }
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _out.print(f"Wrote [cyan]{out}[/cyan]  (transfer-test evidence, JSON)")
        return

    table = Table(title=f"Transfer-test  ({loaded.policy} x {loaded.suite})")
    table.add_column("family", style="cyan", no_wrap=True)
    table.add_column("rate (95% CI)", justify="right")
    table.add_column("benign FPR", justify="right")
    table.add_column("n", justify="right")
    table.add_column("transfer-status", style="magenta")
    for t in tests:
        ci = "" if t.ci95 is None else f" [{100.0 * t.ci95[0]:.0f}-{100.0 * t.ci95[1]:.0f}%]"
        benign = "n/a" if t.benign_fpr is None else f"{100.0 * t.benign_fpr:.1f}%"
        if t.benign_n:
            benign += f" ({t.benign_successes}/{t.benign_n})"
        if t.benign_ci95 is not None:
            benign += f" [{100.0 * t.benign_ci95[0]:.0f}-{100.0 * t.benign_ci95[1]:.0f}%]"
        table.add_row(
            t.family, f"{100.0 * t.rate:.1f}%{ci}", benign, str(t.n), t.transfer_status
        )
    _out.print(table)
    if loaded.policy == "stub" or loaded.suite == "stub":
        _err.print(
            "[yellow]note:[/yellow] stub-scaffolding — rates are properties of the deterministic "
            "fixture, not a real VLA. The real SmolVLA x LIBERO transfer is GPU-gated."
        )


@app.command()
def export(
    in_dir: Annotated[Path, typer.Option("--in", help="Directory containing report.json.")],
    fmt: Annotated[
        ExportFormat,
        typer.Option(
            "--format",
            help="'avid' (evidence-graph record) or 'hf-eval' (Hugging Face .eval_results YAML).",
        ),
    ] = ExportFormat.avid,
    out: Annotated[
        Path | None, typer.Option("--out", help="Write here instead of stdout.")
    ] = None,
    dataset: Annotated[
        str | None,
        typer.Option(
            "--dataset",
            help="hf-eval only: the Hub dataset id registered as the benchmark (required).",
        ),
    ] = None,
    source_url: Annotated[
        str | None,
        typer.Option(
            "--source-url",
            help="hf-eval only: URL of the committed results directory the entries point at.",
        ),
    ] = None,
) -> None:
    """Export a run into an external database's format: an AVID record, or Hugging Face
    Community Evals entries (`.eval_results/*.yaml`, one per measured arm).

    Submitting the file — to AVID, or as a pull request on the model's Hub repo — is an external
    action; this only produces it. Nothing here emits a `verifyToken`: that badge is reserved for
    HF Jobs runs with inspect-ai, which provael is not.
    """
    try:
        loaded = load_report(in_dir)
    except FileNotFoundError as exc:
        _fail(str(exc))
        return
    except ValidationError:
        _fail(f"{in_dir} does not contain a valid Provael report.json")
        return
    if fmt is ExportFormat.hf_eval:
        from provael.hf_eval import to_eval_results_yaml, write_eval_results
        from provael.test_report import load_manifest

        if not dataset:
            _fail("--format hf-eval needs --dataset <hub dataset id> (the registered benchmark)")
            return
        manifest = load_manifest(in_dir)
        if out is not None:
            write_eval_results(loaded, dataset, out, manifest=manifest, source_url=source_url)
            _out.print(f"Wrote [cyan]{out}[/cyan]  (Hugging Face .eval_results entries)")
        else:
            print(to_eval_results_yaml(loaded, dataset, manifest=manifest, source_url=source_url))
        return
    if out is not None:
        write_avid(loaded, out)
        _out.print(f"Wrote [cyan]{out}[/cyan]  (AVID record)")
    else:
        print(to_avid_json(loaded))


@app.command("compose-video")
def compose_video(
    left: Annotated[Path, typer.Argument(help="Clip for the left half (e.g. the benign twin).")],
    right: Annotated[
        Path, typer.Argument(help="Clip for the right half (e.g. the attacked episode).")
    ],
    out: Annotated[Path, typer.Option("--out", help="Where to write the composed MP4.")],
) -> None:
    """Put two episode clips side by side, step-aligned, into one MP4.

    The clips come from `provael attack --video-dir`; pair the benign and the attacked episode of
    the same task and seed so the divergence is visible at the step it happens. Needs the
    `[lerobot]` extra's imageio + ffmpeg; the CPU core does not ship them.
    """
    from provael.video import compose_side_by_side

    try:
        frames = compose_side_by_side(left, right, out)
    except (FileNotFoundError, ValueError, ImportError) as exc:
        _fail(str(exc))
        return
    _out.print(f"Wrote [cyan]{out}[/cyan]  ({frames} frames)")
