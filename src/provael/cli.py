"""``provael`` command-line interface.

Commands:
  * ``attack``         — run a red-team evaluation and write a report.
  * ``list-policies``  — show registered policies and whether they're runnable here.
  * ``list-attacks``   — show registered attacks and families.
  * ``report``         — print a previously written report.
  * ``version``        — print the tool version.

Errors that a user can act on (missing ``[lerobot]`` extra, unknown policy / suite /
attack, bad config) are caught and printed as a single clear line with a non-zero
exit code — never a raw traceback.
"""

from __future__ import annotations

import json
import time
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from provael import __version__
from provael.attacks.registry import (
    available_attacks,
    available_families,
    make_attack,
)
from provael.calibration import calibrate_suite, load_calibrations, save_calibration
from provael.compliance import (
    COMPLIANCE_JSON,
    to_compliance_json,
    write_compliance_json,
    write_compliance_markdown,
)
from provael.config import RunConfig
from provael.leaderboard import Leaderboard, build_leaderboard
from provael.policies.lerobot_adapter import IncompatiblePolicyError, MissingLeRobotError
from provael.policies.registry import (
    available_policies,
    policy_extra,
    policy_is_ready,
)
from provael.recipes import RECIPES, available_recipes, load_recipe
from provael.report import load_report, render_summary, write_report
from provael.reproductions import available_reproductions, get_reproduction
from provael.runner import run
from provael.sarif import to_sarif_json, write_sarif
from provael.scorecard import SCORECARD_MD, to_scorecard_markdown, write_scorecard


class OutputFormat(StrEnum):
    """Console / artifact output format for ``attack`` and ``report``."""

    table = "table"
    sarif = "sarif"
    compliance = "compliance"
    scorecard = "scorecard"


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
            "compliance, a '.md' suffix writes the human-readable report, else JSON.",
        ),
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
    render_summary(loaded, _out)


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
    table.add_column("ASR", justify="right", style="bold red")
    table.add_column("successes", justify="right")
    table.add_column("attempts", justify="right")
    for rank, row in enumerate(leaderboard.rows, start=1):
        table.add_row(
            str(rank),
            row.policy,
            row.suite,
            row.family,
            f"{100.0 * row.asr:.1f}%",
            str(row.successes),
            str(row.attempts),
        )
    _out.print(table)


@leaderboard_app.command("build")
def leaderboard_build(
    runs: Annotated[
        list[str] | None,
        typer.Option(help="Run dir(s), glob(s), or report.json path(s). Quote globs."),
    ] = None,
    out: Annotated[Path, typer.Option(help="Output directory for leaderboard.json.")] = Path(
        "leaderboard/results"
    ),
) -> None:
    """Aggregate report.json files into a ranked, deterministic leaderboard.json."""
    try:
        out_path, leaderboard = build_leaderboard(runs or ["runs"], out)
    except FileNotFoundError as exc:
        _fail(str(exc))
        return
    _render_leaderboard(leaderboard)
    _out.print(f"\nWrote [cyan]{out_path}[/cyan]")


if __name__ == "__main__":  # pragma: no cover
    app()
