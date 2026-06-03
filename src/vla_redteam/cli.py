"""``robopwn`` command-line interface.

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

import time
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from vla_redteam import __version__
from vla_redteam.attacks.registry import (
    available_attacks,
    available_families,
    make_attack,
)
from vla_redteam.config import RunConfig
from vla_redteam.leaderboard import Leaderboard, build_leaderboard
from vla_redteam.policies.lerobot_adapter import IncompatiblePolicyError, MissingLeRobotError
from vla_redteam.policies.registry import (
    REQUIRES_LEROBOT,
    available_policies,
    policy_is_ready,
)
from vla_redteam.report import load_report, render_summary, write_report
from vla_redteam.runner import run

app = typer.Typer(
    name="robopwn",
    help="RoboPwn — red-team open Vision-Language-Action (VLA) robot policies in simulation.",
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
    """Print the RoboPwn / vla-redteam version."""
    _out.print(f"robopwn (vla-redteam) {__version__}")


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
        note = (
            escape("requires `vla-redteam[lerobot]` (GPU)")
            if name in REQUIRES_LEROBOT
            else "CPU, no deps"
        )
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


@app.command()
def attack(
    policy: Annotated[str, typer.Option(help="Registered policy name.")] = "stub",
    suite: Annotated[str, typer.Option(help="Registered suite name.")] = "stub",
    attacks: Annotated[
        str, typer.Option(help="Comma-separated attack or family names.")
    ] = "instruction",
    episodes: Annotated[int, typer.Option(min=1, help="Episodes per (task, attack) pair.")] = 10,
    seed: Annotated[int, typer.Option(min=0, help="Base random seed.")] = 0,
    horizon: Annotated[int, typer.Option(min=1, help="Max timesteps per episode.")] = 8,
    tasks: Annotated[
        str | None, typer.Option(help="Comma-separated task subset (default: all).")
    ] = None,
    out: Annotated[Path, typer.Option(help="Output directory for reports.")] = Path("runs/stub"),
) -> None:
    """Run a red-team evaluation and write report.json + report.md."""
    try:
        config = RunConfig(
            policy=policy,
            suite=suite,
            attacks=_split_csv(attacks) or ["instruction"],
            tasks=_split_csv(tasks),
            episodes=episodes,
            seed=seed,
            horizon=horizon,
            out=out,
        )
    except ValidationError as exc:
        _fail(f"invalid configuration: {exc.errors()[0]['msg']}")
        return

    started = time.perf_counter()
    try:
        report = run(config)
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


@app.command()
def report(
    in_dir: Annotated[Path, typer.Option("--in", help="Directory containing report.json.")],
) -> None:
    """Print a summary of a previously written report."""
    try:
        loaded = load_report(in_dir)
    except FileNotFoundError as exc:
        _fail(str(exc))
        return
    except ValidationError:
        _fail(f"{in_dir} does not contain a valid RoboPwn report.json")
        return
    render_summary(loaded, _out)


def _render_leaderboard(leaderboard: Leaderboard) -> None:
    if leaderboard.is_demo:
        _out.print(
            "[yellow]demo data[/yellow]: stub-policy results only — add real "
            "SmolVLA/OpenVLA runs for live numbers (see leaderboard/README.md)."
        )
    table = Table(title="RoboPwn — ASR leaderboard (policy x suite x family)", title_style="bold")
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
