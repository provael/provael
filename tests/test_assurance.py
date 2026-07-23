"""Standards-aligned assurance profiles + the signed-attestation `--profile` path.

Guards: the three profiles reuse the shipped scoring/compliance/insurer surfaces (no statistic
reimplemented), the per-family transfer status is honest (real vs stub, never inflated), the
attestation stays byte-deterministic, and the committed SmolVLA×LIBERO sample matches a fresh build.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import provael.assurance as asr_mod
from provael.assurance import (
    ASSURANCE_FORMAT,
    CERT_READINESS,
    AssuranceProfile,
    build_assurance,
    family_transfer_table,
)
from provael.attest import load_bundle, to_bundle, to_bundle_json, verify_bundle
from provael.cli import app
from provael.config import RunConfig
from provael.report import load_report
from provael.runner import run

runner = CliRunner()

_ISSUED = "2026-07-22T00:00:00Z"
_COMMIT = "test"
_REAL = Path(__file__).resolve().parent.parent / "results" / "smolvla_libero_object"
_SAMPLE = _REAL / "attestation.insurer.json"


def _real_report():  # noqa: ANN202 - test helper
    return load_report(_REAL)


def _stub_report():  # noqa: ANN202
    return run(RunConfig(policy="stub", suite="stub", attacks=["none", "instruction", "visual"],
                         episodes=10, seed=0))


def _assurance(report, profile):  # noqa: ANN001, ANN202
    return build_assurance(report, profile, issued_at=_ISSUED, commit=_COMMIT)


# --------------------------------------------------------------------------- #
# the three profiles: structure + reuse of the shipped surfaces
# --------------------------------------------------------------------------- #


def test_iso_10218_2_routes_to_iec_62443_sl2_reusing_the_requirement() -> None:
    a = _assurance(_real_report(), AssuranceProfile.iso_10218_2)
    assert a["format"] == ASSURANCE_FORMAT and a["profile"] == "iso-10218-2"
    assert a["requirement"]["key"] == "iso-10218-2:cyber"  # reused compliance row, not rebuilt
    assert a["routes_to"]["framework"] == "IEC 62443" and a["routes_to"]["target_security_level"] == "SL2"
    assert a["risk_assessment_items"]  # the per-family evidence


def test_iec_62443_targets_sl2_with_foundational_requirements() -> None:
    a = _assurance(_real_report(), AssuranceProfile.iec_62443)
    assert a["profile"] == "iec-62443" and a["target_security_level"] == "SL2"
    assert a["requirement"]["key"] == "iec-62443:slv"
    frs = {fr["fr"] for fr in a["applicable_foundational_requirements"]}
    assert any("FR3" in fr for fr in frs) and any("FR7" in fr for fr in frs)


def test_insurer_reuses_the_shipped_insurer_report_and_transfer_table() -> None:
    a = _assurance(_real_report(), AssuranceProfile.insurer)
    assert a["profile"] == "insurer"
    # reused, not reimplemented; the shipped report is an honestly-named assurance-report DRAFT
    assert a["insurer_report"]["format"] == "provael-assurance-report-draft/v1"
    assert a["family_transfer_table"]


def test_all_profiles_carry_cert_readiness_caveat_and_disclaimer() -> None:
    for profile in AssuranceProfile:
        a = _assurance(_real_report(), profile)
        assert {r["framework"] for r in a["cert_readiness_crossref"]} == {
            r["framework"] for r in CERT_READINESS
        }
        assert any(r["framework"] == "NVIDIA Halos" for r in a["cert_readiness_crossref"])
        assert a["transfer_caveat"] and a["not_a_conformity_assessment"]


# --------------------------------------------------------------------------- #
# honesty: real vs stub transfer, no OWASP branding, no "first"
# --------------------------------------------------------------------------- #


def test_transfer_table_is_honest_real_vs_stub() -> None:
    # Real SmolVLA×LIBERO: instruction transfers, visual/injection ~0, all measured-real-transfer.
    real_rows = {r["family"]: r for r in family_transfer_table(_real_report())}
    assert real_rows["instruction"]["transfer_status"] == "measured-real-transfer"
    assert real_rows["instruction"]["asr"] > 0 and real_rows["visual"]["asr"] == 0.0
    for row in real_rows.values():
        assert row["transfer_status"] == "measured-real-transfer"
        assert row["wilson_ci95"] and row["n"] > 0  # the CI travels with every number
    # Stub: every family is stub-validated-scaffolding (never inflated to real).
    for row in family_transfer_table(_stub_report()):
        assert row["transfer_status"] == "stub-validated-scaffolding"


def test_authored_content_has_no_owasp_branding_or_first_claim() -> None:
    # The reused insurer_report legitimately cross-maps EAI -> OWASP as an external framework; the
    # assurance module's OWN authored text must not brand the Top 10 as OWASP or claim "first".
    authored = json.dumps([list(CERT_READINESS)] + [
        {k: v for k, v in _assurance(_real_report(), p).items() if k != "insurer_report"}
        for p in AssuranceProfile
    ])
    assert "OWASP" not in authored
    assert "first" not in authored.lower()


def test_reuses_scoring_without_reimplementing_it(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"by_family": 0, "wilson": 0, "mbf": 0}
    reals = {"by_family": asr_mod.by_family, "wilson": asr_mod.wilson_ci,
             "mbf": asr_mod.matched_benign_fpr}

    def wrap(key):  # noqa: ANN001, ANN202
        def inner(*a: object, **k: object) -> object:
            calls[key] += 1
            return reals[key](*a, **k)  # type: ignore[operator]
        return inner

    monkeypatch.setattr(asr_mod, "by_family", wrap("by_family"))
    monkeypatch.setattr(asr_mod, "wilson_ci", wrap("wilson"))
    monkeypatch.setattr(asr_mod, "matched_benign_fpr", wrap("mbf"))
    family_transfer_table(_real_report())
    assert all(v > 0 for v in calls.values()), calls


# --------------------------------------------------------------------------- #
# determinism + the signed attestation path
# --------------------------------------------------------------------------- #


def test_assurance_is_byte_deterministic() -> None:
    for profile in AssuranceProfile:
        a = json.dumps(_assurance(_real_report(), profile), sort_keys=True)
        b = json.dumps(_assurance(_real_report(), profile), sort_keys=True)
        assert a == b


def test_attestation_with_profile_is_byte_identical_across_two_runs() -> None:
    report = _real_report()

    def _bundle():  # noqa: ANN202
        assurance = _assurance(report, AssuranceProfile.insurer)
        bundle, _ = to_bundle(report, issued_at=_ISSUED, commit=_COMMIT, sign=False,
                              assurance=assurance)
        return to_bundle_json(bundle)

    assert _bundle() == _bundle()  # digest-only + fixed metadata -> reproducible


def test_committed_sample_matches_a_fresh_build_and_verifies() -> None:
    report = _real_report()
    assurance = build_assurance(report, AssuranceProfile.insurer,
                                issued_at=_ISSUED, commit="smolvla-libero-2026-06-06")
    fresh, _ = to_bundle(report, issued_at=_ISSUED, commit="smolvla-libero-2026-06-06",
                         sign=False, assurance=assurance)
    assert to_bundle_json(fresh) + "\n" == _SAMPLE.read_text(encoding="utf-8")  # drift guard
    # digest-only sample: the honest offline check is the integrity layer (not a trusted signature).
    assert verify_bundle(load_bundle(_SAMPLE)).integrity_only_ok


def test_cli_attest_profile_embeds_assurance(tmp_path: Path) -> None:
    out = tmp_path / "att"
    result = runner.invoke(app, ["attest", "--run", str(_REAL), "--profile", "iso-10218-2",
                                 "--no-sign", "--out", str(out)])
    assert result.exit_code == 0
    import base64
    bundle = json.loads((out / "attestation.json").read_text())
    stmt = json.loads(base64.b64decode(bundle["payload"]))
    assert stmt["assurance"]["profile"] == "iso-10218-2"
    assert stmt["ruleset"] == "provael-attest-ruleset/4"
