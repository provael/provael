# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The per-checkpoint baseline-regression gate: the CI-aware diff and its CLI wiring.

Every case uses hand-built deterministic reports (no policy/sim/GPU), so it runs in CPU CI. The
regression rule is: candidate ASR beats baseline by more than the tolerance AND the 95% Wilson CIs
are disjoint. We cover the three verdicts (clear regression, within-tolerance / CI-overlap noise,
improvement) plus the non-zero CLI exit and the regression SARIF.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from provael.cli import app
from provael.regression import (
    RegressionAttestation,
    RegressionSignature,
    build_regression_attestation,
    diff_reports,
    to_diff_dict,
    to_diff_json,
    to_markdown,
    to_regression_sarif,
    verify_regression_attestation,
)
from provael.report import write_report
from provael.types import ASRStat, EaiTag, RunReport

runner = CliRunner()

_HAS_CRYPTO = importlib.util.find_spec("cryptography") is not None
_needs_crypto = pytest.mark.skipif(
    not _HAS_CRYPTO, reason="requires the `attest` extra (cryptography)"
)
_ISSUED = "2026-07-24T00:00:00Z"


def _report(successes: int, attempts: int, *, attack: str = "roleplay", eai: str = "EAI01") -> RunReport:
    """A minimal deterministic report whose single attack == the overall stat.

    The adversarial_* fields are populated to equal the overall stat because this fixture models a
    run whose only applicable episodes ARE the adversarial ones. The gate compares the adversarial
    subset (see :func:`provael.regression._adversarial_stat`), so leaving them unset would make the
    fixture describe a run with no adversarial evidence at all.
    """
    asr = successes / attempts if attempts else 0.0
    return RunReport(
        tool_version="9.9.9", policy="stub", suite="stub",
        attacks=["none", attack], tasks=["reach"], episodes=attempts, horizon=8, seed=0,
        attempts=attempts, successes=successes, asr=asr,
        adversarial_attempts=attempts, adversarial_successes=successes, adversarial_asr=asr,
        by_attack={attack: ASRStat(attempts=attempts, successes=successes, asr=asr)},
        eai={attack: EaiTag(id=eai, name="Policy & instruction jailbreak")},
    )


# --------------------------------------------------------------------------------------------
# the three verdicts
# --------------------------------------------------------------------------------------------

def test_clear_regression_trips_the_gate() -> None:
    # 6.7% [1.8-21%] -> 90% [74-97%]: big delta AND disjoint CIs.
    baseline = _report(2, 30)
    candidate = _report(27, 30)
    diff = diff_reports(candidate, baseline, tolerance=0.05)
    assert diff.regressed is True
    assert diff.overall.delta is not None and diff.overall.delta > 0.8
    assert "EAI01" in diff.regressed_keys  # the per-EAI slice regressed too
    assert diff.by_eai[0].regressed is True


def test_within_tolerance_is_not_a_regression() -> None:
    # 50% -> 53.3%: delta 3.3pp <= 5pp tolerance -> never even checks CIs.
    diff = diff_reports(_report(16, 30), _report(15, 30), tolerance=0.05)
    assert diff.regressed is False
    assert "within tolerance" in diff.overall.reason


def test_overlapping_cis_are_not_a_regression() -> None:
    # 50% [24-76%] -> 70% [40-89%] at n=10: delta 20pp > tol, but CIs overlap -> small-n noise.
    diff = diff_reports(_report(7, 10), _report(5, 10), tolerance=0.05)
    assert diff.regressed is False
    assert "overlap" in diff.overall.reason


def test_improvement_is_not_a_regression() -> None:
    diff = diff_reports(_report(2, 30), _report(27, 30), tolerance=0.05)  # candidate improved
    assert diff.regressed is False
    assert diff.overall.delta is not None and diff.overall.delta < 0


def test_diff_is_deterministic() -> None:
    a = diff_reports(_report(27, 30), _report(2, 30)).model_dump_json()
    b = diff_reports(_report(27, 30), _report(2, 30)).model_dump_json()
    assert a == b


# --------------------------------------------------------------------------------------------
# regression SARIF
# --------------------------------------------------------------------------------------------

def test_regression_sarif_flags_only_regressed_families() -> None:
    candidate, baseline = _report(27, 30), _report(2, 30)
    diff = diff_reports(candidate, baseline, tolerance=0.05)
    sarif = to_regression_sarif(diff, candidate)
    results = sarif["runs"][0]["results"]
    assert len(results) == 1
    assert results[0]["ruleId"] == "EAI01"
    assert results[0]["level"] == "error"
    assert sarif["runs"][0]["properties"]["regressed"] is True

    # No regression -> valid SARIF with an empty results array (clears prior alerts).
    clean = to_regression_sarif(diff_reports(_report(2, 30), _report(2, 30)), _report(2, 30))
    assert clean["runs"][0]["results"] == []


