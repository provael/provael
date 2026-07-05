"""``provael`` command-line interface.

Commands:
  * ``attack``         — run a red-team evaluation and write a report.
  * ``list-policies``  — show registered policies and whether they're runnable here.
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
from provael.attacks.baseline import FAMILY as BASELINE_FAMILY
from provael.attacks.registry import (
    available_attacks,
    available_families,
    make_attack,
)
from provael.attest import (
    ATTESTATION_JSON,
    ATTESTATION_PUB,
    MissingAttestExtraError,
    generate_private_key_pem,
    load_bundle,
    public_key_pem,
    to_bundle,
    verify_bundle,
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
from provael.compliance import (
    COMPLIANCE_JSON,
    to_compliance_json,
    write_compliance_json,
    write_compliance_markdown,
)
from provael.config import RunConfig
from provael.leaderboard import (
    LEADERBOARD_JSON,
    Leaderboard,
    build_leaderboard,
    load_leaderboard,
    verify_leaderboard,
)
from provael.oscal import OSCAL_JSON, to_oscal_json, write_oscal
from provael.policies.lerobot_adapter import IncompatiblePolicyError, MissingLeRobotError
from provael.policies.registry import (
    available_policies,
    policy_extra,
    policy_is_ready,
)
from provael.recipes import RECIPES, available_recipes, load_recipe
from provael.regression import (
    DEFAULT_TOLERANCE,
    RegressionDiff,
    SliceDelta,
    diff_reports,
    write_diff_json,
    write_diff_markdown,
    write_regression_sarif,
)
from provael.report import load_report, render_summary, write_report
from provael.reproductions import available_reproductions, get_reproduction
from provael.runner import run
from provael.sarif import to_sarif_json, write_sarif
from provael.scorecard import SCORECARD_MD, to_scorecard_markdown, write_scorecard
from provael.scoring.asr import by_family
from provael.types import RunReport, TransferTest


class OutputFormat(StrEnum):
    """Console / artifact output format for ``attack`` and ``report``."""

    table = "table"
    sarif = "sarif"
    compliance = "compliance"
    scorecard = "scorecard"
    oscal = "oscal"


class ExportFormat(StrEnum):
    """Evidence-graph export formats for ``provael export``."""

    avid = "avid"


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


@app.command()
def version() -> None:
    """Print the Provael / provael version."""
    _out.print(f"provael (provael) {__version__}")


@app.command("list-policies")
def list_policies() -> None:
    """List registered policies and whether they can run in this environment."""
    table = Table(title="Policies")
    table.add_column("name", style="cyan", no_wrap=True)
    table.add_column("ready here", justify="center")
    table.add_column("notes")
    for name in available_policies():
        ready = policy_is_ready(name)
        mark = "[green]yes[/green]" if ready else "[yellow]no[/yellow]"
        extra = policy_extra(name)
        note = escape(f"requires `provael[{extra}]` (GPU)") if extra else "CPU, no deps"
        table.add_row(name, mark, note)
    _out.print(table)


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

    overrides: dict[str, object] = {}
    if _explicit("policy"):
        overrides["policy"] = policy
    if _explicit("suite"):
        overrides["suite"] = suite
    if _explicit("attacks"):
        overrides["attacks"] = _split_csv(attacks) or ["instruction"]
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
    if _explicit("query_budget"):
        overrides["query_budget"] = query_budget
    if _explicit("out"):
        overrides["out"] = out

    try:
        config = RunConfig.model_validate({**base, **overrides})
    except ValidationError as exc:
        _fail(f"invalid configuration: {exc.errors()[0]['msg']}")
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
    try:
        report = run(config, calibrations)
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


def _report_baseline(
    candidate_report: RunReport, baseline: Path, tolerance: float,
    out: Path | None, sarif_out: Path | None,
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
        typer.Option("--format", help="Output: 'table', 'sarif', 'compliance', or 'scorecard'."),
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
        _report_baseline(loaded, baseline, regression_tolerance, out, sarif_out)
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
def serve(
    host: Annotated[str, typer.Option(help="Bind host.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535, help="Bind port.")] = 8000,
) -> None:
    """Run the reference hosted attestation server (needs the `[hosted]` extra).

    Open-core: the server is Apache-2.0 and self-hostable (it returns self-signed attestations). The
    operated, project-key-signed instance plus the insurer / Notified-Body report are the paid tier;
    the free CLI, attacks, ASR, SARIF, the Action and local `attest` are never gated.
    """
    try:
        import uvicorn

        from provael.hosted.server import MissingHostedExtraError, create_app
    except ImportError:
        _fail("The hosted server needs the `hosted` extra: pip install 'provael[hosted]'.")
        return
    try:
        application = create_app()
    except MissingHostedExtraError as exc:
        _fail(str(exc))
        return
    _out.print(
        f"Provael hosted (reference) on [cyan]http://{host}:{port}[/cyan]  —  Ctrl-C to stop"
    )
    uvicorn.run(application, host=host, port=port)


@app.command()
def attest(
    in_dir: Annotated[
        Path | None,
        typer.Option("--in", help="Directory with a prior report.json to attest. Omit to run one."),
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
    DSSE-style envelope (Ed25519). It is evidence, not certification.
    """
    # -- verification mode -------------------------------------------------------------------
    if verify is not None:
        try:
            bundle = load_bundle(verify)
        except (FileNotFoundError, ValidationError):
            _fail(f"{verify} is not a readable attestation bundle")
            return
        pub_bytes = pubkey.read_bytes() if pubkey is not None else None
        try:
            result = verify_bundle(bundle, public_key_pem_bytes=pub_bytes)
        except MissingAttestExtraError as exc:
            _fail(str(exc))
            return
        for reason in result.reasons:
            _out.print(f"  - {reason}")
        if result.ok:
            _out.print("[green]attestation OK[/green]")
        else:
            _fail("attestation verification FAILED", code=1)
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

    try:
        bundle, pub_pem = to_bundle(
            report, issued_at=issued_at, commit=stamp,
            private_key_pem=private_key_pem, sign=not no_sign,
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
    lo, hi = wilson_ci(report.successes, report.attempts) if report.attempts else (0.0, 0.0)
    fpr = "n/a" if report.benign_fpr is None else f"{100.0 * report.benign_fpr:.1f}%"
    _out.print("\n[bold]Attestation[/bold]")
    _out.print(f"  subject   : {report.policy} x {report.suite}")
    _out.print(f"  evidence  : ASR {100.0 * report.asr:.1f}% "
               f"[{100.0 * lo:.0f}-{100.0 * hi:.0f}%], benign FPR {fpr}")
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
    for rank, row in enumerate(leaderboard.rows, start=1):
        ci = "" if row.ci95 is None else f" [{100.0 * row.ci95[0]:.0f}-{100.0 * row.ci95[1]:.0f}%]"
        transfer = "[green]real[/green]" if row.transfer_status == "real-transfer" else "stub"
        table.add_row(
            str(rank),
            row.policy,
            row.suite,
            row.family,
            f"{100.0 * row.asr:.1f}%{ci}",
            f"{row.successes}/{row.attempts}",
            transfer,
        )
    _out.print(table)


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
) -> None:
    """Aggregate report.json files into a ranked leaderboard.json (deterministic; real + signed)."""
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


if __name__ == "__main__":  # pragma: no cover
    app()
