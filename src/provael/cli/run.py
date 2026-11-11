# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The two commands that execute a run: `attack` and `reproduce`."""

from __future__ import annotations

import contextlib
import json
import time
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.markup import escape

from provael.attacks.registry import INSTRUCTION_CHANNEL_FAMILIES, attack_names, with_controls
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
from provael.coverage import FIXTURE_POLICIES
from provael.mlbom import ML_BOM_JSON, write_ml_bom
from provael.oscal import OSCAL_JSON, write_oscal
from provael.policies.lerobot_adapter import IncompatiblePolicyError, MissingLeRobotError
from provael.policies.registry import REQUIRES_LEROBOT
from provael.recipes import FULL_SWEEP, fixture_only_families, full_sweep_attacks, load_recipe
from provael.report import (
    render_summary,
    write_report,
)
from provael.reproductions import get_reproduction
from provael.runner import (
    CompetenceCheckError,
    InitStatePlanError,
    ResumeModeError,
    ScenePinError,
    UnreadParameterError,
    run,
)
from provael.runtime_versions import drift_warnings, installed_versions
from provael.sarif import write_sarif
from provael.scorecard import SCORECARD_MD, write_scorecard
from provael.sidecars import (
    CHUNKS_NPZ,
    TIMING_JSON,
    ChunkLog,
    TimingLog,
    write_chunks,
    write_timing,
)
from provael.suites.libero import suite_and_ids_from_tasks
from provael.verdict import write_decision


def _add_controls(overrides: dict[str, object], base: dict[str, object]) -> None:
    """Add the benign control and the control family to an instruction-channel run, and say so.

    Reads the attack list the run will use (an explicit ``--attacks``, else the recipe's, else
    :class:`~provael.config.RunConfig`'s default) and writes the extended list into ``overrides``
    only when :func:`~provael.attacks.registry.with_controls` changed it, naming every arm it added
    on stderr so the run's shape is never a surprise. A list that is not a list of names is left
    for the configuration's own validation to refuse.
    """
    current = overrides.get(
        "attacks", base.get("attacks", RunConfig.model_fields["attacks"].get_default(
            call_default_factory=True
        ))
    )
    if not isinstance(current, list) or not all(isinstance(t, str) for t in current):
        return
    extended = with_controls(current)
    if extended == current:
        return
    overrides["attacks"] = extended
    before = set(attack_names(current))
    added = [name for name in attack_names(extended) if name not in before]
    _err.print(
        "[yellow]note:[/yellow] the run includes an instruction-channel family, so it also runs "
        f"the controls it is read against: {', '.join(added)}. Pass --no-controls to run only "
        "the arms named."
    )