# --------------------------------------------------------------------------------------------
# CLI wiring: report --baseline exits non-zero on a regression
# --------------------------------------------------------------------------------------------

def _write(report: RunReport, path: Path) -> Path:
    write_report(report, path)
    return path / "report.json"


def test_cli_report_baseline_exit_codes(tmp_path: Path) -> None:
    base_json = _write(_report(2, 30), tmp_path / "baseline")
    cand_dir = tmp_path / "candidate"
    _write(_report(27, 30), cand_dir)

    # regression -> exit 1
    bad = runner.invoke(
        app, ["report", "--in", str(cand_dir), "--baseline", str(base_json),
               "--regression-tolerance", "0.05", "--out", str(tmp_path / "diff.json"),
               "--sarif-out", str(tmp_path / "reg.sarif")],
    )
    assert bad.exit_code == 1, bad.output
    assert "regression" in bad.output.lower()
    written = json.loads((tmp_path / "diff.json").read_text())
    assert written["regressed"] is True

    # candidate == baseline -> no regression -> exit 0
    ok = runner.invoke(
        app, ["report", "--in", str(tmp_path / "baseline"), "--baseline", str(base_json)],
    )
    assert ok.exit_code == 0, ok.output
    assert "no regression" in ok.output.lower()


# --------------------------------------------------------------------------------------------
# critical slices: a flat aggregate cannot hide a regressed critical attack
# --------------------------------------------------------------------------------------------


def _two_arm(roleplay: tuple[int, int], patch: tuple[int, int]) -> RunReport:
    """A report with two adversarial arms whose pool is what the overall slice sees."""
    (rs, rn), (ps, pn) = roleplay, patch
    total_s, total_n = rs + ps, rn + pn
    return RunReport(
        tool_version="9.9.9", policy="stub", suite="stub",
        attacks=["none", "roleplay", "patch"], tasks=["reach"], episodes=rn, horizon=8, seed=0,
        attempts=total_n, successes=total_s, asr=total_s / total_n,
        adversarial_attempts=total_n, adversarial_successes=total_s, adversarial_asr=total_s / total_n,
        by_attack={
            "roleplay": ASRStat(attempts=rn, successes=rs, asr=rs / rn),
            "patch": ASRStat(attempts=pn, successes=ps, asr=ps / pn),
        },
        eai={
            "roleplay": EaiTag(id="EAI01", name="Policy & instruction jailbreak"),
            "patch": EaiTag(id="EAI02", name="Adversarial perception"),
        },
    )


def test_a_critical_attack_regression_trips_the_gate_with_a_flat_aggregate() -> None:
    """roleplay 2/30 -> 27/30 while patch 27/30 -> 2/30: the pool is 29/60 on both sides."""
    baseline = _two_arm((2, 30), (27, 30))
    candidate = _two_arm((27, 30), (2, 30))
    plain = diff_reports(candidate, baseline, tolerance=0.05)
    assert plain.overall.regressed is False and plain.regressed is False
    assert "roleplay" in plain.regressed_keys  # computed all along, gating nothing
    gated = diff_reports(candidate, baseline, tolerance=0.05, critical_attacks=["roleplay"])
    assert gated.regressed is True
    assert gated.critical_regressed == ["roleplay"]
    assert gated.overall.regressed is False  # the aggregate is still flat; the gate no longer is
    assert "Critical regression: roleplay" in to_markdown(gated)


def test_a_critical_attack_missing_on_one_side_is_reported_not_passed() -> None:
    baseline = _two_arm((2, 30), (2, 30))
    candidate = _report(2, 30)  # only roleplay ran
    diff = diff_reports(candidate, baseline, critical_attacks=["patch", "roleplay"])
    assert diff.regressed is False
    assert diff.critical_unmeasured == ["patch"]
    assert "not shown to be safe" in to_markdown(diff)


def test_critical_attacks_are_part_of_the_deterministic_diff() -> None:
    baseline, candidate = _two_arm((2, 30), (2, 30)), _two_arm((27, 30), (2, 30))
    a = to_diff_json(diff_reports(candidate, baseline, critical_attacks=["roleplay"]))
    b = to_diff_json(diff_reports(candidate, baseline, critical_attacks=["roleplay"]))
    assert a == b and '"critical_attacks": [\n    "roleplay"' in a


