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

import hashlib
import json
import os
import platform
import re
import subprocess
from collections.abc import Sequence
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
from provael.verdict import (
    AcceptanceProtocol,
    ReleaseDecision,
    load_decision,
    release_verdict,
)


class OutputFormat(StrEnum):
    """Console / artifact output format for ``attack`` and ``report``."""

    table = "table"
    sarif = "sarif"
    compliance = "compliance"
    scorecard = "scorecard"
    oscal = "oscal"
    mlbom = "mlbom"
    test_report = "test-report"


class ExportFormat(StrEnum):
    """Evidence-graph export formats for ``provael export``."""

    avid = "avid"
    hf_eval = "hf-eval"


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


#: Explicit repository override for the same containers. A wheel installed from PyPI has no remote
#: to read, so the driver states which repository's release it is running.
REPOSITORY_ENV = "PROVAEL_REPOSITORY"
_REPO_SLUG = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
#: Explicit dependency-lock digest override; the value is recorded verbatim after a shape check.
DEP_LOCK_ENV = "PROVAEL_DEP_LOCK_DIGEST"
_DEP_LOCK = re.compile(r"^[a-z0-9_.+-]+:sha256:[0-9a-f]{64}$")


def _repository() -> str | None:
    """``owner/name`` of the code that ran: ``PROVAEL_REPOSITORY`` if set, else the git origin.

    THIS WAS NEVER POPULATED, by any version, in any lane. `execution.py` listed ``repository`` as
    provenance the caller should supply and no caller did, so every manifest ever committed reports
    it under ``missing_fields`` — including the scheduled GPU lane's, whose shards this project now
    promotes into a published number. Read from the same two places ``commit`` is: an explicit
    variable for containers that install from PyPI, else the git checkout. None when neither can
    say, never a guess.
    """
    explicit = os.environ.get(REPOSITORY_ENV, "").strip()
    if _REPO_SLUG.match(explicit):
        return explicit
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],  # noqa: S607 - fixed argv, no user input
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return _repository_slug(result.stdout.strip())


def _repository_slug(remote_url: str) -> str | None:
    """``git@github.com:owner/name.git`` or ``https://host/owner/name(.git)`` -> ``owner/name``."""
    tail = remote_url.rstrip("/")
    if tail.endswith(".git"):
        tail = tail[:-4]
    tail = tail.split(":")[-1] if "@" in tail and "://" not in tail else tail
    parts = [part for part in tail.replace("\\", "/").split("/") if part]
    if len(parts) < 2:
        return None
    slug = f"{parts[-2]}/{parts[-1]}"
    return slug if _REPO_SLUG.match(slug) else None


