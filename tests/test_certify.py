"""`provael certify` — the Machinery conformity-assessment evidence dossier.

Covers: the dossier's separately-addressable sections over a stub-policy run; the non-negotiable
transfer-statement honesty (a family with no real-policy transfer is labelled so, in the same
sentence as its ASR); the preliminary flag under 5 seeds; OSCAL validity + control bindings;
determinism; the profile switch parity with the hosted Annex III pack; the component-metadata
overlay; and a guard that no scoring is reimplemented (the dossier calls provael.scoring.asr /
provael.calibration, it does not re-derive them).
"""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import provael.certify as certify_mod
from provael.certify import (
    CertifyProfile,
    build_dossier,
    to_dossier_html,
    to_dossier_json,
    to_dossier_oscal_json,
)
from provael.cli import app
from provael.config import RunConfig
from provael.hosted.machinery import build_machinery_annex_pack
from provael.runner import run
from provael.types import ComponentProfile, RunReport

runner = CliRunner()

_ISSUED = "2026-07-05T00:00:00Z"
_COMMIT = "abc1234"


def _report(attacks: list[str] | None = None, episodes: int = 5) -> RunReport:
    """A deterministic stub run with a benign control (CPU, fast)."""
    return run(
        RunConfig(
            policy="stub", suite="stub",
            attacks=attacks or ["none", "instruction", "action"],
            episodes=episodes, seed=0, out=Path("runs/_certify_test"),
        )
    )


def _annex_i(report: RunReport, **kw: object) -> dict[str, object]:
    return build_dossier(
        report, profile=CertifyProfile.annex_i_part_a, issued_at=_ISSUED, commit=_COMMIT, **kw
    )


# --------------------------------------------------------------------------------------------
# dossier structure — every artifact is separately addressable
# --------------------------------------------------------------------------------------------

def test_dossier_has_all_addressable_sections() -> None:
    d = _annex_i(_report())
    assert d["format"] == "provael-machinery-annex-i-part-a-dossier/v1"
    assert d["applies_from"] == "2027-01-20"
    assert set(d) >= {
        "component_identification", "adversarial_evidence", "transfer_statement",
        "residual_risk", "standards_crosswalk", "referenced_artifacts",
        "attestation_statement", "not_a_conformity_assessment", "disclaimers",
    }
    # Prominent "not a conformity assessment / not a notified body" framing.
    framing = str(d["not_a_conformity_assessment"])
    assert "NOT a conformity assessment" in framing and "notified body" in framing
    # Every per-family row carries its n and BOTH intervals.
    for row in d["adversarial_evidence"]["per_family"]:
        assert {"n", "asr", "wilson_ci95", "anytime_ci", "matched_benign_fpr",
                "succ_but_unsafe", "transfer_status"} <= set(row)
    # The EAI Top 10 is never branded OWASP (it is an independent list).
    assert any("not OWASP" in str(x) for x in d["disclaimers"])
    # Referenced (not duplicated) ML-BOM + attestation.
    refs = d["referenced_artifacts"]
    assert refs["ml_bom"]["file"] == "report.mlbom.json"
    assert refs["attestation"]["file"] == "attestation.json"


def test_headline_evidence_carries_every_number_with_its_n() -> None:
    head = _annex_i(_report())["adversarial_evidence"]["headline"]
    assert head["attempts"] > 0 and head["successes"] >= 0
    assert head["wilson_ci95"] is not None and head["anytime_ci"] is not None
    assert head["benign_fpr"] == 0.0  # the `none` control ran on the stub


# --------------------------------------------------------------------------------------------
# transfer-statement honesty — the non-negotiable discipline
# --------------------------------------------------------------------------------------------

def test_family_without_transfer_is_labelled_in_the_same_sentence_as_its_asr() -> None:
    d = _annex_i(_report())
    rows = d["adversarial_evidence"]["per_family"]
    assert rows  # families ran
    for row in rows:
        # A stub run demonstrates nothing on a real policy: every family says so, next to its ASR.
        assert row["transfer_demonstrated"] is False
        assert "ASR" in row["statement"]
        assert "not demonstrated on a real policy" in row["statement"]
    # The dedicated transfer-statement section mirrors it.
    for row in d["transfer_statement"]["per_family"]:
        assert "not demonstrated on a real policy" in row["statement"]


# --------------------------------------------------------------------------------------------
# preliminary flag — fewer than 5 distinct seeds
# --------------------------------------------------------------------------------------------

def test_preliminary_flag_below_five_seeds() -> None:
    head = _annex_i(_report(episodes=3))["adversarial_evidence"]["headline"]
    assert head["seeds"] == 3
    assert head["preliminary"] is True
    assert head["preliminary_note"] is not None
    # A 5-seed run is bankable.
    banked = _annex_i(_report(episodes=5))["adversarial_evidence"]["headline"]
    assert banked["preliminary"] is False and banked["preliminary_note"] is None


# --------------------------------------------------------------------------------------------
# residual risk — plainly states what was NOT tested
# --------------------------------------------------------------------------------------------

def test_residual_risk_states_untested_scope() -> None:
    rr = _annex_i(_report(attacks=["none", "instruction"]))["residual_risk"]
    # A family that did not run this run is named as not exercised.
    assert "backdoor" in rr["families_not_exercised_this_run"]
    # SAFETY.md-deferred classes and permanently out-of-scope items are surfaced.
    assert any("GCG" in s for s in rr["deferred_attack_classes"])
    assert any("physical injury" in s for s in rr["out_of_scope"])


