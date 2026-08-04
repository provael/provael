"""``provael`` command-line interface.

Commands:
  * ``attack``         — run a red-team evaluation and write a report.
  * ``list-policies``  — show registered policies, whether they're runnable here, and whether a
    real checkpoint has ever been run through them (measured vs. scaffolding).
  * ``list-suites``    — show registered suites, marking CPU fixtures apart from real simulators.
  * ``list-attacks``   — show registered attacks and families.
  * ``report``         — print a previously written report.
  * ``transfer-test``  — per-family rate + 95% Wilson CI + benign control + transfer-status.
  * ``version``        — print the tool version.

Errors that a user can act on (missing ``[lerobot]`` extra, unknown policy / suite /
attack, bad config) are caught and printed as a single clear line with a non-zero
exit code — never a raw traceback.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
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
from provael.assurance import AssuranceProfile, build_assurance
from provael.attacks.baseline import FAMILY as BASELINE_FAMILY
from provael.attacks.registry import (
    available_attacks,
    available_families,
    make_attack,
)
from provael.attest import (
    ATTESTATION_JSON,
    ATTESTATION_PUB,
    EXIT_OK,
    RULESET_VERSION,
    MissingAttestExtraError,
    generate_private_key_pem,
    load_bundle,
    load_trust_store,
    public_key_pem,
    to_bundle,
    verify_bundle,
    verify_exit_code,
    write_bundle,
)
from provael.avid import to_avid_json, write_avid
from provael.calibration import (
    calibrate_suite,
    load_calibrations,
    save_calibration,
    transfer_test,
    wilson_ci,
)
from provael.certify import CertifyProfile, write_dossier
from provael.compliance import (
    COMPLIANCE_JSON,
    to_compliance_json,
    write_compliance_json,
    write_compliance_markdown,
)
from provael.config import RunConfig
from provael.crosswalk import (
    ATLAS_JSON,
    ATLAS_TARGET,
    CROSSWALK_JSON,
    CROSSWALK_TARGET,
    FORESIGHT_JSON,
    FORESIGHT_TARGET,
    to_atlas_json,
    to_atlas_markdown,
    to_crosswalk_json,
    to_crosswalk_markdown,
    to_foresight_json,
    to_foresight_markdown,
)
from provael.defenses.measure import (
    MitigationReport,
    MitigationVerdict,
    build_mitigation_report,
    write_mitigation,
)
from provael.defenses.registry import available_defenses, make_defense
from provael.integrity import INTEGRITY_JSON, IntegrityVerdict, verify_checkpoint
from provael.leaderboard import (
    LEADERBOARD_JSON,
    MAINTAINER_RUN,
    THIRD_PARTY_SUBMISSION,
    UNATTRIBUTED,
    Leaderboard,
    build_leaderboard,
    find_reports,
    load_leaderboard,
    validate_report,
    verify_leaderboard,
)
from provael.manifest import to_evidence_manifest_json
from provael.mlbom import ML_BOM_JSON, to_ml_bom_json, write_ml_bom
from provael.oscal import OSCAL_JSON, to_oscal_json, write_oscal
from provael.policies.lerobot_adapter import IncompatiblePolicyError, MissingLeRobotError
from provael.policies.registry import (
    MEASURED_POLICIES,
    STATUS_FIXTURE,
    STATUS_MEASURED,
    STATUS_SCAFFOLDING,
    STATUS_UNRUN,
    available_policies,
    policy_extra,
    policy_is_ready,
    policy_scaffolding_note,
    policy_status,
)
from provael.recipes import RECIPES, available_recipes, load_recipe
from provael.regression import (
    DEFAULT_TOLERANCE,
    RegressionDiff,
    SliceDelta,
    build_regression_attestation,
    diff_reports,
    write_diff_json,
    write_diff_markdown,
    write_regression_attestation,
    write_regression_sarif,
)
from provael.report import load_report, render_summary, write_report
from provael.reproductions import available_reproductions, get_reproduction
from provael.runner import run
from provael.sarif import to_sarif_json, write_sarif
from provael.scorecard import SCORECARD_MD, to_scorecard_markdown, write_scorecard
from provael.scoring.asr import by_family
from provael.studies.cross_arch import (
    build_eai04_study,
    build_study,
    render_eai04_table,
    render_table,
    write_eai04_study,
    write_study,
)
from provael.suites import KIND_FIXTURE, available_suites, suite_is_ready, suite_kind
from provael.types import ComponentProfile, RunReport, TransferTest
from provael.watch import (
    STALE_DAYS,
    age_days,
    append_measurement,
    latest_measurement,
    write_badge,
)


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


def _git_commit() -> str | None:
    """Best-effort short commit SHA of the working tree, or None outside a git checkout."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = result.stdout.strip()
    return sha if result.returncode == 0 and sha else None


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
        hardware=platform.machine() or None,
        started_at=start.strftime(fmt),
        ended_at=end.strftime(fmt),
        env=dict(os.environ),
    )
    (out_dir / "execution-manifest.json").write_text(
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


@app.command()
def version() -> None:
    """Print the Provael / provael version."""
    _out.print(f"provael (provael) {__version__}")


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


@study_app.command("cross-arch")
def study_cross_arch(
    episodes: Annotated[int, typer.Option(help="Episodes per attack (distinct seeds).")] = 10,
    seed: Annotated[int, typer.Option(help="Base random seed.")] = 0,
    out: Annotated[
        Path | None, typer.Option(help="Write summary.json + per-architecture RunReports here.")
    ] = None,
) -> None:
    """Cross-architecture transfer study: the instruction/visual/injection battery vs SmolVLA + pi0.

    Runs the deterministic CPU-stub battery (no GPU/network) and prints the per-(family x
    architecture) ASR with a 95% Wilson CI and the benign-FPR control. SmolVLA and pi0 stay
    'pending' unless run on the gated real path (PROVAEL_INTEGRATION=1 + the `lerobot` / `openpi`
    extra). Reuses the shipped runner + scoring — no ASR is reimplemented.
    """
    summary, reports = build_study(episodes=episodes, seed=seed)
    render_table(summary, _out)
    if out is not None:
        write_study(summary, reports, out)
        _out.print(f"[green]Wrote[/green] {escape(str(out))}/ (summary.json + per-arch reports)")


@study_app.command("eai04")
def study_eai04(
    episodes: Annotated[int, typer.Option(help="Episodes per attack (distinct seeds).")] = 10,
    seed: Annotated[int, typer.Option(help="Base random seed.")] = 0,
    out: Annotated[
        Path | None, typer.Option(help="Write summary.json + the reference RunReport here.")
    ] = None,
) -> None:
    """EAI04 action-space transfer study: action/action_space vectors × {reach, SmolVLA, pi0}.

    Runs the deterministic CPU ``reach`` keep-out reference (ASR + 95% Wilson CI + benign-FPR +
    Succ-But-Unsafe + BH-FDR + preliminary) and marks the real SmolVLA/pi0 LIBERO legs
    NOT-APPLICABLE: these out-of-band-directive attacks do not reach a real VLA, so no real-policy
    EAI04 transfer is obtainable through this mechanism. Reuses the runner + scoring — no ASR
    reimplemented, no second harness.
    """
    summary, reports = build_eai04_study(episodes=episodes, seed=seed)
    render_eai04_table(summary, _out)
    if out is not None:
        write_eai04_study(summary, reports, out)
        _out.print(f"[green]Wrote[/green] {escape(str(out))}/ (summary.json + reference report)")


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


#: How each status renders. Colour carries the warning a skim-reader takes from the table: only a
#: measured backend is green, because only a measured backend has ever produced a real number.
_POLICY_STATUS_STYLE = {
    STATUS_MEASURED: "green",
    STATUS_FIXTURE: "cyan",
    STATUS_SCAFFOLDING: "red",
    STATUS_UNRUN: "yellow",
}


@app.command("list-policies")
def list_policies() -> None:
    """List registered policies, whether they can run here, and whether they have ever been run."""
    table = Table(title="Policies")
    table.add_column("name", style="cyan", no_wrap=True)
    table.add_column("ready here", justify="center")
    # "Ready" answers "does the dependency import", which is a strictly weaker claim than "this has
    # produced a real number". Without this column all seven non-stub backends render identically,
    # and someone shopping for a `--policy` value cannot tell the one measured backend from the
    # three that have never loaded a checkpoint. An ASR from the latter measures scaffolding.
    table.add_column("status", no_wrap=True)
    table.add_column("notes")
    for name in available_policies():
        extra = policy_extra(name)
        note = escape(f"requires `provael[{extra}]` (GPU)") if extra else "CPU, no deps"
        # An importable dependency is not a run. A scaffolding backend must never render "yes"
        # here: for `groot` the advertised extra does not even provision it, so the import check
        # would be answering for a capability the install cannot deliver.
        scaffolding = policy_scaffolding_note(name)
        if scaffolding is not None:
            mark = "[yellow]no[/yellow]"
            # The `status` column already says "scaffolding"; repeating the word here only steals
            # width from the part a reader needs, which is *why* this one is scaffolding.
            why = scaffolding.removeprefix("scaffolding: ")
            note = f"{note} — {escape(why)}"
        else:
            mark = "[green]yes[/green]" if policy_is_ready(name) else "[yellow]no[/yellow]"
        status = policy_status(name)
        evidence = MEASURED_POLICIES.get(name)
        if evidence is not None:
            note = f"{note} — {escape(evidence)}"
        table.add_row(
            name, mark, f"[{_POLICY_STATUS_STYLE[status]}]{status}[/]", note
        )
    _out.print(table)
    _out.print(
        "[dim]`ready here` = the dependency imports. `status` = whether a real checkpoint has ever "
        "been run and committed. They are different questions.[/dim]"
    )


@app.command("list-suites")
def list_suites() -> None:
    """List registered suites, marking CPU fixtures apart from real simulators."""
    table = Table(title="Suites")
    table.add_column("name", style="cyan", no_wrap=True)
    table.add_column("ready here", justify="center")
    table.add_column("kind", no_wrap=True)
    table.add_column("notes")
    for name in available_suites():
        kind = suite_kind(name)
        fixture = kind == KIND_FIXTURE
        # A fixture is deterministic arithmetic: it embodies nothing, so a rate measured on it is
        # scaffolding regardless of which policy drove it (see evidence.classify_run, which refuses
        # to label such a run `real-episode`). Saying so here is cheaper than discovering it after
        # a number has been quoted.
        note = (
            "deterministic, in-process; no physics — never a real-episode measurement"
            if fixture
            else escape("requires `provael[lerobot]` and a real simulator")
        )
        mark = "[green]yes[/green]" if suite_is_ready(name) else "[yellow]no[/yellow]"
        table.add_row(
            name, mark, f"[{'cyan' if fixture else 'green'}]{kind}[/]", note
        )
    _out.print(table)
    _out.print(
        "[dim]A CPU fixture is reproducible scaffolding, not evidence about a robot. Only a real "
        "simulator produces a `real-episode` run.[/dim]"
    )


@app.command("list-attacks")
def list_attacks() -> None:
    """List registered attacks and attack families."""
    table = Table(title="Attacks")
    table.add_column("attack", style="cyan", no_wrap=True)
    table.add_column("family", style="magenta")
    for name in available_attacks():
        table.add_row(name, make_attack(name).family)
    _out.print(table)
    _out.print(f"families: {', '.join(available_families())}")


@app.command("list-recipes")
def list_recipes() -> None:
    """List built-in run recipes (named RunConfig presets for `attack --recipe`)."""
    table = Table(title="Recipes")
    table.add_column("recipe", style="cyan", no_wrap=True)
    table.add_column("attacks", style="magenta")
    table.add_column("episodes", justify="right")
    table.add_column("description")
    for name in available_recipes():
        cfg = RECIPES[name].config
        attacks = ", ".join(cfg.get("attacks", ["instruction"]))
        episodes = str(cfg.get("episodes", 10))
        table.add_row(name, attacks, episodes, RECIPES[name].description)
    _out.print(table)
    _out.print("Use: [cyan]provael attack --recipe <name>[/cyan]  (explicit flags override it)")


@app.command("list-reproductions")
def list_reproductions() -> None:
    """List published-attack reproductions (`reproduce <name>`)."""
    table = Table(title="Reproductions")
    table.add_column("name", style="cyan", no_wrap=True)
    table.add_column("EAI", style="magenta")
    table.add_column("paper")
    table.add_column("Provael family")
    for name in available_reproductions():
        repro = get_reproduction(name)
        table.add_row(name, repro.eai, f"{repro.title.split(':')[0]} ({repro.arxiv})",
                      ", ".join(repro.attacks))
    _out.print(table)
    _out.print("Use: [cyan]provael reproduce <name>[/cyan]  (defaults to the CPU stub)")


@app.command("list-defenses")
def list_defenses() -> None:
    """List registered defenses (mitigations measured under the docs/defenses.md protocol)."""
    table = Table(title="Defenses")
    table.add_column("defense", style="cyan", no_wrap=True)
    table.add_column("kind", style="magenta")
    # A certifier reading "a defense was applied" needs to know whether it was a text pre-filter or
    # an output monitor: different protective measures, different failure modes.
    table.add_column("position")
    table.add_column("EAI ids")
    table.add_column("status")
    for name in available_defenses():
        d = make_defense(name)
        # "measured" ONLY where a study exists — docs/defenses.md keeps every other taxonomy row at
        # "specified, unproven" and this column must not quietly upgrade one.
        #
        # Read from the class attribute, NOT from the filesystem. Probing for
        # docs/studies/<name>.md worked in a git checkout and never in an installed wheel (docs/ is
        # not packaged), so 0.26.0 told every user its one measured defense was unproven.
        status = "measured" if d.study else "specified, unproven"
        table.add_row(name, d.kind, d.position, ", ".join(d.eai_ids) or "—", status)
    _out.print(table)
    _out.print(
        "Four of the six docs/defenses.md taxonomy rows ship no implementation and are "
        "deliberately absent: an unmeasured mitigation is not a registered one."
    )
    _out.print(
        "Use: [cyan]provael attack --defense <name>[/cyan] then [cyan]provael mitigation[/cyan]"
    )


@app.command()
def attack(
    ctx: typer.Context,
    policy: Annotated[str, typer.Option(help="Registered policy name.")] = "stub",
    suite: Annotated[str, typer.Option(help="Registered suite name.")] = "stub",
    attacks: Annotated[
        str, typer.Option(help="Comma-separated attack or family names.")
    ] = "instruction",
    episodes: Annotated[int, typer.Option(min=1, help="Episodes per (task, attack) pair.")] = 10,
    seeds: Annotated[
        int | None, typer.Option(min=1, help="Number of seeds (alias for --episodes).")
    ] = None,
    seed: Annotated[int, typer.Option(min=0, help="Base random seed.")] = 0,
    horizon: Annotated[int, typer.Option(min=1, help="Max timesteps per episode.")] = 8,
    tasks: Annotated[
        str | None, typer.Option(help="Comma-separated task subset (default: all).")
    ] = None,
    model: Annotated[
        str | None, typer.Option(help="Checkpoint override (e.g. a LIBERO-finetuned SmolVLA).")
    ] = None,
    rename_map: Annotated[
        str | None, typer.Option("--rename-map", help="JSON obs-key rename map for the policy.")
    ] = None,
    unnorm_key: Annotated[
        str | None,
        typer.Option("--unnorm-key", help="Action-unnormalization stats id (e.g. OpenVLA)."),
    ] = None,
    accelerator: Annotated[
        str | None,
        typer.Option(
            "--accelerator",
            help="Execution device: 'cpu' | 'cuda' | 'mps'. Recorded into the report (D6). "
            "'tpu' is an explicit NotImplementedError slot (see ROADMAP §8).",
        ),
    ] = None,
    precision: Annotated[
        str | None,
        typer.Option("--precision", help="Compute-precision hint (e.g. 'fp32', 'bf16'), recorded."),
    ] = None,
    out: Annotated[Path, typer.Option(help="Output directory for reports.")] = Path("runs/stub"),
    fmt: Annotated[
        OutputFormat,
        typer.Option(
            "--format",
            help="Output format. 'sarif' also writes report.sarif, 'compliance' also writes "
            "report.compliance.json, into --out.",
        ),
    ] = OutputFormat.table,
    sarif_out: Annotated[
        Path | None,
        typer.Option("--sarif-out", help="Write a SARIF 2.1.0 file to this path (implies SARIF)."),
    ] = None,
    calib: Annotated[
        Path | None,
        typer.Option("--calib", help="Dir of calibration artifacts (from `provael calibrate`)."),
    ] = None,
    query_budget: Annotated[
        int | None,
        typer.Option(
            "--query-budget",
            min=1,
            help="Per-episode policy-query budget for the optimized (search) attack family.",
        ),
    ] = None,
    defense: Annotated[
        str | None,
        typer.Option(
            "--defense",
            help="Registered defense applied between the attack and the policy "
            "(see `provael list-defenses`). Writes a defense-log.jsonl audit sidecar.",
        ),
    ] = None,
    recipe: Annotated[
        str | None,
        typer.Option(
            "--recipe",
            help="Built-in recipe name (see `list-recipes`) or path to a recipe .yml. "
            "Explicitly-passed flags override the recipe.",
        ),
    ] = None,
) -> None:
    """Run a red-team evaluation and write report.json + report.md."""
    rename: dict[str, str] | None = None
    if rename_map is not None:
        try:
            rename = json.loads(rename_map)
        except json.JSONDecodeError:
            _fail("--rename-map must be a JSON object, e.g. '{\"a\": \"b\"}'")
            return

    # A recipe provides the base config; explicitly-passed CLI flags override it. We use the
    # parameter source to tell an explicit flag from a default, so `--recipe quick --seed 3`
    # keeps the recipe's attacks/episodes but uses seed 3.
    try:
        base: dict[str, object] = load_recipe(recipe) if recipe is not None else {}
    except (KeyError, ValueError) as exc:
        _fail(str(exc).strip('"'))
        return

    def _explicit(name: str) -> bool:
        source = ctx.get_parameter_source(name)
        return source is not None and source.name == "COMMANDLINE"

    # `--seeds` and `--episodes` write the same config key, so passing both resolves by source
    # order and the reported `n` is not the one the caller asked for. Aliases must be exclusive.
    if _explicit("episodes") and _explicit("seeds"):
        _fail("--seeds and --episodes are aliases for the same value; pass only one")
        return

    overrides: dict[str, object] = {}
    if _explicit("policy"):
        overrides["policy"] = policy
    if _explicit("suite"):
        overrides["suite"] = suite
    if _explicit("attacks"):
        # An explicit `--attacks ""` (an unset CI variable) must not fall back to a default family:
        # the run would be an EAI01-only sweep labelled as whatever the caller meant to configure.
        selected = _split_csv(attacks)
        if selected is None:
            _fail("--attacks must name at least one attack or attack family")
            return
        overrides["attacks"] = selected
    if _explicit("tasks"):
        overrides["tasks"] = _split_csv(tasks)
    if _explicit("episodes"):
        overrides["episodes"] = episodes
    if _explicit("seeds") and seeds is not None:
        overrides["episodes"] = seeds
    if _explicit("seed"):
        overrides["seed"] = seed
    if _explicit("horizon"):
        overrides["horizon"] = horizon
    if _explicit("model"):
        overrides["model"] = model
    if _explicit("rename_map"):
        overrides["rename_map"] = rename
    if _explicit("unnorm_key"):
        overrides["unnorm_key"] = unnorm_key
    if _explicit("accelerator"):
        overrides["accelerator"] = accelerator
    if _explicit("precision"):
        overrides["precision"] = precision
    if _explicit("query_budget"):
        overrides["query_budget"] = query_budget
    if _explicit("defense"):
        overrides["defense"] = defense
    if _explicit("out"):
        overrides["out"] = out

    try:
        config = RunConfig.model_validate({**base, **overrides})
    except ValidationError as exc:
        _fail(f"invalid configuration: {exc.errors()[0]['msg']}")
        return
    except NotImplementedError as exc:
        # e.g. --accelerator tpu — the D5/§8 reserved slot surfaces its decision text cleanly.
        _fail(str(exc))
        return

    calibrations = None
    if calib is not None:
        calibrations = load_calibrations(calib, config.policy, config.suite)
        if not calibrations:
            _err.print(
                f"[yellow]note:[/yellow] no calibration artifacts for "
                f"{config.policy}/{config.suite} in {calib}; using the default predicate."
            )

    started = time.perf_counter()
    # The defense audit trail is collected here and written as a SIDECAR, never merged into
    # report.json — a field on RunReport would move the attestation subject digest.
    defense_audit: list[dict[str, str]] = []
    try:
        report = run(config, calibrations, audit_sink=defense_audit)
    except (MissingLeRobotError, IncompatiblePolicyError) as exc:
        _fail(str(exc))
        return
    except KeyError as exc:
        # Unknown policy / suite / attack — KeyError carries a helpful message.
        _fail(str(exc).strip('"'))
        return
    except NotImplementedError as exc:
        _fail(str(exc))
        return
    elapsed = time.perf_counter() - started

    json_path, md_path = write_report(report, config.out)
    _emit_execution_manifest(report, config.out, elapsed=elapsed, defense=config.defense)
    if config.defense:
        log_path = _write_defense_log(defense_audit, config.out)
        _out.print(f"Defense [cyan]{config.defense}[/cyan] audit trail -> [cyan]{log_path}[/cyan]")
    render_summary(report, _out)
    _out.print(f"\nWrote [cyan]{json_path}[/cyan] and [cyan]{md_path}[/cyan]  ({elapsed:.2f}s)")

    sarif_target = sarif_out or (config.out / "report.sarif" if fmt is OutputFormat.sarif else None)
    if sarif_target is not None:
        write_sarif(report, sarif_target)
        _out.print(f"Wrote [cyan]{sarif_target}[/cyan]  (SARIF 2.1.0)")

    if fmt is OutputFormat.compliance:
        compliance_target = config.out / COMPLIANCE_JSON
        write_compliance_json(report, compliance_target)
        _out.print(f"Wrote [cyan]{compliance_target}[/cyan]  (compliance evidence, JSON)")

    if fmt is OutputFormat.scorecard:
        scorecard_target = write_scorecard(report, config.out / SCORECARD_MD)
        _out.print(f"Wrote [cyan]{scorecard_target}[/cyan]  (pre-deployment ASR scorecard)")

    if fmt is OutputFormat.oscal:
        oscal_target = write_oscal(report, config.out / OSCAL_JSON)
        _out.print(f"Wrote [cyan]{oscal_target}[/cyan]  (OSCAL assessment-results)")

    if fmt is OutputFormat.mlbom:
        mlbom_target = write_ml_bom(report, config.out / ML_BOM_JSON)
        _out.print(f"Wrote [cyan]{mlbom_target}[/cyan]  (CycloneDX ML-BOM)")


@app.command()
def reproduce(
    name: Annotated[str, typer.Argument(help="Reproduction name (see `list-reproductions`).")],
    policy: Annotated[str, typer.Option(help="Policy to run it against.")] = "stub",
    suite: Annotated[str, typer.Option(help="Suite to run it in.")] = "stub",
    model: Annotated[
        str | None, typer.Option(help="Checkpoint override for a real policy.")
    ] = None,
    unnorm_key: Annotated[
        str | None, typer.Option("--unnorm-key", help="Action-unnormalization id (e.g. OpenVLA).")
    ] = None,
    episodes: Annotated[int, typer.Option(min=1, help="Episodes per (task, attack) pair.")] = 10,
    seed: Annotated[int, typer.Option(min=0, help="Base random seed.")] = 0,
    out: Annotated[Path, typer.Option(help="Output directory.")] = Path("runs/repro"),
) -> None:
    """Reproduce a published VLA attack by name, mapped onto Provael's attack families.

    Prints the paper's *cited* result separately from Provael's *measured* result. On the CPU
    stub the measured numbers are properties of the deterministic fixture, not a real VLA.
    """
    try:
        repro = get_reproduction(name)
    except KeyError as exc:
        _fail(str(exc).strip('"'))
        return

    _out.print(
        f"\n[bold]Reproduction:[/bold] {escape(repro.title)}  [magenta]{repro.eai}[/magenta]"
    )
    _out.print(f"  paper: {escape(repro.arxiv)}")
    _out.print(f"  {escape(repro.summary)}")
    _out.print(f"  [dim]mapping:[/dim] {escape(repro.mapping_note)}")
    _out.print(f"  [dim]paper reported (cited, NOT Provael's):[/dim] {escape(repro.paper_asr)}\n")

    try:
        config = RunConfig(
            policy=policy, suite=suite, model=model, unnorm_key=unnorm_key,
            attacks=repro.attacks, episodes=episodes, seed=seed, out=out,
        )
        report = run(config)
    except (MissingLeRobotError, IncompatiblePolicyError, NotImplementedError) as exc:
        _fail(str(exc))
        return
    except KeyError as exc:
        _fail(str(exc).strip('"'))
        return

    write_report(report, config.out)
    render_summary(report, _out)
    _out.print(
        f"\n[bold]Provael measured[/bold] (policy={policy}, suite={suite}): {report.headline()}"
    )
    if policy == "stub" or suite == "stub":
        _err.print(
            "[yellow]note:[/yellow] stub numbers are properties of the deterministic test "
            "fixture, not a real VLA. Run against a real model for real numbers, e.g.\n"
            "  PROVAEL_INTEGRATION=1 provael reproduce "
            f"{repro.name} --policy smolvla --suite libero --model HuggingFaceVLA/smolvla_libero"
        )


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


@app.command()
def report(
    in_dir: Annotated[Path, typer.Option("--in", help="Directory containing report.json.")],
    fmt: Annotated[
        OutputFormat,
        typer.Option(
            "--format",
            help="Output: 'table', 'sarif', 'compliance', 'scorecard', 'oscal', or 'mlbom'.",
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
    if fmt is OutputFormat.mlbom:
        if out is not None:
            write_ml_bom(loaded, out)
            _out.print(f"Wrote [cyan]{out}[/cyan]  (CycloneDX ML-BOM)")
        else:
            print(to_ml_bom_json(loaded))  # machine-readable ML-BOM to stdout
        return
    render_summary(loaded, _out)


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
        ExportFormat, typer.Option("--format", help="Evidence-graph format (currently 'avid').")
    ] = ExportFormat.avid,
    out: Annotated[
        Path | None, typer.Option("--out", help="Write here instead of stdout.")
    ] = None,
) -> None:
    """Export a run into an evidence-graph format (AVID record) for a recognised database.

    Submitting the record to AVID is an external action — this only produces the file.
    """
    try:
        loaded = load_report(in_dir)
    except FileNotFoundError as exc:
        _fail(str(exc))
        return
    except ValidationError:
        _fail(f"{in_dir} does not contain a valid Provael report.json")
        return
    # fmt is ExportFormat.avid (the only member today).
    if out is not None:
        write_avid(loaded, out)
        _out.print(f"Wrote [cyan]{out}[/cyan]  (AVID record)")
    else:
        print(to_avid_json(loaded))


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
    else:
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
        write_report(report, out)

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
        include_crosswalk=include_crosswalk, mitigation=mitigation_report,
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


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Bind host.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535, help="Bind port.")] = 8000,
) -> None:
    """Run the EXPERIMENTAL reference hosted server (needs the `hosted` extra).

    Not a production signing service: it does not authenticate callers or bind ownership, and every
    signature it produces is the operator's OWN key — untrusted until a verifier adds it to a trust
    store. Disabled by default; set `PROVAEL_ENABLE_EXPERIMENTAL_HOSTED=1` to run it. The free CLI,
    attacks, ASR, SARIF, the Action and local `attest` are never gated.
    """
    try:
        import uvicorn

        from provael.hosted import HostedDisabledError
        from provael.hosted.server import MissingHostedExtraError, create_app
    except ImportError:
        _fail("The hosted server needs the `hosted` extra: pip install 'provael[hosted]'.")
        return
    try:
        application = create_app()
    except (MissingHostedExtraError, HostedDisabledError) as exc:
        _fail(str(exc))
        return
    _out.print(
        f"Provael hosted (EXPERIMENTAL, operator-key-only) on "
        f"[cyan]http://{host}:{port}[/cyan]  —  Ctrl-C to stop"
    )
    uvicorn.run(application, host=host, port=port)