def test_cli_report_baseline_gates_the_protocols_critical_attacks(tmp_path: Path) -> None:
    base_json = _write(_two_arm((2, 30), (27, 30)), tmp_path / "baseline")
    cand_dir = tmp_path / "candidate"
    _write(_two_arm((27, 30), (2, 30)), cand_dir)
    protocol = tmp_path / "protocol.yml"
    protocol.write_text(
        "name: pilot\nrequirements:\n  critical_attacks:\n    roleplay: {max_asr: 0.2}\n",
        encoding="utf-8",
    )
    flat = runner.invoke(app, ["report", "--in", str(cand_dir), "--baseline", str(base_json)])
    assert flat.exit_code == 0, flat.output  # the aggregate did not move
    gated = runner.invoke(
        app, ["report", "--in", str(cand_dir), "--baseline", str(base_json),
               "--protocol", str(protocol), "--out", str(tmp_path / "diff.json")],
    )
    assert gated.exit_code == 1, gated.output
    assert "Critical regression: roleplay" in gated.output
    assert json.loads((tmp_path / "diff.json").read_text())["critical_regressed"] == ["roleplay"]


# --------------------------------------------------------------------------------------------
# like-for-like, or say why not (R09)
# --------------------------------------------------------------------------------------------


def _calibrated(report: RunReport, **meta: object) -> RunReport:
    from provael.types import CalibrationMeta

    base = {"predicate": "calibrated", "kind": "scalar", "target_fpr": 0.05, "holdout_fpr": 0.0,
            "n_benign": 20}
    base.update(meta)
    return report.model_copy(
        update={"calibrated": True, "calibration": {"reach": CalibrationMeta(**base)}}  # type: ignore[arg-type]
    )


def test_a_changed_calibration_is_incomparable_even_with_the_same_flag() -> None:
    """The calibrated boolean matched on both sides; the predicate behind it did not."""
    baseline = _calibrated(_report(2, 30), target_fpr=0.05)
    candidate = _calibrated(_report(27, 30), target_fpr=0.10)
    diff = diff_reports(candidate, baseline)
    assert any("predicate identity differs" in reason for reason in diff.incomparable)
    assert "NOT LIKE-FOR-LIKE" in to_markdown(diff)
    same = diff_reports(_calibrated(_report(27, 30)), _calibrated(_report(2, 30)))
    assert not any("predicate identity" in r for r in same.incomparable)


def test_a_checkpoint_only_change_compares_and_is_on_the_record() -> None:
    from provael.types import ActionUnnormaliser, ControllerConvention, DeployedPolicy

    unnorm = ActionUnnormaliser(mode="MEAN_STD", source="lerobot-postprocessor", stats_digest="abc")
    convention = ControllerConvention(action_dim=7, pipeline=["clip"])

    def deployed(checkpoint: str, revision: str) -> DeployedPolicy:
        return DeployedPolicy.build(
            adapter="smolvla", policy_class="SmolVLAPolicy", checkpoint=checkpoint,
            checkpoint_revision=revision, action_unnormaliser=unnorm,
            controller_convention=convention,
        )

    baseline = _report(2, 30).model_copy(
        update={"model": "org/ckpt-v1", "deployed_policy": deployed("org/ckpt-v1", "aaa")}
    )
    candidate = _report(27, 30).model_copy(
        update={"model": "org/ckpt-v2", "deployed_policy": deployed("org/ckpt-v2", "bbb")}
    )
    diff = diff_reports(candidate, baseline)
    assert diff.incomparable == []  # same suite, horizon, tasks, predicate, action pipeline
    assert any(c.startswith("checkpoint:") for c in diff.changed)
    assert any(c.startswith("resolved checkpoint:") for c in diff.changed)
    assert diff.regressed is True  # 2/30 -> 27/30 is a regression under the same protocol
    md = to_markdown(diff)
    assert "What changed between the runs" in md and "Next investigation" in md


def test_a_different_action_pipeline_is_incomparable() -> None:
    from provael.types import ActionUnnormaliser, DeployedPolicy

    def deployed(mode: str) -> DeployedPolicy:
        return DeployedPolicy.build(
            adapter="smolvla", checkpoint="org/ckpt",
            action_unnormaliser=ActionUnnormaliser(mode=mode, source="lerobot-postprocessor"),
        )

    baseline = _report(2, 30).model_copy(update={"deployed_policy": deployed("MEAN_STD")})
    candidate = _report(27, 30).model_copy(update={"deployed_policy": deployed("MIN_MAX")})
    diff = diff_reports(candidate, baseline)
    assert any("action unnormaliser differs" in r for r in diff.incomparable)


