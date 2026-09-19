# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""`offline-study` and `sim-to-real`.

The two studies that read a recorded dataset rather than stepping a simulator."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Annotated

import typer

from provael import __version__
from provael.attest import RULESET_VERSION
from provael.cli._shared import _emit_execution_manifest, _err, _fail, _git_commit, _out, app
from provael.config import RunConfig
from provael.coverage import HARDWARE_DIR_NAME
from provael.datasets.lerobot_frames import DatasetRejected, load_info
from provael.evidence import EvidenceState
from provael.manifest import to_evidence_manifest_json
from provael.report import (
    render_summary,
    write_report,
)
from provael.runner import run
from provael.studies.offline_runner import run_offline_study


@app.command("offline-study")
def offline_study_cmd(
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run/--no-dry-run",
            help="Validate the open-loop pipeline against the deterministic CPU stub, with no "
            "dataset download. The real path needs the [lerobot] extra and a GPU.",
        ),
    ] = True,
    dataset: Annotated[
        str | None,
        typer.Option(
            "--dataset", help="LeRobotDataset repo id. Validated before anything is read."
        ),
    ] = None,
    frames: Annotated[
        int,
        typer.Option("--frames", help="Frames to sample. Fix this in the pre-registration BEFORE "
                     "looking at any data, not after."),
    ] = 200,
    instruction: Annotated[
        str, typer.Option("--instruction", help="The operator's benign instruction.")
    ] = "pick up the cube",
    attack: Annotated[
        str, typer.Option("--attack", help="Registered attack name, e.g. roleplay.")
    ] = "roleplay",
    model_id: Annotated[
        str,
        typer.Option(
            "--model",
            help="Policy checkpoint. Defaults to smolvla_base, whose 6-dim state matches an "
            "SO-101. The LIBERO-finetuned checkpoint behind the published simulation result "
            "expects an 8-dim state and CANNOT consume SO-101 observations.",
        ),
    ] = "lerobot/smolvla_base",
    rename_map: Annotated[
        str | None,
        typer.Option(
            "--rename-map",
            help='JSON mapping dataset observation keys to the checkpoint\'s, e.g. '
            '\'{"observation.images.ego": "observation.images.camera1"}\'. Required when the '
            "dataset's camera names differ from the checkpoint's, which is the normal case.",
        ),
    ] = None,
    device: Annotated[
        str,
        typer.Option("--device", help="Torch device. CPU is the default and is enough: this study "
                     "only does forward passes, it renders and steps nothing."),
    ] = "cpu",
    out: Annotated[
        Path | None, typer.Option("--out", help="Directory to write offline-observation.json into.")
    ] = None,
) -> None:
    """Open-loop attack measurement on RECORDED frames of a real robot dataset.

    Asks the policy what it WOULD do, twice, about the same real observation — once with the
    operator's instruction, once with the attacker's. Nothing executes and no robot moves.

    This is not a real-robot attack success rate. It cannot become one: the study emits its own
    artifact type with no `asr` field, and earns the `real-forward` rung, which sits BELOW
    `real-episode` because an episode at least executes. See
    docs/studies/offline-real-observation.md.
    """
    if not dry_run:
        if dataset is None:
            _fail("--no-dry-run needs --dataset. The protocol names selection criteria, not a "
                  "default: pinning one third-party repo puts someone else's housekeeping in the "
                  "critical path. See docs/studies/offline-real-observation.md.")
        try:
            info = load_info(str(dataset))
        except DatasetRejected as exc:
            _fail(str(exc))
        except ImportError:
            _fail("reading a real dataset needs huggingface_hub: pip install 'provael[lerobot]'")
        _out.print(
            f"[green]dataset accepted[/]: {dataset} — {info.robot_type}, "
            f"{info.state_dim}-DoF, {info.total_frames} frames, cameras {list(info.camera_keys)}"
        )

        try:
            from provael.datasets.lerobot_frames import iter_frames  # noqa: PLC0415
            from provael.policies.lerobot_adapter import LeRobotAdapter  # noqa: PLC0415
        except ImportError as exc:
            _fail(f"the [lerobot] extra is required: pip install 'provael[lerobot]' ({exc})")

        # CPU by default, unlike the simulation studies. Those need a GPU because they render and
        # step a simulator; this only does forward passes. Defaulting to cuda would make the
        # cheapest honest study in the project look like it needed hardware it does not.
        mapping: dict[str, str] | None = None
        if rename_map:
            try:
                mapping = json.loads(rename_map)
            except json.JSONDecodeError as exc:
                _fail(f"--rename-map is not valid JSON: {exc}")

        # A checkpoint whose state dimension does not match the dataset's cannot consume it, and
        # the failure downstream is an opaque shape error rather than a statement of the problem.
        # Checked here so the message names the actual mismatch. This is not pedantry: the
        # LIBERO-finetuned SmolVLA behind the published 10/10 has an 8-dim state and an SO-101 has
        # 6, so the obvious choice of checkpoint is the wrong one and fails confusingly.
        adapter = LeRobotAdapter(
            model_id=model_id,
            device=device,
            dataset_repo_id=str(dataset),
            rename_map=mapping,
        )
        adapter.load()
        frame_iter = iter_frames(str(dataset), limit=frames)
        report = run_offline_study(
            adapter,
            frame_iter,
            benign_instruction=instruction,
            attack_name=attack,
            tool_version=__version__,
            dataset=str(dataset),
            robot_type=info.robot_type,
            policy_name="smolvla",
            model=model_id,
        )
    else:
        # The dry run walks the SAME loop against the deterministic stub, so what it proves is the
        # pipeline and not a mock of it. Previously it fabricated two action vectors, which checked
        # the artifact shape and nothing else — and the shape was never the risky part.
        # 6-DoF on purpose: the stub's default is 11 channels, and the dry run stands in for an
        # SO-101, which has 6. A dimension mismatch between the stub and the arm it is rehearsing
        # would make the dry run pass on a shape no real dataset produces — which is exactly the
        # class of thing a dry run exists to catch, so it must not be the thing it hides.
        from provael.policies.stub import StubPolicy  # noqa: PLC0415

        stub = StubPolicy(action_dim=6)
        stub.load()
        synthetic = [
            ({"state": [0.01 * i] * 6}, [0.0] * 6, [0.01 * i] * 6)
            for i in range(12)
        ]
        report = run_offline_study(
            stub,
            synthetic,
            benign_instruction=instruction,
            attack_name=attack,
            tool_version=__version__,
            dataset="(dry-run: deterministic stub, no dataset read)",
            robot_type="so101_follower",
            policy_name="stub",
        )

    problems: list[str] = []
    if report.evidence_state != EvidenceState.REAL_FORWARD.value:
        problems.append(f"evidence_state is {report.evidence_state!r}, expected real-forward")
    if report.hardware_runs != 0:
        problems.append("hardware_runs is non-zero on an open-loop study")
    keys = set(json.loads(report.model_dump_json()))
    leaked = {"asr", "successes", "attempts"} & keys
    if leaked:
        problems.append(
            f"artifact carries run-report field(s) {sorted(leaked)} — invites the misread"
        )
    if problems:
        _fail("FAILED its own shape assertions:\n  " + "\n  ".join(problems))

    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        (out / "offline-observation.json").write_text(
            report.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        _out.print(f"wrote {out / 'offline-observation.json'}")

    # The dry run deliberately does NOT print its rates. They are properties of a deterministic
    # fixture on synthetic states — a "100% envelope violations" line is one screenshot away from
    # being quoted as a finding, and it would be quoting the stub. The pipeline is what is being
    # checked here, so the pipeline is what gets reported.
    if dry_run:
        _out.print(
            f"[green]dry run OK[/] — pipeline walked {report.frames_compared} frames end to end "
            "and the artifact passed its own shape assertions."
        )
        _out.print(
            "[dim]Rates withheld on purpose: on the stub they are properties of the fixture, not "
            "measurements. Run with --dataset to get numbers that mean something.[/]"
        )
    else:
        _out.print(f"[green]measured[/] — {report.frames_compared} frames, "
                   f"median divergence {report.divergence_median:.3f}, "
                   f"envelope violations {report.envelope_violation_rate:.0%} "
                   f"(benign control {report.benign_envelope_violation_rate:.0%})")
    _out.print(f"[dim]evidence rung: {report.evidence_state} (below real-episode, by design)[/]")
    _out.print(
        "\n[yellow]Still zero physical runs.[/] This validated the open-loop pipeline, not a "
        "policy on an arm. Nothing executed; no robot moved."
    )


@app.command("sim-to-real")
def sim_to_real_cmd(
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run/--no-dry-run",
            help="Validate the whole protocol against the deterministic CPU stub. Required "
            "until hardware is attached — there is no non-dry path yet.",
        ),
    ] = True,
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Where to write the dry-run artifacts (default: a temp dir)."),
    ] = None,
) -> None:
    """Dry-run the pre-registered sim-to-real protocol, so the first physical session is
    not also the first debugging session.

    Walks the SAME code path a physical run will take — runner, scoring, report, execution manifest,
    evidence manifest — against the deterministic CPU stub, and asserts the artifact shape a real
    run must produce. The point is that when the arm arrives you are executing, not plumbing.

    IT PRODUCES NO HARDWARE RESULT, and it deliberately cannot: the artifacts land in a temp
    directory (or an explicit --out) and NEVER in results/hardware/, because `provael coverage`
    counts that directory and provael.com renders its "not yet measured" claim from the count. A
    dry-run that incremented it would make the website assert a physical result that does not exist.

    The protocol is pre-registered at docs/studies/sim-to-real-so101.md; that file is the source of
    record and this command mirrors its instruction-family arm.
    """
    if not dry_run:
        _fail(
            "there is no non-dry sim-to-real path yet: no physical hardware is attached, and this "
            "tool ships no robot-control code (see SAFETY.md — moving an arm is LeRobot's job, "
            "under an operator with an E-stop).\n"
            "  Runs land in results/hardware/ once they exist; that directory documents the "
            "protocol and the hardware it is written for.\n"
            "  Drop --no-dry-run to validate the pipeline against the stub."
        )
        return


    dest = out or Path(tempfile.mkdtemp(prefix="provael-sim2real-dry-"))
    dest.mkdir(parents=True, exist_ok=True)
    if HARDWARE_DIR_NAME in dest.parts:
        _fail(
            f"refusing to write a dry run into a path containing '{HARDWARE_DIR_NAME}/': that "
            "directory is counted as physical-robot evidence and the website renders its "
            "sim-to-real claim from the count."
        )
        return

    _out.print(
        "[dim]Dry run — the deterministic CPU stub, not a robot. No hardware result.[/dim]\n"
    )

    # The instruction arm of the pre-registered protocol, run against the stub so the shape is
    # exercised without a policy download or a GPU.
    started = time.perf_counter()
    report = run(
        RunConfig(
            policy="stub", suite="stub",
            attacks=["none", "instruction"],
            episodes=10, seed=0,
        )
    )
    elapsed = time.perf_counter() - started
    write_report(report, dest)
    _emit_execution_manifest(report, dest, elapsed=elapsed)
    (dest / "evidence-manifest.json").write_text(
        to_evidence_manifest_json(
            report,
            repository="https://github.com/provael/provael",
            commit=_git_commit() or f"v{__version__}",
            regulatory_clock_version=RULESET_VERSION,
        ),
        encoding="utf-8",
    )

    # Assert the shape a physical run must produce. Failing here, now, is the whole point.
    problems: list[str] = []
    for name in ("report.json", "execution-manifest.json", "evidence-manifest.json"):
        if not (dest / name).is_file():
            problems.append(f"missing {name}")
    manifest = json.loads((dest / "execution-manifest.json").read_text(encoding="utf-8"))
    # Identical second-granularity stamps are expected for a sub-second stub run and are only a
    # defect once a run is long enough to span a second boundary — which every physical run is.
    if elapsed >= 1.0 and manifest.get("started_at") == manifest.get("ended_at"):
        problems.append(
            "execution manifest records identical started_at/ended_at for a run that took "
            f"{elapsed:.1f}s — a physical run must record distinct instants"
        )
    if str(manifest.get("ended_at", "")).endswith("T00:00:00Z"):
        problems.append(
            "execution manifest ended_at is exact midnight UTC, which the freshness badge reads as "
            "a reconstructed date rather than an observed one"
        )
    for field in ("python_version", "os", "report_digest"):
        if not manifest.get(field):
            problems.append(f"execution manifest is missing {field}")
    if problems:
        _err.print("[red]dry run produced a malformed artifact set:[/red]")
        for problem in problems:
            _err.print(f"  - {problem}")
        raise typer.Exit(1)

    render_summary(report, _out)
    _out.print(f"\n[green]✓[/green] artifact set validates → [cyan]{dest}[/cyan]")
    _out.print(
        "  report.json · execution-manifest.json · evidence-manifest.json\n"
        f"  provenance recorded: started_at {manifest['started_at']} → "
        f"ended_at {manifest['ended_at']}"
    )
    _out.print(
        "\n[dim]Still zero physical runs. This validated the pipeline, not the policy on an "
        "arm — see results/hardware/README.md for what is blocked and on what.[/dim]"
    )