@app.command(name="evidence-manifest")
def evidence_manifest(
    in_dir: Annotated[
        Path, typer.Option("--in", "--report", help="Directory with a report.json to describe.")
    ],
    commit: Annotated[
        str,
        typer.Option("--commit", help="Pinned source commit (required — never a moving branch)."),
    ],
    repo: Annotated[
        str, typer.Option("--repo", help="Source repository URL.")
    ] = "https://github.com/provael/provael",
    out: Annotated[
        Path, typer.Option("--out", help="Output path for the manifest JSON.")
    ] = Path("artifacts/public-evidence-manifest.json"),
) -> None:
    """Build the deterministic public evidence manifest a website can consume.

    Restates the honest metric semantics (adversarial ASR vs the all-episode rate vs the benign
    control), per-attack results with Wilson intervals and applicability (N/A stays N/A), the
    evidence-ladder state, the release verdict, and the limitations. It pins its source commit and
    carries no wall-clock, so the same report + commit yields byte-identical output.
    """
    try:
        report = load_report(in_dir)
    except (FileNotFoundError, ValidationError):
        _fail(f"{in_dir} does not contain a valid report.json")
        return
    try:
        text = to_evidence_manifest_json(
            report, repository=repo, commit=commit, regulatory_clock_version=RULESET_VERSION
        )
    except ValueError as exc:
        _fail(str(exc))
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    _out.print(f"[green]wrote[/green] evidence manifest -> {out}")


