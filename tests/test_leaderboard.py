"""Leaderboard aggregation: correctness, determinism, demo flag, CLI."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from vla_redteam.cli import app
from vla_redteam.config import RunConfig
from vla_redteam.leaderboard import (
    aggregate,
    attack_examples,
    build_leaderboard,
    find_reports,
    load_leaderboard,
    to_json,
)
from vla_redteam.report import write_report
from vla_redteam.runner import run

runner = CliRunner()


def _stub_report():
    return run(
        RunConfig(
            policy="stub",
            suite="stub",
            attacks=["instruction", "visual", "injection"],
            episodes=10,
            seed=0,
        )
    )


def test_aggregate_rows_and_asr() -> None:
    board = aggregate([_stub_report()])
    by_family = {r.family: r for r in board.rows}
    assert (by_family["instruction"].successes, by_family["instruction"].attempts) == (21, 30)
    assert (by_family["visual"].successes, by_family["visual"].attempts) == (14, 20)
    assert (by_family["injection"].successes, by_family["injection"].attempts) == (12, 20)
    # Ranked by ASR descending.
    assert [r.asr for r in board.rows] == sorted((r.asr for r in board.rows), reverse=True)
    assert board.is_demo is True


def test_is_demo_false_with_a_real_policy() -> None:
    stub = _stub_report()
    pretend_real = stub.model_copy(update={"policy": "smolvla"})
    board = aggregate([stub, pretend_real])
    assert board.is_demo is False
    policies = {r.policy for r in board.rows}
    assert policies == {"stub", "smolvla"}


def test_attack_examples_cover_every_attack() -> None:
    names = ["roleplay", "patch", "scene_text", "mcp_tool_desc", "decoy_object"]
    examples = {e.attack: e for e in attack_examples(names)}
    assert set(examples) == set(names)
    # Instruction-family example is the rewritten instruction; obs families show a channel.
    assert "knife" in examples["roleplay"].example.lower()
    assert "visual_tokens" in examples["patch"].example
    assert "scene_text" in examples["scene_text"].example


def test_find_reports_directory_and_glob(tmp_path: Path) -> None:
    write_report(_stub_report(), tmp_path / "a")
    write_report(_stub_report(), tmp_path / "b")
    via_dir = find_reports([str(tmp_path)])
    assert len(via_dir) == 2
    via_glob = find_reports([str(tmp_path / "*")])
    assert sorted(via_glob) == sorted(via_dir)


def test_build_leaderboard_is_deterministic(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    write_report(_stub_report(), runs / "one")
    out1, board1 = build_leaderboard([str(runs)], tmp_path / "out1")
    out2, _ = build_leaderboard([str(runs)], tmp_path / "out2")
    assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")
    # Round-trips.
    assert to_json(load_leaderboard(out1)) == to_json(board1)


def test_cli_leaderboard_build(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    assert runner.invoke(
        app, ["attack", "--episodes", "5", "--attacks", "instruction,visual", "--out", str(runs)]
    ).exit_code == 0
    result = runner.invoke(
        app, ["leaderboard", "build", "--runs", str(runs), "--out", str(tmp_path / "lb")]
    )
    assert result.exit_code == 0
    assert (tmp_path / "lb" / "leaderboard.json").exists()
    assert "ASR leaderboard" in result.output
    assert "demo data" in result.output  # stub-only -> demo banner


def test_cli_leaderboard_build_no_reports(tmp_path: Path) -> None:
    result = runner.invoke(app, ["leaderboard", "build", "--runs", str(tmp_path / "empty")])
    assert result.exit_code == 2
