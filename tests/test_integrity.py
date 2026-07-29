"""Checkpoint supply-chain integrity: the fail-closed matrix and the honesty boundary.

The whole value of this control is that "we did not check" and "we checked and it matched" produce
DIFFERENT verdicts. Most of this file is the fail-closed matrix proving that.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from provael.cli import app
from provael.integrity import (
    INTEGRITY_JSON,
    CheckpointFormat,
    IntegrityVerdict,
    detect_format,
    digest_checkpoint,
    skipped_record,
    verify_checkpoint,
)
from provael.sarif import to_sarif

runner = CliRunner()


@pytest.fixture
def safe_ckpt(tmp_path: Path) -> Path:
    d = tmp_path / "safe"
    d.mkdir()
    (d / "model.safetensors").write_bytes(b"weights")
    return d


@pytest.fixture
def pickle_ckpt(tmp_path: Path) -> Path:
    d = tmp_path / "pickled"
    d.mkdir()
    (d / "pytorch_model.bin").write_bytes(b"weights")
    return d


# --------------------------------------------------------------------------- #
# format detection
# --------------------------------------------------------------------------- #


def test_format_detection(safe_ckpt: Path, pickle_ckpt: Path, tmp_path: Path) -> None:
    assert detect_format(safe_ckpt) is CheckpointFormat.safetensors
    assert detect_format(pickle_ckpt) is CheckpointFormat.pickle
    (safe_ckpt / "extra.bin").write_bytes(b"also")
    assert detect_format(safe_ckpt) is CheckpointFormat.mixed
    empty = tmp_path / "empty"
    empty.mkdir()
    assert detect_format(empty) is CheckpointFormat.unknown


def test_digest_is_layout_independent(tmp_path: Path) -> None:
    """The pin must survive a directory reshuffle, or nobody can re-check it elsewhere."""
    a, b = tmp_path / "a", tmp_path / "b" / "nested"
    a.mkdir()
    b.mkdir(parents=True)
    (a / "model.safetensors").write_bytes(b"weights")
    (b / "model.safetensors").write_bytes(b"weights")
    assert digest_checkpoint(a) == digest_checkpoint(b.parent)


def test_digest_changes_when_a_byte_changes(safe_ckpt: Path) -> None:
    before = digest_checkpoint(safe_ckpt)
    (safe_ckpt / "model.safetensors").write_bytes(b"tampered")
    assert digest_checkpoint(safe_ckpt) != before


# --------------------------------------------------------------------------- #
# the fail-closed matrix
# --------------------------------------------------------------------------- #


def test_matching_pin_passes(safe_ckpt: Path) -> None:
    digest = digest_checkpoint(safe_ckpt)
    assert digest is not None
    assert verify_checkpoint("m", safe_ckpt, expected_digest=digest).verdict is IntegrityVerdict.passed


def test_mismatched_pin_fails(safe_ckpt: Path) -> None:
    record = verify_checkpoint("m", safe_ckpt, expected_digest="00" * 32)
    assert record.verdict is IntegrityVerdict.failed
    assert record.digest_match is False
    assert any("MISMATCH" in f for f in record.findings)


def test_no_pin_fails_closed(safe_ckpt: Path) -> None:
    """THE default. "We did not check" must not look like "we checked and it matched"."""
    record = verify_checkpoint("m", safe_ckpt)
    assert record.verdict is IntegrityVerdict.failed
    assert record.digest_match is None
    assert any("no checkpoint digest was pinned" in f for f in record.findings)


def test_no_pin_passes_only_under_an_explicit_opt_out(safe_ckpt: Path) -> None:
    record = verify_checkpoint("m", safe_ckpt, require_pinned_digest=False)
    assert record.verdict is IntegrityVerdict.passed


def test_pickle_refused_without_opt_in(pickle_ckpt: Path) -> None:
    """Loading a pickle executes it, so the default must be refusal, not a warning."""
    digest = digest_checkpoint(pickle_ckpt)
    record = verify_checkpoint("m", pickle_ckpt, expected_digest=digest)
    assert record.verdict is IntegrityVerdict.failed
    assert any("CVE-2026-25874" in f for f in record.findings)


def test_pickle_allowed_under_an_explicit_opt_in(pickle_ckpt: Path) -> None:
    digest = digest_checkpoint(pickle_ckpt)
    record = verify_checkpoint("m", pickle_ckpt, expected_digest=digest, allow_pickle=True)
    assert record.verdict is IntegrityVerdict.passed
    # Accepted, not made safe — the finding must still say what was accepted.
    assert any("code execution from" in f for f in record.findings)


def test_mixed_format_passes_and_says_which_to_load(safe_ckpt: Path) -> None:
    (safe_ckpt / "legacy.bin").write_bytes(b"old")
    record = verify_checkpoint("m", safe_ckpt, expected_digest=digest_checkpoint(safe_ckpt))
    assert record.verdict is IntegrityVerdict.passed
    assert any("do not\nfall back" in f or "do not" in f for f in record.findings)


def test_unfetched_checkpoint_fails(safe_ckpt: Path) -> None:
    """Nothing on disk means nothing was verified — that is a failure, not a pass."""
    assert verify_checkpoint("hub/id", None, expected_digest="ab" * 32).verdict is IntegrityVerdict.failed


def test_skipped_record_is_visible_never_silent() -> None:
    record = skipped_record("m", "no checkpoint in this job")
    assert record.verdict is IntegrityVerdict.skipped
    assert record.findings and "explicit opt-out" in record.findings[0]


# --------------------------------------------------------------------------- #
# the honesty boundary
# --------------------------------------------------------------------------- #


def test_this_control_is_never_an_asr(safe_ckpt: Path) -> None:
    """A supply-chain verdict must not be reportable as, or aggregated into, an attack rate.

    A checkpoint that passes every check here can still be driven off-task at exactly the rate the
    ASR reports. The record therefore carries no rate field at all, and says so in `note`.
    """
    record = verify_checkpoint("m", safe_ckpt, expected_digest=digest_checkpoint(safe_ckpt))
    payload = json.loads(record.model_dump_json())
    for forbidden in ("asr", "attack_success_rate", "successes", "attempts", "rate", "ci95"):
        assert forbidden not in payload, f"integrity evidence must carry no {forbidden!r}"
    assert "not an attack-success rate" in record.note
    assert record.eai_id == "EAI03"  # supply chain, per the EAI title — not EAI07


def test_sarif_nests_integrity_away_from_the_rates(safe_ckpt: Path) -> None:
    """In SARIF the verdict sits under its own key, never beside adversarialAsr."""
    from provael.config import RunConfig
    from provael.runner import run

    report = run(RunConfig(attacks=["none", "instruction"], episodes=2, seed=0))
    record = verify_checkpoint("m", safe_ckpt, expected_digest=digest_checkpoint(safe_ckpt))
    props = to_sarif(report, record)["runs"][0]["properties"]
    assert "checkpointIntegrity" in props
    assert props["checkpointIntegrity"]["verdict"] == "pass"
    assert props["checkpointIntegrity"]["eaiId"] == "EAI03"
    # The verdict must not have leaked into the rate keys.
    assert "verdict" not in {k for k in props if k != "checkpointIntegrity"}
    assert to_sarif(report).get("runs")[0]["properties"].get("checkpointIntegrity") is None


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def test_cli_fails_closed_on_a_mismatched_digest(safe_ckpt: Path, tmp_path: Path) -> None:
    out = tmp_path / "run"
    result = runner.invoke(app, [
        "verify-checkpoint", "--checkpoint", "demo", "--path", str(safe_ckpt),
        "--digest", "00" * 32, "--out", str(out),
    ])
    assert result.exit_code != 0, "a mismatched digest must fail the job"
    payload = json.loads((out / INTEGRITY_JSON).read_text())
    assert payload["verdict"] == "fail"


def test_cli_passes_and_writes_evidence_on_a_matching_digest(safe_ckpt: Path, tmp_path: Path) -> None:
    out = tmp_path / "run"
    digest = digest_checkpoint(safe_ckpt)
    assert digest is not None
    result = runner.invoke(app, [
        "verify-checkpoint", "--checkpoint", "demo", "--path", str(safe_ckpt),
        "--digest", digest, "--out", str(out),
    ])
    assert result.exit_code == 0, result.output
    payload = json.loads((out / INTEGRITY_JSON).read_text())
    assert payload["verdict"] == "pass"
    assert payload["checkpoint_format"] == "safetensors"
    assert payload["digest_sha256"] == digest
