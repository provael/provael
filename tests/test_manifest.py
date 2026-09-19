"""The public evidence manifest: deterministic, honest, N/A-preserving (Phase 10).

Pins the manifest by building it: a pinned commit is required, the committed SmolVLA×LIBERO manifest
recovers the honest split (adversarial 17/60, all-episode 17/70, benign 0/10, mcp_tool_desc N/A),
the evidence state stays `legacy-unverified` and the verdict `incomplete`, no hardware/calibration
claim is smuggled in, and the checked-in artifact matches a fresh build byte-for-byte.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from provael.attest import RULESET_VERSION
from provael.config import RunConfig
from provael.manifest import (
    EVIDENCE_MANIFEST_FORMAT,
    build_evidence_manifest,
    to_evidence_manifest_json,
)
from provael.report import load_report
from provael.runner import run

_REAL = Path(__file__).resolve().parent.parent / "results" / "smolvla_libero_object"
_MANIFEST = _REAL / "evidence-manifest.json"
_REPO = "https://github.com/provael/provael"
_COMMIT = "smolvla-libero-2026-06-06"


def _manifest(report: object) -> dict:
    return build_evidence_manifest(
        report, repository=_REPO, commit=_COMMIT, regulatory_clock_version=RULESET_VERSION  # type: ignore[arg-type]
    )


def test_a_manifest_requires_a_pinned_commit() -> None:
    report = run(RunConfig(policy="stub", suite="stub", attacks=["none", "instruction"], episodes=4))
    with pytest.raises(ValueError, match="pinned commit"):
        build_evidence_manifest(report, repository=_REPO, commit="  ",
                                regulatory_clock_version=RULESET_VERSION)


def test_committed_artifact_manifest_is_honest() -> None:
    m = _manifest(load_report(_REAL))
    assert m["format"] == EVIDENCE_MANIFEST_FORMAT
    assert m["commit"] == _COMMIT
    assert m["evidence_state"] == "legacy-unverified"  # not re-promoted
    assert m["release_verdict"] == "incomplete"  # no protocol named -> not assessed
    assert m["release_assessed"] is False and m["acceptance_protocol"] is None
    assert (m["adversarial_asr"]["successes"], m["adversarial_asr"]["attempts"]) == (17, 60)
    allep = m["all_episode_observed_unsafe_rate"]
    assert (allep["successes"], allep["attempts"]) == (17, 70)
    assert m["benign_unsafe_rate"] == 0.0
    # mcp_tool_desc never applied -> N/A, not a fabricated 0
    mcp = next(r for r in m["per_attack"] if r["attack"] == "mcp_tool_desc")
    assert mcp["applicable"] is False and mcp["rate"] is None and mcp["wilson_ci95"] is None


def test_registry_counts_use_coverages_convention() -> None:
    """One convention: adversarial = registered minus the baseline AND the control family.

    The manifest used to subtract the baseline alone (18 families / 43 attacks) while
    `coverage.py` subtracted both (17 / 39); the website carried a conversion between its own
    upstream's two numbers. The manifest now reads `coverage.registry_counts()`.
    """
    from provael.coverage import coverage

    reg = _manifest(load_report(_REAL))["registry"]
    cov = coverage()
    assert reg["attacks_total"] == (
        reg["attacks_adversarial"] + reg["attacks_baseline"] + reg["attacks_control"]
    )
    assert reg["attacks_baseline"] == 1  # exactly one benign baseline
    assert reg["attacks_control"] == 4  # the harmless-variation arms
    assert reg["families_adversarial"] == reg["families_total"] - 2
    assert (reg["families_adversarial"], reg["attacks_adversarial"]) == (
        cov.adversarial_families, cov.adversarial_attacks
    )
    assert (reg["families_adversarial"], reg["attacks_adversarial"]) == (17, 39)


def test_defense_counts_say_study_and_real_policy_apart() -> None:
    """Two shipped defenses carry a study; both studies ran on the stub fixture."""
    reg = _manifest(load_report(_REAL))["registry"]
    assert reg["defenses_total"] == 2 and reg["defenses_with_study"] == 2
    assert reg["defenses_measured_real_policy"] == 0  # until a real-policy defended arm lands
    assert "defenses_measured" not in reg  # the ambiguous key is gone


def test_manifest_makes_no_unearned_claim() -> None:
    blob = json.dumps(_manifest(load_report(_REAL)))
    for forbidden in ("hardware-corroborated", "externally-reproduced", "measured-real-policy-effect"):
        assert forbidden not in blob  # a legacy artifact claims none of these
    assert any("Simulation only" in lim for lim in _manifest(load_report(_REAL))["limitations"])


def test_manifest_is_deterministic_and_matches_the_checked_in_artifact() -> None:
    report = load_report(_REAL)
    a = to_evidence_manifest_json(report, repository=_REPO, commit=_COMMIT,
                                  regulatory_clock_version=RULESET_VERSION)
    b = to_evidence_manifest_json(report, repository=_REPO, commit=_COMMIT,
                                  regulatory_clock_version=RULESET_VERSION)
    assert a == b  # no wall-clock -> byte-identical
    assert a == _MANIFEST.read_text(encoding="utf-8")  # drift guard vs the checked-in manifest
