"""Leaderboard aggregation: correctness, determinism, demo flag, real-run, provenance, CLI."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from typer.testing import CliRunner

from provael.attest import generate_private_key_pem, public_key_pem
from provael.cli import app
from provael.config import RunConfig
from provael.leaderboard import (
    REAL_TRANSFER,
    STUB_SCAFFOLDING,
    aggregate,
    attack_examples,
    build_leaderboard,
    find_reports,
    load_leaderboard,
    sign_leaderboard,
    stamp_provenance,
    to_json,
    verify_leaderboard,
)
from provael.report import write_report
from provael.runner import run
from provael.types import RunReport

runner = CliRunner()

_HAS_CRYPTO = importlib.util.find_spec("cryptography") is not None
_needs_crypto = pytest.mark.skipif(not _HAS_CRYPTO, reason="requires the `attest` extra")


def _real_report() -> RunReport:
    """A deterministic run (with the `none` baseline) relabelled as a real smolvla x libero run."""
    report = run(
        RunConfig(
            policy="stub", suite="stub",
            attacks=["none", "instruction", "visual", "injection"], episodes=10, seed=0,
        )
    )
    return report.model_copy(update={"policy": "smolvla", "suite": "libero"})


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


# --------------------------------------------------------------------------------------------
# real-run aggregation: is_demo flips, rows carry transfer-status + CI + benign control
# --------------------------------------------------------------------------------------------

def test_real_run_flips_is_demo_and_labels_rows() -> None:
    board = aggregate([_real_report()])
    assert board.is_demo is False
    for row in board.rows:
        assert row.transfer_status == REAL_TRANSFER
        assert row.ci95 is not None  # every real row carries its 95% Wilson CI
    # the benign control (baseline family rate) is attached to every row
    assert all(r.benign_fpr is not None for r in board.rows if r.attempts)


def test_stub_only_keeps_is_demo_and_stub_label() -> None:
    board = aggregate([_stub_report()])
    assert board.is_demo is True
    assert all(r.transfer_status == STUB_SCAFFOLDING for r in board.rows)


def test_never_silently_mixes_stub_and_real() -> None:
    board = aggregate([_stub_report(), _real_report()])
    assert board.is_demo is False
    labels = {(r.policy, r.transfer_status) for r in board.rows}
    assert ("stub", STUB_SCAFFOLDING) in labels
    assert ("smolvla", REAL_TRANSFER) in labels  # each row explicitly labelled, not blended


# --------------------------------------------------------------------------------------------
# provenance digest: deterministic and input-sensitive
# --------------------------------------------------------------------------------------------

def test_inputs_digest_is_stable_and_sensitive() -> None:
    a = aggregate([_real_report()]).inputs_digest
    b = aggregate([_real_report()]).inputs_digest
    assert a is not None and a == b  # same inputs -> same digest
    changed = _real_report().model_copy(update={"successes": 999})
    assert aggregate([changed]).inputs_digest != a


def test_build_leaderboard_stays_deterministic_with_digest(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    write_report(_stub_report(), runs / "one")
    out1, board1 = build_leaderboard([str(runs)], tmp_path / "o1")
    out2, _ = build_leaderboard([str(runs)], tmp_path / "o2")
    assert out1.read_text() == out2.read_text()  # digest deterministic, no date stamped
    assert board1.generated_at is None and board1.signature is None


def test_require_real_rejects_stub_only(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    write_report(_stub_report(), runs / "one")
    with pytest.raises(ValueError, match="no real"):
        build_leaderboard([str(runs)], tmp_path / "o", require_real=True)


# --------------------------------------------------------------------------------------------
# signing (gated on the crypto extra; present in the dev group -> runs in CI)
# --------------------------------------------------------------------------------------------

@_needs_crypto
def test_sign_and_verify_roundtrip() -> None:
    board = stamp_provenance(aggregate([_real_report()]), generated_at="2026-07-04T00:00:00Z",
                             commit="abc1234")
    priv = generate_private_key_pem()
    signed = sign_leaderboard(board, priv)
    assert signed.signature is not None and signed.signature.alg == "ed25519"
    assert verify_leaderboard(signed, public_key_pem(priv)) is True
    # a different key does not verify
    assert verify_leaderboard(signed, public_key_pem(generate_private_key_pem())) is False
    # tampering with a row breaks verification
    tampered = signed.model_copy(deep=True)
    tampered.rows[0].successes += 1
    assert verify_leaderboard(tampered, public_key_pem(priv)) is False


@_needs_crypto
def test_unsigned_board_does_not_verify() -> None:
    board = aggregate([_real_report()])
    assert board.signature is None
    assert verify_leaderboard(board, public_key_pem(generate_private_key_pem())) is False


# --------------------------------------------------------------------------------------------
# CLI --real path
# --------------------------------------------------------------------------------------------

def test_cli_leaderboard_build_real(tmp_path: Path) -> None:
    real = tmp_path / "real"
    write_report(_real_report(), real / "smolvla")
    result = runner.invoke(
        app, ["leaderboard", "build", "--real", str(real), "--out", str(tmp_path / "lb")]
    )
    assert result.exit_code == 0, result.output
    board = load_leaderboard(tmp_path / "lb" / "leaderboard.json")
    assert board.is_demo is False
    assert board.inputs_digest is not None
    assert board.generated_at is not None and board.commit is not None


def test_cli_leaderboard_build_real_rejects_stub(tmp_path: Path) -> None:
    stub = tmp_path / "stub"
    write_report(_stub_report(), stub / "one")
    result = runner.invoke(app, ["leaderboard", "build", "--real", str(stub)])
    assert result.exit_code == 2  # _fail on ValueError (no real runs)