@app.command()
def attest(
    in_dir: Annotated[
        Path | None,
        typer.Option(
            "--in", "--run",
            help="Directory with a prior report.json (RunReport) to attest. Omit to run one.",
        ),
    ] = None,
    profile: Annotated[
        AssuranceProfile | None,
        typer.Option(
            "--profile",
            help="Embed a standards-aligned assurance view: iso-10218-2 | iec-62443 | insurer.",
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
    key: Annotated[
        Path | None,
        typer.Option("--key", help="Ed25519 private-key PEM to sign with. Omit for ephemeral."),
    ] = None,
    no_sign: Annotated[
        bool, typer.Option("--no-sign", help="Emit a digest-only bundle (no signature, no extra).")
    ] = False,
    verify: Annotated[
        Path | None,
        typer.Option("--verify", help="Verify an existing attestation.json instead of issuing."),
    ] = None,
    pubkey: Annotated[
        Path | None, typer.Option("--pubkey", help="Public-key PEM to verify a signed bundle with.")
    ] = None,
    trust_store: Annotated[
        Path | None,
        typer.Option(
            "--trust-store",
            help="Local trust store (JSON) of trusted signer keys. Strict --verify needs it: a "
            "valid signature from an unknown key is authentic but UNTRUSTED.",
        ),
    ] = None,
    subject_report: Annotated[
        Path | None,
        typer.Option(
            "--report",
            help="A report.json to independently recheck against the attested subject digest "
            "(--verify). Without it, the embedded digest is not independently confirmed.",
        ),
    ] = None,
    integrity_only: Annotated[
        bool,
        typer.Option(
            "--integrity-only",
            help="Grade only the digest layer (--verify): pass if the payload is intact, WITHOUT "
            "establishing signer identity or trust. Never reported as plain 'verified'.",
        ),
    ] = False,
    commit: Annotated[
        str | None, typer.Option("--commit", help="Override the source commit stamp.")
    ] = None,
    out: Annotated[
        Path, typer.Option(help="Output directory for the bundle.")
    ] = Path("runs/attest"),
) -> None:
    """Issue (or verify) a signed, dated, standards-crosswalked ASR evidence bundle.

    `attest` wraps the SAME compliance evidence as `report --format compliance` — the ASR with its
    95% Wilson CI, the benign-FPR control, the per-EAI breakdown, and the EU/ISO/NIST/IEC crosswalk
    — then binds it with a SHA-256 digest, stamps a UTC date + ruleset + commit, and signs a
    DSSE-style envelope (Ed25519). `--profile` embeds a standards-aligned assurance view
    (ISO 10218-2 -> IEC 62443 SL2, or an insurer summary) with the honest per-family transfer table
    and a third-party cert-readiness cross-reference. It is evidence, not certification.
    """
    # -- verification mode -------------------------------------------------------------------
    if verify is not None:
        try:
            bundle = load_bundle(verify)
        except (FileNotFoundError, ValidationError):
            _fail(f"{verify} is not a readable attestation bundle")
            return
        pub_bytes = pubkey.read_bytes() if pubkey is not None else None
        store = None
        if trust_store is not None:
            try:
                store = load_trust_store(trust_store)
            except (FileNotFoundError, ValidationError):
                _fail(f"{trust_store} is not a readable trust store")
                return
        subject = None
        if subject_report is not None:
            try:
                subject = load_report(subject_report)
            except (FileNotFoundError, ValidationError):
                _fail(f"{subject_report} does not contain a valid report.json")
                return
        try:
            result = verify_bundle(
                bundle,
                public_key_pem_bytes=pub_bytes,
                trust_store=store,
                subject_report=subject,
                now=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
        except MissingAttestExtraError as exc:
            _fail(str(exc))
            return
        for reason in result.reasons:
            _out.print(f"  - {reason}")
        code = verify_exit_code(result, integrity_only=integrity_only)
        if code == EXIT_OK and integrity_only:
            _out.print(
                "[yellow]attestation INTEGRITY-ONLY OK[/yellow] — payload intact; signer identity "
                "and trust NOT established"
            )
        elif code == EXIT_OK:
            _out.print("[green]attestation STRICT OK[/green] — integrity + trusted signature")
        else:
            _fail(
                f"attestation verification FAILED [{'/'.join(result.codes) or 'not strict-OK'}]",
                code=code,
            )
        return

    # -- issuance mode -----------------------------------------------------------------------
    if in_dir is not None:
        try:
            report = load_report(in_dir)
        except FileNotFoundError as exc:
            _fail(str(exc))
            return
        except ValidationError:
            _fail(f"{in_dir} does not contain a valid Provael report.json")
            return
    else:
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
        write_report(report, out)

    issued_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp = commit or _git_commit() or f"v{__version__}"
    private_key_pem = key.read_bytes() if key is not None else None
    assurance = (
        build_assurance(report, profile, issued_at=issued_at, commit=stamp)
        if profile is not None else None
    )

    try:
        bundle, pub_pem = to_bundle(
            report, issued_at=issued_at, commit=stamp,
            private_key_pem=private_key_pem, sign=not no_sign, assurance=assurance,
        )
    except MissingAttestExtraError as exc:
        _fail(str(exc))
        return

    bundle_path = write_bundle(bundle, out / ATTESTATION_JSON)
    # The human-readable evidence travels with the bundle.
    write_compliance_markdown(report, out / "report.compliance.md")
    pub_path: Path | None = None
    if pub_pem is not None and key is None:
        # Ephemeral key: publish the public half so the bundle stays offline-verifiable.
        pub_path = out / ATTESTATION_PUB
        pub_path.write_bytes(pub_pem)

    render_summary(report, _out)
    # The signed payload's evidence is the ADVERSARIAL headline (`compliance._evidence` reads
    # `adversarial_headline`), so this line must read the same fields. Printing the all-episode
    # rate made the console block and the bundle it had just written disagree by the width of the
    # benign control — and the console figure is the one that gets pasted into tickets.
    rate, succ, att = report.adversarial_headline()
    fpr = "n/a" if report.benign_fpr is None else f"{100.0 * report.benign_fpr:.1f}%"
    if att == 0:
        evidence = "adversarial ASR N/A (0 adversarial episodes)"
    else:
        lo, hi = wilson_ci(succ, att)
        evidence = (
            f"adversarial ASR {100.0 * rate:.1f}% ({succ}/{att}) "
            f"[{100.0 * lo:.0f}-{100.0 * hi:.0f}%]"
        )
    _out.print("\n[bold]Attestation[/bold]")
    _out.print(f"  subject   : {report.policy} x {report.suite}")
    _out.print(f"  evidence  : {evidence}, benign FPR {fpr}")
    _out.print(f"  issued_at : {issued_at}   commit: {stamp}")
    if bundle.signed:
        _out.print(f"  signature : ed25519  keyid {bundle.signatures[0].keyid}")
    else:
        _out.print("  signature : [yellow]digest-only (unsigned)[/yellow]")
    _out.print("  clock     : EU Machinery Reg 2023/1230 applies 2027-01-20")
    _out.print(f"\nWrote [cyan]{bundle_path}[/cyan]"
               + (f" and [cyan]{pub_path}[/cyan]" if pub_path is not None else ""))
    if bundle.signed and key is None:
        _err.print("[yellow]note:[/yellow] signed with an ephemeral key (integrity, not identity). "
                   "Pass --key <ed25519.pem> to sign with your organisation key.")
    if report.policy == "stub" or report.suite == "stub":
        _err.print("[yellow]note:[/yellow] stub numbers are properties of the deterministic "
                   "fixture, not a real VLA. Attest a real run for a transfer measurement.")
    verify_hint = f"provael attest --verify {bundle_path}"
    if pub_path is not None:
        verify_hint += f" --pubkey {pub_path}"
    _out.print(f"Verify offline: [bold]{verify_hint}[/bold]")


@app.command()
def calibrate(
    policy: Annotated[str, typer.Option(help="Registered policy name.")] = "stub",
    suite: Annotated[str, typer.Option(help="Registered suite name.")] = "stub",
    tasks: Annotated[
        str | None, typer.Option(help="Comma-separated task subset (default: all).")
    ] = None,
    seeds: Annotated[
        int, typer.Option(min=2, help="Number of benign rollouts (split into fit/holdout).")
    ] = 20,
    seed: Annotated[int, typer.Option(min=0, help="Base seed; rollout i uses seed + i.")] = 0,
    horizon: Annotated[int, typer.Option(min=1, help="Max timesteps per benign rollout.")] = 8,
    target_fpr: Annotated[
        float,
        typer.Option("--target-fpr", min=0.0, max=1.0, help="Max benign FPR on the holdout split."),
    ] = 0.05,
    model: Annotated[
        str | None, typer.Option(help="Checkpoint override (real policies).")
    ] = None,
    out: Annotated[
        Path, typer.Option(help="Output directory for calibration artifacts.")
    ] = Path("calib"),
) -> None:
    """Calibrate the per-task unsafe predicate from benign rollouts (writes calib artifacts)."""
    seed_list = list(range(seed, seed + seeds))
    try:
        calibrations = calibrate_suite(
            policy, suite, _split_csv(tasks), seed_list,
            target_fpr=target_fpr, horizon=horizon, tool_version=__version__, model=model,
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
    table.add_column("boundary")
    written: list[Path] = []
    for task, cal in calibrations.items():
        boundary = (
            f"danger > {cal.threshold:.3f}"
            if cal.kind == "scalar"
            else f"{len(cal.keep_out_zones)} keep-out zone(s)"
        )
        table.add_row(
            task, cal.kind, str(cal.n_benign),
            f"{100.0 * cal.target_fpr:.1f}%", f"{100.0 * cal.benign_fpr:.1f}%", boundary,
        )
        written.append(save_calibration(cal, out))
    _out.print(table)
    for path in written:
        _out.print(f"Wrote [cyan]{path}[/cyan]")
    _out.print(
        f"\nApply it: [bold]provael attack --policy {policy} --suite {suite} "
        f"--calib {out}[/bold]"
    )


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


@leaderboard_app.command("build")
def leaderboard_build(
    runs: Annotated[
        list[str] | None,
        typer.Option(help="Run dir(s), glob(s), or report.json path(s). Quote globs."),
    ] = None,
    real: Annotated[
        Path | None,
        typer.Option(
            "--real",
            help="Build the public real board from this results dir (requires a non-stub run; "
            "stamps a UTC date, source commit, and an inputs digest).",
        ),
    ] = None,
    sign: Annotated[
        bool, typer.Option("--sign", help="Ed25519-sign the board (needs the `attest` extra).")
    ] = False,
    key: Annotated[
        Path | None,
        typer.Option("--key", help="Ed25519 private-key PEM to sign with. Omit for ephemeral."),
    ] = None,
    out: Annotated[Path, typer.Option(help="Output directory for leaderboard.json.")] = Path(
        "leaderboard/results"
    ),
    submitted_by: Annotated[
        str | None,
        typer.Option(
            "--submitted-by",
            help="Attribute every produced row to this submitter (a GitHub handle or org). "
            "Omit to leave rows unattributed.",
        ),
    ] = None,
    provenance: Annotated[
        str,
        typer.Option(
            "--provenance",
            help=f"How these rows reached the board: {MAINTAINER_RUN} | "
            f"{THIRD_PARTY_SUBMISSION} | {UNATTRIBUTED}.",
        ),
    ] = UNATTRIBUTED,
) -> None:
    """Aggregate report.json files into a ranked leaderboard.json (deterministic; real + signed)."""
    if provenance not in {MAINTAINER_RUN, THIRD_PARTY_SUBMISSION, UNATTRIBUTED}:
        _fail(
            f"unknown --provenance {provenance!r}; expected one of {MAINTAINER_RUN}, "
            f"{THIRD_PARTY_SUBMISSION}, {UNATTRIBUTED}"
        )
        return
    if submitted_by is None and provenance != UNATTRIBUTED:
        _fail(f"--provenance {provenance} needs --submitted-by (who is being attributed?)")
        return
    source = [str(real)] if real is not None else (runs or ["runs"])
    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if real is not None else None
    commit = (_git_commit() or f"v{__version__}") if real is not None else None

    sign_key: bytes | None = None
    ephemeral = False
    if sign:
        try:
            sign_key = key.read_bytes() if key is not None else generate_private_key_pem()
        except MissingAttestExtraError as exc:
            _fail(str(exc))
            return
        ephemeral = key is None

    try:
        out_path, leaderboard = build_leaderboard(
            source, out, generated_at=generated_at, commit=commit,
            sign_key=sign_key, require_real=real is not None,
            submitted_by=submitted_by, provenance=provenance,
        )
    except FileNotFoundError as exc:
        _fail(str(exc))
        return
    except ValueError as exc:  # require_real on a stub-only input
        _fail(str(exc))
        return

    pub_path: Path | None = None
    if sign and ephemeral and sign_key is not None:
        pub_path = out / (LEADERBOARD_JSON.replace(".json", ".pub"))
        pub_path.write_bytes(public_key_pem(sign_key))

    _render_leaderboard(leaderboard)
    if leaderboard.inputs_digest is not None:
        _out.print(f"inputs digest: [dim]{leaderboard.inputs_digest[:16]}…[/dim]")
    if leaderboard.signature is not None:
        _out.print(f"signature: ed25519  keyid {leaderboard.signature.keyid}")
    _out.print(f"\nWrote [cyan]{out_path}[/cyan]"
               + (f" and [cyan]{pub_path}[/cyan]" if pub_path is not None else ""))
    if sign and ephemeral:
        _err.print("[yellow]note:[/yellow] signed with an ephemeral key (integrity, not identity). "
                   "Pass --key to sign with your organisation key.")


@leaderboard_app.command("verify")
def leaderboard_verify(
    board: Annotated[Path, typer.Option("--in", help="Path to a leaderboard.json to verify.")],
    pubkey: Annotated[Path, typer.Option("--pubkey", help="Ed25519 public-key PEM.")],
) -> None:
    """Verify a signed leaderboard offline against a public key."""
    try:
        loaded = load_leaderboard(board)
    except (FileNotFoundError, ValidationError):
        _fail(f"{board} is not a readable leaderboard.json")
        return
    if loaded.signature is None:
        _fail("leaderboard is unsigned — nothing to verify", code=1)
        return
    try:
        ok = verify_leaderboard(loaded, pubkey.read_bytes())
    except MissingAttestExtraError as exc:
        _fail(str(exc))
        return
    if ok:
        _out.print(f"[green]leaderboard OK[/green]  keyid {loaded.signature.keyid}")
    else:
        _fail("leaderboard signature INVALID", code=1)


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
        _err.print(
            f"[red]stale[/red]: the newest measurement is {int(age)} days old (over "
            f"{STALE_DAYS}). The README's continuous-verification claim is not currently true."
        )


#: Where a leaderboard submission lands. The submission is a PR to this repo adding
#: ``results/<name>/`` — the flow CONTRIBUTING-leaderboard.md documents, which the
#: `Leaderboard submission` workflow already validates on arrival.
SUBMISSION_REPO = "provael/provael"


@app.command("submit")
def submit_cmd(
    run_dir: Annotated[
        Path,
        typer.Argument(
            help="A run directory containing report.json (from `provael attack --out`)."
        ),
    ],
    submitted_by: Annotated[
        str,
        typer.Option("--submitted-by", help="Your GitHub handle or org — attributed on every row."),
    ],
    key: Annotated[
        Path | None,
        typer.Option("--key", help="Ed25519 private-key PEM to sign with. Omit for ephemeral."),
    ] = None,
    name: Annotated[
        str | None,
        typer.Option("--name", help="Submission directory name (default: --submitted-by)."),
    ] = None,
    open_pr: Annotated[
        bool,
        typer.Option("--open-pr/--no-open-pr", help="Open the PR with `gh` (needs gh, authed)."),
    ] = True,
) -> None:
    """Validate, sign and submit a run to the public leaderboard — the whole path, one command.

    Three steps that were three documents: validate the report against the submission schema,
    Ed25519-sign it so the numbers are tamper-evident in transit, and open the PR. The submission
    machinery has existed since the board did and has never been exercised by an outsider, which
    is the kind of thing a five-step README causes.

    Nothing here is privileged: it runs against a fork the same way it runs for the maintainer, and
    every step prints the command it ran so a submitter can do it by hand instead. If `gh` is
    missing or unauthenticated the command still validates and signs, then prints the exact
    remaining steps rather than failing at the end with the work thrown away.
    """
    report_paths = find_reports([str(run_dir)])
    if not report_paths:
        _fail(f"no report.json under {run_dir} — run `provael attack --out {run_dir}` first")
        return
    if len(report_paths) > 1:
        _fail(
            f"{run_dir} holds {len(report_paths)} report.json files; submit one run at a time so "
            "a reviewer can attribute each number to its own protocol"
        )
        return

    try:
        report = load_report(report_paths[0].parent)
    except (FileNotFoundError, ValidationError) as exc:
        _fail(f"{report_paths[0]} is not a readable report.json: {exc}")
        return

    # 1. Validate — the same check the CI workflow runs on arrival, so a submitter sees the
    #    failure here rather than after opening a PR.
    problems = validate_report(report)
    if problems:
        _err.print("[red]submission is not valid:[/red]")
        for problem in problems:
            _err.print(f"  - {problem}")
        raise typer.Exit(2)
    _out.print(f"[green]✓[/green] report validates ({report.policy} × {report.suite})")

    # 2. Sign — tamper-evidence in transit. A reviewer verifies the bundle offline against the
    #    published public half before trusting a single number in the PR.
    issued_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp = _git_commit() or f"v{__version__}"
    try:
        bundle, pub_pem = to_bundle(
            report, issued_at=issued_at, commit=stamp,
            private_key_pem=key.read_bytes() if key is not None else None, sign=True,
        )
    except MissingAttestExtraError as exc:
        _fail(f"{exc}  (install with: pip install 'provael[attest]')")
        return

    slug = (name or submitted_by).strip().replace("/", "__")
    dest = Path("results") / slug
    dest.mkdir(parents=True, exist_ok=True)
    write_report(report, dest)
    bundle_path = write_bundle(bundle, dest / ATTESTATION_JSON)
    if pub_pem is not None and key is None:
        (dest / ATTESTATION_PUB).write_bytes(pub_pem)
        _err.print(
            "[yellow]note:[/yellow] signed with an ephemeral key (integrity, not identity). "
            "Pass --key to sign as yourself; the public half is published beside the bundle."
        )
    keyid = bundle.signatures[0].keyid if bundle.signatures else "unsigned"
    _out.print(f"[green]✓[/green] signed  keyid {keyid} → [cyan]{bundle_path}[/cyan]")

    # 3. Open the PR. Every step is printed so the manual path is always available.
    branch = f"leaderboard/{slug}"
    title = f"leaderboard: {report.policy} × {report.suite} from {submitted_by}"
    body = (
        f"Leaderboard submission from **{submitted_by}**.\n\n"
        f"- policy × suite: `{report.policy}` × `{report.suite}`\n"
        f"- measured with: `provael {report.tool_version}`\n"
        f"- attempts: {report.attempts} · successes: {report.successes}\n"
        f"- signed: ed25519 keyid `{keyid}`\n\n"
        f"Validated locally with `provael submit`. The Leaderboard submission workflow "
        f"re-validates on arrival; verify the bundle offline with `provael verify "
        f"{dest / ATTESTATION_JSON}`.\n"
    )
    steps = [
        f"git checkout -b {branch}",
        f"git add {dest}",
        f"git commit -m {title!r}",
        f"git push -u origin {branch}",
        f"gh pr create --repo {SUBMISSION_REPO} --title {title!r} --body <the summary above>",
    ]
    if not open_pr:
        _out.print("\n[bold]Submission staged.[/bold] To open the PR:")
        for step in steps:
            _out.print(f"  {step}")
        return
    if shutil.which("gh") is None:
        _err.print(
            "\n[yellow]gh is not installed[/yellow] — the submission is validated, signed and "
            f"staged in {dest}. Finish it with:"
        )
        for step in steps:
            _err.print(f"  {step}")
        return
    _out.print(f"\nOpening the PR against {SUBMISSION_REPO}…")
    for cmd in (
        ["git", "checkout", "-b", branch],
        ["git", "add", str(dest)],
        ["git", "commit", "-m", title],
        ["git", "push", "-u", "origin", branch],
        ["gh", "pr", "create", "--repo", SUBMISSION_REPO, "--title", title, "--body", body],
    ):
        _out.print(f"  [dim]$ {' '.join(cmd)}[/dim]")
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            _err.print(f"[red]step failed:[/red] {completed.stderr.strip() or completed.stdout}")
            _err.print(
                f"The submission is validated and signed in {dest} — finish the remaining steps "
                "by hand (listed above) rather than re-running, so the work is not repeated."
            )
            raise typer.Exit(1)
        if completed.stdout.strip():
            _out.print(f"  {completed.stdout.strip().splitlines()[-1]}")
    _out.print("\n[green]Submitted.[/green] The Leaderboard submission workflow validates it next.")


if __name__ == "__main__":  # pragma: no cover
    app()


@app.command("verify-checkpoint")
def verify_checkpoint_cmd(
    checkpoint: Annotated[
        str, typer.Option("--checkpoint", help="Checkpoint identity (hub id or path) to record.")
    ],
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Local path to the fetched checkpoint to hash and classify."),
    ] = None,
    digest: Annotated[
        str | None,
        typer.Option("--digest", help="Pinned SHA-256 the checkpoint must match. Required unless "
                     "--no-require-digest is passed."),
    ] = None,
    allow_pickle: Annotated[
        bool,
        typer.Option("--allow-pickle/--no-allow-pickle",
                     help="Explicitly opt in to loading pickle-format weights (code execution)."),
    ] = False,
    require_digest: Annotated[
        bool,
        typer.Option("--require-digest/--no-require-digest",
                     help="Fail when no digest is pinned. ON by default — fail closed."),
    ] = True,
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Directory to write checkpoint-integrity.json into."),
    ] = None,
) -> None:
    """Verify a checkpoint BEFORE loading it — a supply-chain control, not an ASR.

    Fails closed: an unpinned digest and an un-opted-in pickle checkpoint both exit non-zero, so a
    gate that forgets to pin gets a failure rather than a silent pass. This produces a verdict, not
    a rate; it does not reduce attack success (see `provael.integrity`).
    """
    record = verify_checkpoint(
        checkpoint, path,
        expected_digest=digest, allow_pickle=allow_pickle, require_pinned_digest=require_digest,
    )
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        (out / INTEGRITY_JSON).write_text(
            json.dumps(json.loads(record.model_dump_json()), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    table = Table(title="Checkpoint integrity (supply chain, not an ASR)")
    table.add_column("field", style="cyan", no_wrap=True)
    table.add_column("value")
    table.add_row("checkpoint", record.checkpoint)
    table.add_row("EAI", f"{record.eai_id} — model & pipeline poisoning, backdoors & supply chain")
    table.add_row("format", record.checkpoint_format.value)
    shown = f"{record.digest_sha256[:32]}…" if record.digest_sha256 else "—"
    table.add_row("digest", shown)
    table.add_row("digest match", "—" if record.digest_match is None else str(record.digest_match))
    table.add_row("verdict", record.verdict.value)
    _out.print(table)
    for finding in record.findings:
        _err.print(f"[yellow]•[/yellow] {finding}")

    if record.verdict is IntegrityVerdict.failed:
        _fail("checkpoint integrity FAILED — refusing to load. See the findings above.")


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
