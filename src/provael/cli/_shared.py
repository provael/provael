"""The Typer apps, the two consoles, and the helpers the command modules share.

WHAT LIVES HERE, AND WHAT DELIBERATELY DOES NOT. This file was `cli.py` — 3,057 lines and every
command (issue #193). The commands moved out into one module per subject; what stayed is the
things more than one of them needs: `app`, `leaderboard_app` and `study_app`; the stdout/stderr
consoles; the `--version` callback; and the private helpers that write an execution manifest,
resolve a defense from one, or render a leaderboard.

NOTHING HERE REGISTERS A COMMAND. That is the property to preserve when adding to this file: a
`@app.command` here would register before every module in `__init__`'s import list, because
`_shared` is imported first by all of them — so it would jump to the front of `provael --help`
without anyone touching the import list. `tests/test_cli_surface.py` would catch it, but the
reason it happened would not be obvious from the diff.
"""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from provael import __version__
from provael.attacks.baseline import FAMILY as BASELINE_FAMILY
from provael.calibration import transfer_test
from provael.crosswalk import (
    ATLAS_TARGET,
    CROSSWALK_TARGET,
    FORESIGHT_TARGET,
    SAFEVLA_TARGET,
    VLA_ARENA_TARGET,
)
from provael.leaderboard import (
    THIRD_PARTY_SUBMISSION,
    Leaderboard,
    LeaderboardRow,
)
from provael.policies.registry import (
    STATUS_FIXTURE,
    STATUS_MEASURED,
    STATUS_SCAFFOLDING,
    STATUS_UNRUN,
)
from provael.regression import (
    RegressionDiff,
    SliceDelta,
    build_regression_attestation,
    diff_reports,
    write_diff_json,
    write_diff_markdown,
    write_regression_attestation,
    write_regression_sarif,
)
from provael.report import load_report
from provael.scoring.asr import by_family
from provael.types import RunReport, TransferTest


class OutputFormat(StrEnum):
    """Console / artifact output format for ``attack`` and ``report``."""

    table = "table"
    sarif = "sarif"
    compliance = "compliance"
    scorecard = "scorecard"
    oscal = "oscal"
    mlbom = "mlbom"


class ExportFormat(StrEnum):
    """Evidence-graph export formats for ``provael export``."""

    avid = "avid"


class CrosswalkTarget(StrEnum):
    """Taxonomy a ``provael crosswalk`` maps the Embodied AI Security Top 10 against."""

    robojailbench = CROSSWALK_TARGET
    atlas = ATLAS_TARGET
    foresight = FORESIGHT_TARGET
    vla_arena = VLA_ARENA_TARGET
    safevla = SAFEVLA_TARGET


class CrosswalkFormat(StrEnum):
    """Output format for ``provael crosswalk``."""

    json = "json"
    md = "md"


app = typer.Typer(
    name="provael",
    help="Provael — red-team open Vision-Language-Action (VLA) robot policies in simulation.",
    no_args_is_help=True,
    add_completion=False,
)

leaderboard_app = typer.Typer(
    help="Aggregate run reports into a ranked ASR leaderboard.",
    no_args_is_help=True,
)
app.add_typer(leaderboard_app, name="leaderboard")

study_app = typer.Typer(
    help="Reproducible red-team studies (sim-only; CPU-stub deterministic, real paths gated).",
    no_args_is_help=True,
)
app.add_typer(study_app, name="study")

_out = Console()
_err = Console(stderr=True)


def _fail(message: str, code: int = 2) -> None:
    """Print a clean error line to stderr and exit with ``code``.

    The message is Rich-escaped so substrings like ``[lerobot]`` are printed
    literally instead of being parsed as console markup.
    """
    _err.print(f"[bold red]Error:[/bold red] {escape(message)}")
    raise typer.Exit(code)


def _split_csv(value: str | None) -> list[str] | None:
    """Parse a comma-separated option value into a clean list (or None)."""
    if value is None:
        return None
    items = [tok.strip() for tok in value.split(",") if tok.strip()]
    return items or None


#: Explicit provenance override for containers that install provael from PyPI and have no git
#: checkout — the Modal GPU lanes. Both scheduled-GPU manifests committed in September 2026 carried
#: `commit: null` for exactly that reason. The driver resolves the pinned release tag's commit on
#: the GitHub runner and passes it in; the value is validated as a hex SHA so a stray string cannot
#: masquerade as provenance. Same variable the hosted server already reads.
COMMIT_ENV = "PROVAEL_COMMIT"
_SHA = re.compile(r"^[0-9a-f]{7,40}$")