# --------------------------------------------------------------------------------------------
# OSCAL twin — schema validity + control bindings
# --------------------------------------------------------------------------------------------

def test_dossier_oscal_is_valid_and_bound_to_the_crosswalk() -> None:
    doc = json.loads(to_dossier_oscal_json(_report(), profile=CertifyProfile.annex_i_part_a))
    ar = doc["assessment-results"]
    assert ar["metadata"]["oscal-version"] == "1.1.2"
    assert ar["import-ap"]["href"] == "urn:provael:profile:machinery-annex-i-part-a"
    controls = ar["results"][0]["reviewed-controls"]["control-selections"][0]["include-controls"]
    ids = {c["control-id"] for c in controls}
    assert "eu-machinery-annex-i-part-a" in ids
    assert "nist-ai-100-2-taxonomy" in ids


# --------------------------------------------------------------------------------------------
# determinism
# --------------------------------------------------------------------------------------------

def test_dossier_is_deterministic_given_fixed_metadata() -> None:
    report = _report()
    assert to_dossier_json(_annex_i(report)) == to_dossier_json(_annex_i(report))


# --------------------------------------------------------------------------------------------
# profile switch — annex-iii shares this code path with the hosted pack
# --------------------------------------------------------------------------------------------

def test_annex_iii_profile_matches_the_hosted_pack_shape() -> None:
    report = _report()
    via_profile = build_dossier(
        report, profile=CertifyProfile.annex_iii, issued_at=_ISSUED, commit=_COMMIT
    )
    via_hosted = build_machinery_annex_pack(report, issued_at=_ISSUED, commit=_COMMIT)
    assert via_profile == via_hosted
    assert via_profile["format"] == "provael-machinery-annex-iii-pack/v1"


# --------------------------------------------------------------------------------------------
# component-metadata overlay
# --------------------------------------------------------------------------------------------

def test_component_metadata_overlay_and_placeholder() -> None:
    report = _report()
    absent = _annex_i(report)["component_identification"]["operator_declared"]
    assert absent["manufacturer"] is None
    assert "[operator to complete]" in to_dossier_html(_annex_i(report))

    comp = ComponentProfile(manufacturer="Acme Robotics", intended_use="bin picking")
    present = _annex_i(report, component=comp)["component_identification"]["operator_declared"]
    assert present["manufacturer"] == "Acme Robotics"
    assert present["intended_use"] == "bin picking"


# --------------------------------------------------------------------------------------------
# no scoring is reimplemented — the dossier calls provael.scoring.asr / provael.calibration
# --------------------------------------------------------------------------------------------

def test_dossier_reuses_scoring_functions_without_reimplementing_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"wilson": 0, "anytime": 0, "by_family": 0}
    real_wilson = certify_mod.wilson_ci
    real_anytime = certify_mod.anytime_ci
    real_by_family = certify_mod.by_family

    def wrapped_wilson(*a: object, **k: object) -> object:
        calls["wilson"] += 1
        return real_wilson(*a, **k)  # type: ignore[arg-type]

    def wrapped_anytime(*a: object, **k: object) -> object:
        calls["anytime"] += 1
        return real_anytime(*a, **k)  # type: ignore[arg-type]

    def wrapped_by_family(*a: object, **k: object) -> object:
        calls["by_family"] += 1
        return real_by_family(*a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(certify_mod, "wilson_ci", wrapped_wilson)
    monkeypatch.setattr(certify_mod, "anytime_ci", wrapped_anytime)
    monkeypatch.setattr(certify_mod, "by_family", wrapped_by_family)

    _annex_i(_report())
    assert calls["wilson"] > 0 and calls["anytime"] > 0 and calls["by_family"] > 0


def test_certify_module_imports_the_scoring_modules() -> None:
    tree = ast.parse(inspect.getsource(certify_mod))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert "provael.scoring.asr" in imported
    assert "provael.calibration" in imported


# --------------------------------------------------------------------------------------------
# CLI end-to-end (stub, CPU)
# --------------------------------------------------------------------------------------------

def test_cli_certify_writes_the_bundle(tmp_path: Path) -> None:
    out = tmp_path / "dossier"
    res = runner.invoke(
        app,
        ["certify", "--profile", "annex-i-part-a", "--attacks", "none,instruction",
         "--episodes", "3", "--out", str(out)],
    )
    assert res.exit_code == 0, res.output
    assert (out / "dossier.json").is_file()
    assert (out / "dossier.oscal.json").is_file()
    assert (out / "dossier.html").is_file()
    html = (out / "dossier.html").read_text(encoding="utf-8")
    assert "NOT a conformity assessment" in html
    assert "not demonstrated on a real policy" in html


def test_cli_certify_annex_iii_profile(tmp_path: Path) -> None:
    out = tmp_path / "annex3"
    res = runner.invoke(app, ["certify", "--profile", "annex-iii", "--episodes", "5",
                              "--out", str(out)])
    assert res.exit_code == 0, res.output
    data = json.loads((out / "dossier.json").read_text(encoding="utf-8"))
    assert data["format"] == "provael-machinery-annex-iii-pack/v1"


def test_cli_certify_help() -> None:
    res = runner.invoke(app, ["certify", "--help"])
    assert res.exit_code == 0
    assert "evidence" in res.output.lower()
