"""The sim-to-real dry run: exercise the physical-run pipeline before there is a robot.

WHY THIS TEST EXISTS. The pre-registered protocol has been sitting unrun since 24 July, and when
hardware finally arrives the expensive failure is discovering that the artifact plumbing was never
exercised — a session spent debugging serialisation instead of measuring a policy. This walks the
same code path a physical run takes (runner, scoring, report, execution manifest, evidence manifest)
against the deterministic CPU stub, and asserts the artifact shape a real run must produce.

IT MUST NEVER PRODUCE A HARDWARE RESULT. `provael coverage` counts `results/hardware/` and
provael.com renders its "not yet measured" sim-to-real claim from that count, so a dry run that
wrote there would make the website assert a physical result that does not exist. That is asserted
below, not just documented.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from provael.cli import app
from provael.coverage import HARDWARE_DIR_NAME, coverage
from provael.watch import _is_recorded

runner = CliRunner()


def test_dry_run_emits_the_full_artifact_set(tmp_path: Path) -> None:
    """The three files a physical run must produce, all present and parseable."""
    result = runner.invoke(app, ["sim-to-real", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    for name in ("report.json", "execution-manifest.json", "evidence-manifest.json"):
        path = tmp_path / name
        assert path.is_file(), f"{name} missing"
        json.loads(path.read_text(encoding="utf-8"))  # parses


def test_the_dry_run_manifest_would_read_as_RECORDED_not_reconstructed(tmp_path: Path) -> None:
    """The shape that matters for the freshness badge.

    A physical run's manifest must be classified `recorded`; if the dry run's is not, the real one
    will not be either, and the badge would mark a genuine hardware measurement as an approximate
    date. This is exactly the trap the one legacy run fell into.
    """
    assert runner.invoke(app, ["sim-to-real", "--out", str(tmp_path)]).exit_code == 0
    manifest = json.loads((tmp_path / "execution-manifest.json").read_text(encoding="utf-8"))
    assert _is_recorded(manifest), (
        "the dry run's manifest reads as a reconstructed timestamp, so a real hardware run's would "
        f"too: evidence_state={manifest.get('evidence_state')!r} ended_at={manifest.get('ended_at')!r}"
    )
    assert manifest["python_version"] and manifest["os"] and manifest["report_digest"]


def test_dry_run_refuses_to_write_into_the_hardware_directory(tmp_path: Path) -> None:
    """The guard that stops a dry run inflating the physical-evidence count."""
    forbidden = tmp_path / HARDWARE_DIR_NAME / "run-1"
    result = runner.invoke(app, ["sim-to-real", "--out", str(forbidden)])
    assert result.exit_code != 0
    assert "refusing" in result.output.lower()


def test_dry_run_does_not_change_the_hardware_count(tmp_path: Path) -> None:
    before = coverage().hardware_results
    assert runner.invoke(app, ["sim-to-real", "--out", str(tmp_path)]).exit_code == 0
    assert coverage().hardware_results == before == 0


def test_there_is_no_non_dry_path_and_it_says_why() -> None:
    """`--no-dry-run` must fail with a reason, not silently attempt to drive a robot.

    The tool ships no robot-control code by design (SAFETY.md); moving an arm is LeRobot's job under
    an operator with an E-stop. A flag that looked like it would run hardware and then did something
    ambiguous is worse than one that refuses and explains.
    """
    result = runner.invoke(app, ["sim-to-real", "--no-dry-run"])
    assert result.exit_code != 0
    out = result.output.lower()
    assert "no non-dry sim-to-real path" in out
    assert "results/hardware" in out


def test_hardware_directory_is_committed_and_honestly_empty() -> None:
    """The empty directory is the point: a directory that appears only with results counts nothing."""
    hardware = Path(__file__).resolve().parent.parent / "results" / HARDWARE_DIR_NAME
    assert hardware.is_dir(), "results/hardware/ must exist before the first run, not after"
    assert (hardware / "README.md").is_file()
    assert not list(hardware.rglob("report.json")), "a run appeared; update the count-dependent copy"
    text = (hardware / "README.md").read_text(encoding="utf-8")
    assert "Runs executed to date: 0" in text