def _git_commit() -> str | None:
    """Commit SHA for the manifest: ``PROVAEL_COMMIT`` if set and hex-shaped, else the checkout's.

    Returns None outside a git checkout when no override is present — never a guess.
    """
    explicit = os.environ.get(COMMIT_ENV, "").strip().lower()
    if _SHA.match(explicit):
        return explicit
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607 - fixed argv, no user input; resolving git absolutely would break every non-standard install
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = result.stdout.strip()
    return sha if result.returncode == 0 and sha else None


def _hardware_string() -> str | None:
    """What the run executed on, as specifically as this process can honestly tell.

    ``platform.machine()`` alone said ``x86_64`` for every run ever recorded, which names nothing:
    the L4 that produced the published result and a laptop share it. The accelerator is what a
    reader needs, so when torch is importable and a CUDA device is visible its name and memory are
    appended, with the CPU count beside them (the simulator is CPU work and the throughput depends
    on it). torch is imported lazily and every failure degrades to the plain machine string — the
    CPU build must never grow a torch dependency to write a manifest.
    """
    parts = [platform.machine() or "unknown-arch"]
    cpus = os.cpu_count()
    if cpus:
        parts.append(f"cpu={cpus}")
    try:
        import torch  # noqa: PLC0415 - optional, lazy by design

        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            parts.append(f"gpu={props.name} ({props.total_memory // (1024 * 1024)} MiB)")
    except Exception as exc:  # noqa: BLE001 - any torch/CUDA failure is "no accelerator known"
        parts.append(f"gpu=unknown ({type(exc).__name__})")
    return "; ".join(parts)


def _emit_execution_manifest(
    report: RunReport, out_dir: Path, *, elapsed: float, defense: str | None = None
) -> None:
    """Write execution-manifest.json (runtime provenance) beside the deterministic report.json.

    The manifest carries the wall-clock, OS/Python, commit, and (redacted) environment that must
    NOT enter report.json; it is bound to the report by the report's canonical digest.
    """
    from datetime import timedelta

    from provael.execution import build_execution_manifest, to_execution_manifest_json

    end = datetime.now(UTC)
    start = end - timedelta(seconds=elapsed)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    manifest = build_execution_manifest(
        report,
        run_id=f"{report.policy}-{report.suite}-{end.strftime(fmt)}",
        package_version=__version__,
        protocol_version="provael-redteam/v1",
        defense=defense,
        commit=_git_commit(),
        python_version=platform.python_version(),
        os_name=f"{platform.system()} {platform.release()}",
        hardware=_hardware_string(),
        started_at=start.strftime(fmt),
        ended_at=end.strftime(fmt),
        env=dict(os.environ),
    )
    # Name from provael.watch, not a literal: the freshness badge reads this exact file, and a
    # drift between the two halves makes every future measurement invisible to it.
    from provael.watch import EXECUTION_MANIFEST

    (out_dir / EXECUTION_MANIFEST).write_text(
        to_execution_manifest_json(manifest), encoding="utf-8"
    )


def _defense_from_manifest(run_dir: Path) -> str | None:
    """Read the defense name from a run's execution manifest.

    The manifest is where the defense identity lives (report.json deliberately does not carry it),
    so this is the authoritative source rather than asking the operator to retype it.
    """
    path = run_dir / "execution-manifest.json"
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("defense")
    except (OSError, json.JSONDecodeError):
        return None
    return str(value) if value else None


