"""The ``attest`` command: the signed, dated, crosswalked evidence bundle.

Covers the pure statement builder (wraps the SAME compliance evidence, deterministic, digest binds
the run), the digest-only path (verifiable with zero crypto), the transfer-status honesty flags,
and a **gated** real Ed25519 sign/verify roundtrip (runs when ``cryptography`` is importable — it is
in the dev group, so CI exercises it; it skips cleanly without the extra). Plus a CLI stub e2e.
"""

from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from provael.attest import (
    REGULATORY_CLOCK,
    AttestationBundle,
    build_statement,
    generate_private_key_pem,
    public_key_pem,
    to_bundle,
    verify_bundle,
)
from provael.cli import app
from provael.compliance import to_compliance_dict
from provael.config import RunConfig
from provael.runner import run
from provael.types import RunReport

runner = CliRunner()

_HAS_CRYPTO = importlib.util.find_spec("cryptography") is not None
_needs_crypto = pytest.mark.skipif(not _HAS_CRYPTO, reason="requires the `attest` extra (cryptography)")

_ISSUED = "2026-07-03T00:00:00Z"
_COMMIT = "abc1234"


def _report(attacks: list[str] | None = None, episodes: int = 5) -> RunReport:
    """A real stub run with a benign control (fast, deterministic, CPU)."""
    return run(
        RunConfig(
            policy="stub", suite="stub",
            attacks=attacks or ["none", "instruction"],
            episodes=episodes, seed=0, out=Path("runs/_attest_test"),
        )
    )


# --------------------------------------------------------------------------------------------
# statement builder — wraps the SAME evidence, deterministic, binds the run
# --------------------------------------------------------------------------------------------

def test_statement_wraps_the_same_compliance_evidence() -> None:
    report = _report()
    statement = build_statement(report, issued_at=_ISSUED, commit=_COMMIT)
    # attest does not invent a new report — its predicate IS the compliance export.
    assert statement.predicate == to_compliance_dict(report)
    assert statement.tool_version == report.tool_version


def test_statement_is_deterministic() -> None:
    report = _report()
    a = build_statement(report, issued_at=_ISSUED, commit=_COMMIT).model_dump_json()
    b = build_statement(report, issued_at=_ISSUED, commit=_COMMIT).model_dump_json()
    assert a == b


def test_subject_digest_binds_the_run() -> None:
    report = _report()
    base_digest = build_statement(report, issued_at=_ISSUED, commit=_COMMIT).subject.digest["sha256"]
    tampered = report.model_copy(update={"successes": report.successes + 1})
    other = build_statement(tampered, issued_at=_ISSUED, commit=_COMMIT).subject.digest["sha256"]
    assert base_digest != other  # any change to the run changes the bound digest


def test_regulatory_clock_states_machinery_2027_and_both_ai_act_dates() -> None:
    by_id = {c.framework_id: c for c in REGULATORY_CLOCK}
    assert by_id["eu-machinery"].applies_from == "2027-01-20"
    # AI Act line names the statutory date and flags the proposed 2028 as not-yet-adopted.
    ai_act = by_id["eu-ai-act"]
    assert ai_act.applies_from == "2027-08-02"
    assert "2028" in ai_act.note and "not yet adopted" in ai_act.note.lower()
    # CRA (Reg. (EU) 2024/2847): main obligations 2027-12-11; the note states the 2026 reporting date.
    cra = by_id["eu-cra"]
    assert cra.applies_from == "2027-12-11"
    assert "2026-09-11" in cra.note


def test_transfer_status_flags_stub_and_optimized() -> None:
    report = _report(attacks=["none", "instruction", "optimized"])
    statement = build_statement(report, issued_at=_ISSUED, commit=_COMMIT)
    by_attack = {t.attack: t for t in statement.transfer}
    assert "none" not in by_attack  # the control is not a transfer claim
    assert by_attack["roleplay"].status == "stub-validated-scaffolding"  # stub run, not real transfer
    assert by_attack["targeted_hijack"].status == "stub-validated-scaffolding"
    assert "GPU-gated" in by_attack["targeted_hijack"].note


# --------------------------------------------------------------------------------------------
# digest-only path — verifiable with zero crypto
# --------------------------------------------------------------------------------------------

