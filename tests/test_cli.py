"""CLI smoke tests via typer's CliRunner."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from vla_redteam import __version__
from vla_redteam.cli import app
from vla_redteam.report import load_report

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_list_policies() -> None:
    result = runner.invoke(app, ["list-policies"])
    assert result.exit_code == 0
    assert "stub" in result.output
    assert "smolvla" in result.output


def test_list_attacks() -> None:
    result = runner.invoke(app, ["list-attacks"])
    assert result.exit_code == 0
    assert "roleplay" in result.output
    assert "instruction" in result.output


def test_attack_runs_and_writes_report(tmp_path: Path) -> None:
    out = tmp_path / "run"
    result = runner.invoke(
        app,
        [
            "attack",
            "--policy", "stub",
            "--suite", "stub",
            "--attacks", "instruction",
            "--episodes", "5",
            "--seed", "0",
            "--out", str(out),
        ],
    )
    assert result.exit_code == 0
    assert (out / "report.json").exists()
    assert (out / "report.md").exists()

    report = load_report(out)
    assert report.attempts == 15  # 1 task x 3 attacks x 5 episodes
    assert 0.0 <= report.asr <= 1.0
    assert "ASR" in result.output  # headline printed


def test_attack_runs_all_three_families(tmp_path: Path) -> None:
    out = tmp_path / "run"
    result = runner.invoke(
        app,
        [
            "attack",
            "--policy", "stub",
            "--suite", "stub",
            "--attacks", "instruction,visual,injection",
            "--episodes", "5",
            "--seed", "0",
            "--out", str(out),
        ],
    )
    assert result.exit_code == 0
    report = load_report(out)
    # 1 task x 7 attacks (3 instruction + 2 visual + 2 injection) x 5 episodes.
    assert report.attempts == 35
    assert set(report.attacks) == {
        "roleplay", "goal_substitution", "paraphrase",
        "patch", "decoy_object", "scene_text", "mcp_tool_desc",
    }


def test_list_attacks_shows_new_families() -> None:
    result = runner.invoke(app, ["list-attacks"])
    assert result.exit_code == 0
    for token in ("patch", "scene_text", "visual", "injection"):
        assert token in result.output


def test_report_command_round_trips(tmp_path: Path) -> None:
    out = tmp_path / "run"
    assert runner.invoke(app, ["attack", "--episodes", "5", "--out", str(out)]).exit_code == 0
    result = runner.invoke(app, ["report", "--in", str(out)])
    assert result.exit_code == 0
    assert "ASR" in result.output


def test_smolvla_without_extra_exits_cleanly() -> None:
    result = runner.invoke(app, ["attack", "--policy", "smolvla", "--episodes", "2"])
    # Clean, actionable failure — not a crash (exit 1 from an uncaught exception).
    assert result.exit_code == 2
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_unknown_attack_exits_cleanly() -> None:
    result = runner.invoke(app, ["attack", "--attacks", "bogus", "--episodes", "2"])
    assert result.exit_code == 2