# --------------------------------------------------------------------------------------------
# the signed regression attestation
# --------------------------------------------------------------------------------------------

def _diff_and_candidate(cand_successes: int, base_successes: int, n: int = 30):  # noqa: ANN202
    candidate = _report(cand_successes, n)
    diff = diff_reports(candidate, _report(base_successes, n), tolerance=0.05)
    return diff, candidate


def test_digest_only_attestation_is_never_strict_ok() -> None:
    diff, cand = _diff_and_candidate(27, 2)
    att = build_regression_attestation(diff, cand, issued_at=_ISSUED, commit="abc", sign=False)
    assert att.signed is False and att.signatures == [] and att.public_key is None
    r = verify_regression_attestation(att)
    assert r.digest_ok is True
    assert r.signature_present is False
    assert r.signature_valid is None
    assert r.strict_ok is False  # a digest-only bundle is intact but never strict-OK (fail closed)


def test_attestation_binds_the_diff_sarif_and_summary_and_reports_ci() -> None:
    diff, cand = _diff_and_candidate(27, 2)
    att = build_regression_attestation(diff, cand, issued_at=_ISSUED, commit="abc", sign=False)
    st = json.loads(base64.b64decode(att.payload))
    # Honesty: the signed headline is the ASR *with its 95% CI*, plus the verdict — never a bare rate.
    assert st["regressed"] is True
    assert st["candidate_asr"] is not None and st["candidate_ci"] is not None
    # The subject digests bind the actual evidence files.
    diff_digest = hashlib.sha256(
        json.dumps(to_diff_dict(diff), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert st["subject"]["diff_sha256"] == diff_digest
    assert st["subject"]["summary_sha256"] == hashlib.sha256(to_markdown(diff).encode()).hexdigest()


def test_tampered_payload_fails_the_digest() -> None:
    diff, cand = _diff_and_candidate(27, 2)
    att = build_regression_attestation(diff, cand, issued_at=_ISSUED, commit="abc", sign=False)
    tampered = att.model_copy(update={"payloadSha256": "0" * 64})
    r = verify_regression_attestation(tampered)
    assert r.digest_ok is False
    assert r.strict_ok is False


@_needs_crypto
def test_signed_attestation_verifies_and_is_deterministic() -> None:
    from provael.attest import generate_private_key_pem

    diff, cand = _diff_and_candidate(27, 2)
    key = generate_private_key_pem()
    a1 = build_regression_attestation(
        diff, cand, issued_at=_ISSUED, commit="abc", private_key_pem=key
    )
    a2 = build_regression_attestation(
        diff, cand, issued_at=_ISSUED, commit="abc", private_key_pem=key
    )
    assert a1.model_dump_json() == a2.model_dump_json()  # Ed25519 is deterministic + fixed key
    r = verify_regression_attestation(a1)
    assert r.signature_present is True
    assert r.signature_valid is True
    assert r.strict_ok is True


@_needs_crypto
def test_tampered_signature_fails_strict() -> None:
    from provael.attest import generate_private_key_pem

    diff, cand = _diff_and_candidate(27, 2)
    att = build_regression_attestation(
        diff, cand, issued_at=_ISSUED, commit="abc", private_key_pem=generate_private_key_pem()
    )
    s = att.signatures[0].sig
    flipped = s[:10] + ("A" if s[10] != "A" else "B") + s[11:]  # keep length (64 bytes), wrong sig
    bad = att.model_copy(update={"signatures": [RegressionSignature(keyid=att.signatures[0].keyid, sig=flipped)]})
    r = verify_regression_attestation(bad)
    assert r.digest_ok is True
    assert r.signature_valid is False
    assert r.strict_ok is False


@_needs_crypto
def test_cli_report_attest_out_writes_a_verifiable_bundle(tmp_path: Path) -> None:
    base_json = _write(_report(2, 30), tmp_path / "baseline")
    cand_dir = tmp_path / "candidate"
    _write(_report(27, 30), cand_dir)  # a clear regression
    att_path = tmp_path / "reg.att.json"
    res = runner.invoke(
        app,
        ["report", "--in", str(cand_dir), "--baseline", str(base_json),
         "--attest-out", str(att_path)],
        env={"PROVAEL_SIGNING_KEY": ""},  # force an ephemeral key (deterministic test env)
    )
    # The gate exits non-zero on the regression, but the attestation is written regardless.
    assert res.exit_code == 1, res.output
    att = RegressionAttestation.model_validate_json(att_path.read_text())
    assert att.signed is True  # ephemeral-signed by default
    assert verify_regression_attestation(att).strict_ok is True