def test_digest_only_bundle_verifies_and_detects_tampering() -> None:
    report = _report()
    bundle, pub = to_bundle(report, issued_at=_ISSUED, commit=_COMMIT, sign=False)
    assert pub is None
    assert bundle.signed is False and bundle.signatures == []

    result = verify_bundle(bundle)
    assert result.digest_ok is True
    assert result.signature_ok is None  # nothing signed, nothing to check
    assert result.ok is True

    # flip a byte of the payload -> the recomputed digest no longer matches
    raw = base64.b64decode(bundle.payload)
    tampered = base64.b64encode(raw.replace(b"stub", b"XXXX", 1)).decode("ascii")
    bad = bundle.model_copy(update={"payload": tampered})
    assert verify_bundle(bad).digest_ok is False
    assert verify_bundle(bad).ok is False


# --------------------------------------------------------------------------------------------
# signed path — gated on the crypto extra (present in the dev group -> runs in CI)
# --------------------------------------------------------------------------------------------

@_needs_crypto
def test_sign_and_verify_roundtrip() -> None:
    report = _report()
    priv = generate_private_key_pem()
    pub = public_key_pem(priv)
    bundle, returned_pub = to_bundle(
        report, issued_at=_ISSUED, commit=_COMMIT, private_key_pem=priv
    )
    assert returned_pub == pub
    assert bundle.signed is True and bundle.signatures[0].alg == "ed25519"

    good = verify_bundle(bundle, public_key_pem_bytes=pub)
    assert good.digest_ok is True and good.signature_ok is True and good.ok is True

    # a different key must not verify
    other_pub = public_key_pem(generate_private_key_pem())
    bad = verify_bundle(bundle, public_key_pem_bytes=other_pub)
    assert bad.signature_ok is False and bad.ok is False


@_needs_crypto
def test_ed25519_signature_is_deterministic() -> None:
    report = _report()
    priv = generate_private_key_pem()
    a, _ = to_bundle(report, issued_at=_ISSUED, commit=_COMMIT, private_key_pem=priv)
    b, _ = to_bundle(report, issued_at=_ISSUED, commit=_COMMIT, private_key_pem=priv)
    assert a.signatures[0].sig == b.signatures[0].sig  # Ed25519 is deterministic


@_needs_crypto
def test_signed_payload_tamper_breaks_digest() -> None:
    report = _report()
    priv = generate_private_key_pem()
    pub = public_key_pem(priv)
    bundle, _ = to_bundle(report, issued_at=_ISSUED, commit=_COMMIT, private_key_pem=priv)
    raw = base64.b64decode(bundle.payload)
    tampered = base64.b64encode(raw.replace(b"evidence", b"XXXXXXXX", 1)).decode("ascii")
    bad = bundle.model_copy(update={"payload": tampered})
    assert verify_bundle(bad, public_key_pem_bytes=pub).digest_ok is False


# --------------------------------------------------------------------------------------------
# CLI end-to-end (stub, CPU)
# --------------------------------------------------------------------------------------------

def test_cli_attest_help() -> None:
    result = runner.invoke(app, ["attest", "--help"])
    assert result.exit_code == 0
    assert "evidence bundle" in result.output.lower()


def test_cli_attest_stub_e2e_then_verify(tmp_path: Path) -> None:
    out = tmp_path / "attest"
    issue = runner.invoke(
        app,
        ["attest", "--policy", "stub", "--suite", "stub", "--attacks", "none,instruction",
         "--episodes", "5", "--out", str(out)],
    )
    assert issue.exit_code == 0, issue.output
    bundle_path = out / "attestation.json"
    assert bundle_path.exists()
    assert (out / "report.compliance.md").exists()

    bundle = AttestationBundle.model_validate_json(bundle_path.read_text())
    if _HAS_CRYPTO:
        assert bundle.signed is True
        assert (out / "attestation.pub").exists()

    args = ["attest", "--verify", str(bundle_path)]
    if (out / "attestation.pub").exists():
        args += ["--pubkey", str(out / "attestation.pub")]
    verify = runner.invoke(app, args)
    assert verify.exit_code == 0, verify.output
    assert "OK" in verify.output


def test_cli_attest_no_sign_is_digest_only(tmp_path: Path) -> None:
    out = tmp_path / "attest"
    result = runner.invoke(
        app, ["attest", "--no-sign", "--episodes", "3", "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    bundle = json.loads((out / "attestation.json").read_text())
    assert bundle["signed"] is False