def _dep_lock_digest() -> str | None:
    """A digest of the dependency set that ran, labelled with what it digests.

    Three sources, in order, and the label says which so a reader is never left to guess:

    * ``PROVAEL_DEP_LOCK_DIGEST`` — an explicit ``<source>:sha256:<hex>`` value, taken verbatim
      after a shape check.
    * ``uv.lock:sha256:<hex>`` — the lock file of the checkout this process runs from, when there
      is one. A committed lock is the strongest statement of what was resolved.
    * ``installed:sha256:<hex>`` — the sorted ``name==version`` list of every distribution the
      running interpreter can see. This is what a container that pip-installed a release actually
      ran, and it is the case the scheduled GPU lane is in: no checkout, no lock file, and a
      reproducibility claim that was going unrecorded.

    ``installed`` is a digest of a fact about this process, not a guess, so the field is never left
    empty on a working interpreter — and two runs that share it ran the same package set.
    """
    explicit = os.environ.get(DEP_LOCK_ENV, "").strip().lower()
    if _DEP_LOCK.match(explicit):
        return explicit
    for base in (Path.cwd(), *Path.cwd().parents):
        lock = base / "uv.lock"
        if lock.is_file():
            return f"uv.lock:sha256:{hashlib.sha256(lock.read_bytes()).hexdigest()}"
        if (base / ".git").exists():
            break  # the checkout root without a lock file: fall through to the installed set
    try:
        from importlib import metadata

        pins = sorted(
            f"{(d.metadata['Name'] or '').strip().lower()}=={d.version}"
            for d in metadata.distributions()
            if d.metadata["Name"]
        )
    except Exception:  # noqa: BLE001 - a broken metadata walk is "unknown", never invented
        return None
    if not pins:
        return None
    return f"installed:sha256:{hashlib.sha256('\n'.join(pins).encode('utf-8')).hexdigest()}"


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
    report: RunReport,
    out_dir: Path,
    *,
    elapsed: float,
    defense: str | None = None,
    decision: ReleaseDecision | None = None,
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
    # The manifest's checkpoint fields come from the DEPLOYED identity the adapter resolved
    # (issue #227), not from the request — they were never filled before, because nothing
    # resolved them.
    deployed = report.deployed_policy
    manifest = build_execution_manifest(
        report,
        run_id=f"{report.policy}-{report.suite}-{end.strftime(fmt)}",
        package_version=__version__,
        protocol_version="provael-redteam/v1",
        defense=defense,
        repository=_repository(),
        checkpoint_repo=deployed.checkpoint if deployed is not None else None,
        checkpoint_revision=deployed.checkpoint_revision if deployed is not None else None,
        commit=_git_commit(),
        dep_lock_digest=_dep_lock_digest(),
        python_version=platform.python_version(),
        os_name=f"{platform.system()} {platform.release()}",
        hardware=_hardware_string(),
        started_at=start.strftime(fmt),
        ended_at=end.strftime(fmt),
        env=dict(os.environ),
        decision=decision,
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


def _load_protocol(path: Path | None) -> AcceptanceProtocol | None:
    """Load the acceptance protocol at ``path``, or None when none was named.

    A protocol that does not load is a hard error: the caller must not fall back to "not
    assessed" when the operator asked for a decision. ``_fail`` exits the process; the ``None``
    return after it is for the type checker (the CLI tests run in-process).
    """
    if path is None:
        return None
    try:
        return AcceptanceProtocol.load(path)
    except FileNotFoundError:
        _fail(f"no acceptance protocol at {path}")
    except (ValidationError, ValueError) as exc:
        _fail(f"{path} is not a valid acceptance protocol: {exc}")
    return None


def _decide(report: RunReport, protocol: AcceptanceProtocol | None) -> ReleaseDecision:
    """The ONE release decision a command makes, passed to every emitter it writes.

    The decision time is the wall clock, which is fine here because the decision is a sidecar and
    never part of ``report.json``; it is what an exception's expiry is judged against.
    """
    try:
        return release_verdict(report, protocol, as_of=datetime.now(UTC))
    except ValueError as exc:
        _fail(str(exc))
    return release_verdict(report)


def _critical_attacks(protocol: Path | None) -> list[str]:
    """The attacks the protocol at ``protocol`` names as critical, for the regression gate."""
    acceptance = _load_protocol(protocol)
    if acceptance is None:
        return []
    return sorted(acceptance.requirements.critical_attacks)


def _decision_for(run_dir: Path, report: RunReport, protocol: Path | None) -> ReleaseDecision:
    """A decision for a loaded run: from ``--protocol`` if given, else the run's sidecar, else none.

    Re-deciding under a newly named protocol beats a stale sidecar; a sidecar beats nothing. A run
    with neither is rendered as not assessed, which is the truth about it.
    """
    acceptance = _load_protocol(protocol)
    if acceptance is not None:
        return _decide(report, acceptance)
    stored = load_decision(run_dir)
    return stored if stored is not None else release_verdict(report)


def _report_baseline(
    candidate_report: RunReport, baseline: Path, tolerance: float,
    out: Path | None, sarif_out: Path | None,
    attest_out: Path | None = None, key: Path | None = None, no_sign: bool = False,
    critical_attacks: Sequence[str] = (),
) -> None:
    """Run the per-checkpoint regression diff and exit non-zero if the candidate regressed.

    ``critical_attacks`` (from the acceptance protocol) are gated on their own slices, so a critical
    arm regressing under a flat aggregate is a regression here too.
    """
    try:
        baseline_report = load_report(baseline)
    except FileNotFoundError as exc:
        _fail(str(exc))
        return
    except ValidationError:
        _fail(f"{baseline} is not a valid Provael report.json")
        return

    diff: RegressionDiff = diff_reports(
        candidate_report, baseline_report, tolerance, critical_attacks=critical_attacks
    )

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
    critical_rows = {s.key: s for s in diff.by_attack if s.key in diff.critical_attacks}
    for name in diff.critical_attacks:
        if name in critical_rows:
            table.add_row(*_diff_row(critical_rows[name]))
        else:
            table.add_row(f"critical: {name}", "n/a", "n/a", "n/a", "not measured")
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
        critical = (
            f" Critical regression: {', '.join(diff.critical_regressed)}."
            if diff.critical_regressed
            else ""
        )
        _fail(
            f"regression: {diff.overall.reason}. Regressed slices: "
            f"{', '.join(diff.regressed_keys)}.{critical}",
            code=1,
        )
    if diff.critical_unmeasured:
        _err.print(
            f"[yellow]note:[/yellow] critical attack(s) not comparable (no data on one side): "
            f"{', '.join(diff.critical_unmeasured)} — not shown to be safe."
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