@app.command()
def attack(
    ctx: typer.Context,
    policy: Annotated[str, typer.Option(help="Registered policy name.")] = "stub",
    suite: Annotated[str, typer.Option(help="Registered suite name.")] = "stub",
    attacks: Annotated[
        str, typer.Option(help="Comma-separated attack or family names.")
    ] = "instruction",
    no_controls: Annotated[
        bool,
        typer.Option(
            "--no-controls",
            help="Run only the arms named. By default a run that includes an instruction-channel "
            f"family ({', '.join(INSTRUCTION_CHANNEL_FAMILIES)}) also gets the benign control "
            "`none` and the `control` family (the harmless-variation arms), because an "
            "instruction-channel rate is read against both.",
        ),
    ] = False,
    competence_check: Annotated[
        int | None,
        typer.Option(
            "--competence-check",
            min=1,
            help="Before the arms, run this many benign episodes per task (at the seeds after the "
            "run's own) and refuse the adversarial arms on a task whose task success falls below "
            "--competence-floor. The report records each task's pre-run and any refusal; the "
            "pre-run's episodes enter no rate. Off by default; not with --resume.",
        ),
    ] = None,
    competence_floor: Annotated[
        float,
        typer.Option(
            "--competence-floor",
            min=0.0,
            max=1.0,
            help="The task success a task's --competence-check pre-run must reach for its "
            "adversarial arms to run (default 0.8).",
        ),
    ] = 0.8,
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
    pin_init_states: Annotated[
        int | None,
        typer.Option(
            "--pin-init-states",
            min=0,
            help="Pin each episode's starting scene on a suite with a fixed list of initial "
            "states (LIBERO): the episode at seed s starts from state (START + s) mod their "
            "number, for every arm and repeat, whatever the episode before it did. Off by "
            "default, where lerobot walks the list with a reset counter the seed never reaches. "
            "A suite without such a list refuses it. The GPU arm's plan step checks the pinned "
            "states against the calibration fit's (#136).",
        ),
    ] = None,
    init_states: Annotated[
        Path | None,
        typer.Option(
            "--init-states",
            help="JSON file naming the initial state each episode starts from, per task: "
            '{"libero_object/0": [3, 7], ...}, one entry per seed (every arm and repeat at seed '
            "index i starts from entry i) or, when the only arm is the benign baseline, one per "
            "episode. Any other arm needs one state per seed, so every arm at a seed starts from "
            "one scene. Exclusive with --pin-init-states; needs a suite with fixed initial "
            "states (LIBERO).",
        ),
    ] = None,
    horizon: Annotated[int, typer.Option(min=1, help="Max timesteps per episode.")] = 8,
    termination: Annotated[
        str,
        typer.Option(
            "--termination",
            help="'first-event' (default): an episode stops at its first envelope exit or at "
            "task success. 'fixed-horizon': every episode runs all --horizon steps in every arm, "
            "so Succ-But-Unsafe and how long an episode stayed unsafe are observable. A suite "
            "that cannot step past an event refuses it.",
        ),
    ] = "first-event",
    record_episode_errors: Annotated[
        bool,
        typer.Option(
            "--record-episode-errors",
            help="Record a simulator exception during an episode as an UNJUDGED episode with its "
            "reason, instead of stopping the run. Every rate then excludes it and the report "
            "counts it beside the rate. Off by default.",
        ),
    ] = False,
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
    record_chunks: Annotated[
        bool,
        typer.Option(
            "--record-chunks",
            help="Write chunks.npz beside report.json: every action chunk the policy predicted on "
            "each step, including the rows that never ran, and which row each step executed. "
            "Its sha256 goes in execution-manifest.json. Off by default; never changes the report.",
        ),
    ] = False,
    record_timing: Annotated[
        bool,
        typer.Option(
            "--record-timing",
            help="Write timing.json beside report.json: when each step's observation arrived and "
            "when its action was sent, in nanoseconds since the run started. Wall-clock, so never "
            "in report.json; its sha256 goes in execution-manifest.json. Off by default.",
        ),
    ] = False,
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
    include_fixture_families: Annotated[
        bool,
        typer.Option(
            "--include-fixture-families",
            help="With --recipe full-sweep on a REAL policy, also run the families that have "
            "only ever met the CPU fixture (see `list-attacks` for each family's status). Off by "
            "default: the sweep runs the families with a committed real-policy measurement.",
        ),
    ] = False,
    protocol: Annotated[
        Path | None,
        typer.Option(
            "--protocol",
            help="Acceptance protocol (YAML/JSON; see examples/assessment/) the release decision "
            "is made against. Writes report.decision.json beside report.json. Without it the "
            "run is a diagnostic: measured, and its acceptance not assessed.",
        ),
    ] = None,
    preflight: Annotated[
        bool,
        typer.Option(
            "--preflight",
            help="Before the run, command a +x end-effector delta for a few steps on the run's "
            "first task and refuse the run unless the end-effector moved along +x: a simulator "
            "applying deltas in another frame than it reports the pose in (robosuite issue "
            "819). Uses an environment of its own, so the run's scenes are unchanged. Needs a "
            "suite that reports an end-effector position (LIBERO). Off by default.",
        ),
    ] = False,
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
    if _explicit("pin_init_states"):
        overrides["pin_init_states"] = pin_init_states
    if init_states is not None:
        try:
            overrides["init_states"] = json.loads(init_states.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _fail(f"--init-states {init_states}: {exc}")
            return
    if _explicit("horizon"):
        overrides["horizon"] = horizon
    if _explicit("termination"):
        overrides["termination"] = termination
    if _explicit("record_episode_errors"):
        overrides["record_episode_errors"] = record_episode_errors
    if _explicit("competence_check"):
        overrides["competence_check"] = competence_check
    if _explicit("competence_floor"):
        if overrides.get("competence_check", base.get("competence_check")) is None:
            _fail("--competence-floor applies only with --competence-check N")
            return
        overrides["competence_floor"] = competence_floor
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

    # `full-sweep` is the one recipe whose attack list depends on what it is pointed at: on a real
    # policy it defaults to the families with a committed real-policy measurement, and the
    # fixture-only ones are opt-in (`--include-fixture-families`). Resolved here, after the policy
    # is known and before an explicit `--attacks` (which always wins) is applied.
    resolved_policy = str(overrides.get("policy", base.get("policy", policy)))
    if recipe == FULL_SWEEP and "attacks" not in overrides:
        real_policy = resolved_policy not in FIXTURE_POLICIES
        sweep = full_sweep_attacks(
            real_policy=real_policy, include_fixture_families=include_fixture_families
        )
        base["attacks"] = sweep
        skipped = fixture_only_families() if real_policy and not include_fixture_families else []
        if skipped:
            _err.print(
                f"[yellow]note:[/yellow] full-sweep on a real policy runs the "
                f"{len(sweep) - 2} families with a committed real-policy measurement; "
                f"{len(skipped)} fixture-only families are not run ({', '.join(skipped)}). "
                "Add --include-fixture-families to run them, knowing their only evidence so far "
                "is the CPU fixture."
            )
    elif include_fixture_families:
        _err.print(
            "[yellow]note:[/yellow] --include-fixture-families only changes `--recipe full-sweep`; "
            "it has no effect on this run."
        )

    # Controls by default (P2.1): an instruction-channel arm is read against the benign floor and
    # the harmless-variation controls, so a run that has one gets both unless --no-controls says
    # otherwise. Applied to the final list whatever set it (the flag, a recipe or the default).
    if not no_controls:
        _add_controls(overrides, base)

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

    # The stack the run is about to measure on. A warning, not a refusal: a different stack is a
    # different measurement, and execution-manifest.json records the versions either way.
    # escape(), because the lines name "[lerobot]", which Rich would read as a style tag and drop.
    uses_lerobot = config.suite == "libero" or config.policy in REQUIRES_LEROBOT
    task_suite = None
    if config.suite == "libero":
        # A mixed or unknown task list is refused when the suite is built, below.
        with contextlib.suppress(ValueError):
            task_suite = suite_and_ids_from_tasks(config.tasks or [])[0]
    for line in drift_warnings(
        installed_versions(), suite=config.suite, uses_lerobot=uses_lerobot, task_suite=task_suite
    ):
        _err.print(f"[yellow]warning:[/yellow] {escape(line)}")

    calibrations = None
    if calib is not None:
        calibrations = load_calibrations(calib, config.policy, config.suite)
        if not calibrations:
            _err.print(
                f"[yellow]note:[/yellow] no calibration artifacts for "
                f"{config.policy}/{config.suite} in {calib}; using the default predicate."
            )

    if preflight:
        # Its own suite and environment, before the policy loads: a refusal costs no download.
        from provael.policies.preflight import PreflightError, run_frame_preflight

        try:
            checked = run_frame_preflight(config.suite, config.tasks, config.seed)
        except (MissingLeRobotError, PreflightError) as exc:
            _fail(str(exc))
            return
        _err.print(f"[green]preflight:[/green] {escape(checked.detail)}")

    started = time.perf_counter()
    # The defense audit trail is collected here and written as a SIDECAR, never merged into
    # report.json — a field on RunReport would move the attestation subject digest.
    defense_audit: list[dict[str, str]] = []
    # The opt-in sidecars (P1.5) are filled the same way, and written beside the report below.
    chunk_log = ChunkLog() if record_chunks else None
    timing_log = TimingLog() if record_timing else None
    try:
        report = run(
            config, calibrations, audit_sink=defense_audit, ledger_path=resume,
            video_dir=video_dir, chunk_log=chunk_log, timing_log=timing_log,
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
    except (
        InitStatePlanError,
        ScenePinError,
        ResumeModeError,
        UnreadParameterError,
        CompetenceCheckError,
    ) as exc:
        # A plan that does not fit the run is refused before anything loads; a pinned run whose
        # arms started from different scenes stops rather than writing pairs that are not pairs;
        # a ledger written under the other termination mode is not resumed into this one; an
        # attack setting that was never read is not reported as in force.
        _fail(str(exc))
        return
    elapsed = time.perf_counter() - started

    decision = _decide(report, acceptance)
    json_path, md_path = write_report(report, config.out, decision)
    sidecars: dict[str, str] = {}
    if chunk_log is not None:
        chunks_path, sidecars[CHUNKS_NPZ] = write_chunks(chunk_log, config.out)
        _out.print(f"Wrote [cyan]{chunks_path}[/cyan]  (predicted action chunks)")
        if chunk_log.space is None:
            _err.print(
                f"[yellow]note:[/yellow] policy {config.policy!r} hands over no action chunks; "
                "chunks.npz records the steps and no chunk."
            )
    if timing_log is not None:
        timing_path, sidecars[TIMING_JSON] = write_timing(timing_log, config.out)
        _out.print(f"Wrote [cyan]{timing_path}[/cyan]  (per-step timing)")
    if acceptance is not None:
        decision_path = write_decision(decision, config.out)
        _out.print(
            f"Release decision under protocol [cyan]{acceptance.name}[/cyan]: "
            f"[bold]{decision.verdict.value}[/bold] -> [cyan]{decision_path}[/cyan]"
        )
    _emit_execution_manifest(
        report, config.out, elapsed=elapsed, defense=config.defense, decision=decision,
        sidecars=sidecars or None,
    )
    if config.defense:
        log_path = _write_defense_log(defense_audit, config.out)
        _out.print(f"Defense [cyan]{config.defense}[/cyan] audit trail -> [cyan]{log_path}[/cyan]")
    render_summary(report, _out)
    _out.print(f"\nWrote [cyan]{json_path}[/cyan] and [cyan]{md_path}[/cyan]  ({elapsed:.2f}s)")

    sarif_target = sarif_out or (config.out / "report.sarif" if fmt is OutputFormat.sarif else None)
    if sarif_target is not None:
        write_sarif(report, sarif_target, decision)
        _out.print(f"Wrote [cyan]{sarif_target}[/cyan]  (SARIF 2.1.0)")

    if fmt is OutputFormat.compliance:
        compliance_target = config.out / COMPLIANCE_JSON
        write_compliance_json(report, compliance_target, decision)
        _out.print(f"Wrote [cyan]{compliance_target}[/cyan]  (compliance evidence, JSON)")

    if fmt is OutputFormat.scorecard:
        scorecard_target = write_scorecard(report, config.out / SCORECARD_MD, decision=decision)
        _out.print(f"Wrote [cyan]{scorecard_target}[/cyan]  (pre-deployment ASR scorecard)")

    if fmt is OutputFormat.oscal:
        oscal_target = write_oscal(report, config.out / OSCAL_JSON, decision)
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
