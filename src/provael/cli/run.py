"""The two commands that execute a run: `attack` and `reproduce`."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.markup import escape

from provael.calibration import load_calibrations
from provael.cli._shared import (
    OutputFormat,
    _decide,
    _emit_execution_manifest,
    _err,
    _fail,
    _load_protocol,
    _out,
    _split_csv,
    _write_defense_log,
    app,
)
from provael.compliance import (
    COMPLIANCE_JSON,
    write_compliance_json,
)
from provael.config import RunConfig
from provael.mlbom import ML_BOM_JSON, write_ml_bom
from provael.oscal import OSCAL_JSON, write_oscal
from provael.policies.lerobot_adapter import IncompatiblePolicyError, MissingLeRobotError
from provael.recipes import load_recipe
from provael.report import (
    render_summary,
    write_report,
)
from provael.reproductions import get_reproduction
from provael.runner import run
from provael.sarif import write_sarif
from provael.scorecard import SCORECARD_MD, write_scorecard
from provael.verdict import write_decision


@app.command()
def attack(
    ctx: typer.Context,
    policy: Annotated[str, typer.Option(help="Registered policy name.")] = "stub",
    suite: Annotated[str, typer.Option(help="Registered suite name.")] = "stub",
    attacks: Annotated[
        str, typer.Option(help="Comma-separated attack or family names.")
    ] = "instruction",
    episodes: Annotated[
        int, typer.Option(min=1, help="Total episodes per (task, attack) pair.")
    ] = 10,
    seeds: Annotated[
        int | None,
        typer.Option(min=1, help="Number of DISTINCT seeds. With --episodes-per-seed, total "
                     "episodes = seeds x episodes-per-seed."),
    ] = None,
    episodes_per_seed: Annotated[
        int,
        typer.Option(min=1, help="Repeats at the SAME seed. >1 separates policy stochasticity "
                     "from initial-state variation; 1 (default) is the historical behaviour."),
    ] = 1,
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
    resume: Annotated[
        Path | None,
        typer.Option(
            "--resume",
            help="Append-only trial ledger (JSONL). Episodes already in it are replayed instead "
                 "of re-measured, so a preempted run continues rather than restarting. Creates "
                 "the file if absent. Not usable with --episodes-per-seed > 1.",
        ),
    ] = None,
    video_dir: Annotated[
        Path | None,
        typer.Option(
            "--video-dir",
            help="Write one MP4 per episode here: the frames the policy actually saw, "
                 "red-bordered from the first unsafe step. Off by default; never changes the "
                 "report. Needs imageio + imageio-ffmpeg (both ship with provael[lerobot]). "
                 "Episodes replayed from a --resume ledger have no clip.",
        ),
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
    protocol: Annotated[
        Path | None,
        typer.Option(
            "--protocol",
            help="Acceptance protocol (YAML/JSON; see examples/assessment/) the release decision "
            "is made against. Writes report.decision.json beside report.json. Without it the "
            "run is a diagnostic: measured, and its acceptance not assessed.",
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

    # `--seeds` and `--episodes` both determine the total, so passing both resolves by source order
    # and the reported `n` is not the one the caller asked for. They stay mutually exclusive.
    if _explicit("episodes") and _explicit("seeds"):
        _fail("--seeds and --episodes both set the total; pass only one")
        return

    # --seeds now means what its name says: the number of DISTINCT seeds. It used to be a pure alias
    # for --episodes, which was accurate only while an episode was a seed. Now that repeats exist,
    # an alias would make `--seeds 10 --episodes-per-seed 3` quietly mean "3 seeds", the opposite of
    # what it reads as. The total is derived instead.
    if _explicit("seeds") and seeds is not None:
        episodes = seeds * episodes_per_seed

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
    if _explicit("episodes") or _explicit("seeds"):
        overrides["episodes"] = episodes
    if _explicit("episodes_per_seed"):
        overrides["episodes_per_seed"] = episodes_per_seed
    # (--seeds no longer writes `episodes` directly; the total is derived above so that
    # episodes-per-seed is accounted for. Overwriting it here was silently discarding the repeats.)
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

    acceptance = _load_protocol(protocol)
    if protocol is not None and acceptance is None:
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
        report = run(
            config, calibrations, audit_sink=defense_audit, ledger_path=resume, video_dir=video_dir
        )
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
    decision = _decide(report, acceptance)
    if acceptance is not None:
        decision_path = write_decision(decision, config.out)
        _out.print(
            f"Release decision under protocol [cyan]{acceptance.name}[/cyan]: "
            f"[bold]{decision.verdict.value}[/bold] -> [cyan]{decision_path}[/cyan]"
        )
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
        scorecard_target = write_scorecard(report, config.out / SCORECARD_MD, decision=decision)
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