def _write_defense_log(rows: list[dict[str, str]], out_dir: Path) -> Path:
    """Write the defense's raw -> canonical audit trail as a JSONL sidecar.

    A SIDECAR, deliberately. docs/defenses.md requires the canonical form to be "logged next to the
    raw instruction", and the obvious place — a field on AttackResult — is exactly the place it must
    not go: AttackResult is nested in RunReport.results, so a field there moves the canonical JSON
    the attestation is signed over. JSONL so it stays greppable and diffable at any run size.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "defense-log.jsonl"
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )
    return path




def _version_flag(value: bool) -> None:
    """Eager ``--version`` callback: print and exit before any subcommand is resolved."""
    if value:
        _out.print(f"provael (provael) {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    _version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_flag,
            is_eager=True,
            help="Print the Provael version and exit.",
        ),
    ] = False,
) -> None:
    """Provael — red-team open Vision-Language-Action (VLA) robot policies in simulation.

    ``--version`` mirrors the ``version`` subcommand. Both exist because ``--version`` is what
    everyone reaches for first (and what the documented smoke test in the release checklist
    calls), while the subcommand is what scripts already pin to.
    """








#: How each status renders. Colour carries the warning a skim-reader takes from the table: only a
#: measured backend is green, because only a measured backend has ever produced a real number.
_POLICY_STATUS_STYLE = {
    STATUS_MEASURED: "green",
    STATUS_FIXTURE: "cyan",
    STATUS_SCAFFOLDING: "red",
    STATUS_UNRUN: "yellow",
}


















def _diff_row(s: SliceDelta) -> tuple[str, str, str, str, str]:
    def rate(asr: float | None, ci: tuple[float, float] | None) -> str:
        if asr is None or ci is None:
            return "n/a"
        return f"{100.0 * asr:.1f}% [{100.0 * ci[0]:.0f}-{100.0 * ci[1]:.0f}%]"
    delta = "n/a" if s.delta is None else f"{s.delta:+.1%}"
    flag = "[bold red]REGRESSED[/bold red]" if s.regressed else "[green]ok[/green]"
    return (s.label, rate(s.baseline_asr, s.baseline_ci),
            rate(s.candidate_asr, s.candidate_ci), delta, flag)


def _emit_regression_attestation(
    diff: RegressionDiff, candidate: RunReport, attest_out: Path, key: Path | None, no_sign: bool
) -> None:
    """Write a signed (or digest-only) regression attestation next to the diff."""
    issued_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp = _git_commit() or f"v{__version__}"
    private_key_pem: bytes | None = None
    if key is not None:
        private_key_pem = key.read_bytes()
    else:
        env_key = os.environ.get("PROVAEL_SIGNING_KEY")
        if env_key:
            private_key_pem = env_key.encode("utf-8")
    att = build_regression_attestation(
        diff, candidate, issued_at=issued_at, commit=stamp,
        private_key_pem=private_key_pem, sign=not no_sign,
    )
    write_regression_attestation(att, attest_out)
    if att.signed:
        _out.print(
            f"Wrote [cyan]{attest_out}[/cyan]  (signed regression attestation, "
            f"ed25519 keyid {att.signatures[0].keyid})"
        )
        if private_key_pem is None:
            _err.print(
                "[yellow]note:[/yellow] signed with an ephemeral key (integrity, not identity). "
                "Pass --key <ed25519.pem> or set PROVAEL_SIGNING_KEY to sign with your org key."
            )
    else:
        _out.print(f"Wrote [cyan]{attest_out}[/cyan]  (digest-only regression attestation)")


def _report_baseline(
    candidate_report: RunReport, baseline: Path, tolerance: float,
    out: Path | None, sarif_out: Path | None,
    attest_out: Path | None = None, key: Path | None = None, no_sign: bool = False,
) -> None:
    """Run the per-checkpoint regression diff and exit non-zero if the candidate regressed."""
    try:
        baseline_report = load_report(baseline)
    except FileNotFoundError as exc:
        _fail(str(exc))
        return
    except ValidationError:
        _fail(f"{baseline} is not a valid Provael report.json")
        return

    diff: RegressionDiff = diff_reports(candidate_report, baseline_report, tolerance)

    table = Table(
        title=f"Provael — baseline-regression diff (tolerance {tolerance:.0%})", title_style="bold"
    )
    table.add_column("slice", style="cyan", no_wrap=True)
    table.add_column("baseline ASR", justify="right")
    table.add_column("candidate ASR", justify="right")
    table.add_column("delta", justify="right")
    table.add_column("status", justify="center")
    table.add_row(*_diff_row(diff.overall))
    for s in diff.by_eai:
        table.add_row(*_diff_row(s))
    _out.print(table)

    if out is not None:
        if out.suffix.lower() == ".md":
            write_diff_markdown(diff, out)
        else:
            write_diff_json(diff, out)
        _out.print(f"Wrote [cyan]{out}[/cyan]  (regression diff)")
    if sarif_out is not None:
        write_regression_sarif(diff, candidate_report, sarif_out)
        _out.print(f"Wrote [cyan]{sarif_out}[/cyan]  (regression SARIF)")
    if attest_out is not None:
        _emit_regression_attestation(diff, candidate_report, attest_out, key, no_sign)

    if diff.regressed:
        _fail(
            f"regression: {diff.overall.reason}. Regressed slices: "
            f"{', '.join(diff.regressed_keys)}.",
            code=1,
        )
    _out.print("[green]no regression[/green] past the tolerance with disjoint 95% CIs.")




def _family_transfer_tests(report: RunReport) -> list[TransferTest]:
    """One transfer-test per attack family (baseline excluded — it IS the benign control)."""
    fam_stats = by_family(report.results)
    baseline = fam_stats.get(BASELINE_FAMILY)
    return [
        transfer_test(
            stat, benign=baseline, policy=report.policy, suite=report.suite, family=family
        )
        for family, stat in fam_stats.items()
        if family != BASELINE_FAMILY
    ]
















def _benign_cell(row: LeaderboardRow) -> str:
    """The row's benign control, rendered like its ASR: rate, counts, interval.

    ``"n/a"`` when the row has no baseline arm — never ``"0.0%"``. A board that prints a measured
    zero where no control ran advertises a floor it never established.
    """
    if row.benign_fpr is None:
        return "[dim]n/a[/dim]"
    cell = f"{100.0 * row.benign_fpr:.1f}%"
    if row.benign_attempts:
        cell += f" ({row.benign_successes}/{row.benign_attempts})"
    if row.benign_ci95 is not None:
        cell += f" [{100.0 * row.benign_ci95[0]:.0f}-{100.0 * row.benign_ci95[1]:.0f}%]"
    return cell


def _render_leaderboard(leaderboard: Leaderboard) -> None:
    if leaderboard.is_demo:
        _out.print(
            "[yellow]demo data[/yellow]: stub-policy results only — add real-model "
            "(e.g. SmolVLA) runs for live numbers (see leaderboard/README.md)."
        )
    table = Table(title="Provael — ASR leaderboard (policy x suite x family)", title_style="bold")
    table.add_column("rank", justify="right")
    table.add_column("policy", style="cyan", no_wrap=True)
    table.add_column("suite", style="magenta")
    table.add_column("family")
    table.add_column("ASR (95% CI)", justify="right", style="bold red")
    table.add_column("n", justify="right")
    # The control arm, immediately beside the rate it qualifies. The board is the surface where a
    # number travels furthest from its report, and it published the ASR with an interval and the
    # floor not at all — so the one column a reader needed to judge the gap was the missing one.
    table.add_column("benign FPR (95% CI)", justify="right")
    table.add_column("transfer")
    table.add_column("submitted by")
    for rank, row in enumerate(leaderboard.rows, start=1):
        ci = "" if row.ci95 is None else f" [{100.0 * row.ci95[0]:.0f}-{100.0 * row.ci95[1]:.0f}%]"
        transfer = "[green]real[/green]" if row.transfer_status == "real-transfer" else "stub"
        by = row.submitted_by or "[dim]unattributed[/dim]"
        if row.provenance == THIRD_PARTY_SUBMISSION:
            by = f"[green]{by}[/green]"
        table.add_row(
            str(rank),
            row.policy,
            row.suite,
            row.family,
            f"{100.0 * row.asr:.1f}%{ci}",
            f"{row.successes}/{row.attempts}",
            _benign_cell(row),
            transfer,
            by,
        )
    _out.print(table)
    # The independence line. A board of four rows from one run and a board of four rows from four
    # labs are identical in every other field, so state the difference rather than leaving a reader
    # to infer it from a column of repeated names.
    submitters, independent = leaderboard.submitters(), leaderboard.independent_submitters()
    if not submitters:
        _out.print(
            "[dim]submitters:[/dim] none recorded — every row predates submitter attribution "
            "or was built without it."
        )
    else:
        detail = (
            f"{len(independent)} independent ({', '.join(independent)})"
            if independent
            else "[yellow]0 independent[/yellow] — every row is a maintainer run"
        )
        _out.print(f"[dim]submitters:[/dim] {len(submitters)} ({', '.join(submitters)}) · {detail}")
















#: Where a leaderboard submission lands. The submission is a PR to this repo adding
#: ``results/<name>/`` — the flow CONTRIBUTING-leaderboard.md documents, which the
#: `Leaderboard submission` workflow already validates on arrival.
SUBMISSION_REPO = "provael/provael"




if __name__ == "__main__":  # pragma: no cover
    app()






