"""Every surface that labels a run's transfer tier must read the ladder, not re-derive it.

THE BUG THIS PINS. `evidence.transfer_status_of` exists to be the one source of truth, and its
docstring names its callers: "All exporters (attestation, compliance, OSCAL, leaderboard,
assurance) call this instead of re-deriving ``policy != "stub" and suite != "stub"`` themselves."

Three of them did not. `certify._run_transfer_tier` carried a docstring claiming it was "the same
derivation the attestation and every exporter use" while doing the re-derivation itself, and
`assurance` did it twice — once for the family table and once for a bare ``real_model_run``
boolean that goes into the ATTESTATION, so it was inside the signed payload with no ladder behind
it at all.

WHY IT IS NOT ACADEMIC. `FIXTURE_SUITES` is ``{stub, reach, humanoid}``, not ``{stub}``. A real
policy on `reach` or `humanoid` runs in deterministic arithmetic that embodies nothing, so the
ladder gives it adapter-smoke. The re-derivation only asks whether the two NAMES are "stub", so it
awarded the same run measured-real-transfer. `mlbom.py:56-59` records this exact reasoning as a bug
it had already fixed — the fix simply never reached certify or assurance.

The sharpest form: `build_dossier` embeds an attestation statement that DOES read the ladder, so a
single dossier could carry two tiers that disagree about one run.

WHY THE FIXTURE IS BUILT THIS WAY. A real policy cannot run here — the non-stub adapters need a GPU
and the optional extras. But the defect lives entirely in how a report's `policy`/`suite` STRINGS
are read, so running on `reach` with the stub policy and renaming the policy afterwards reproduces
the exact condition: the recorded `evidence_state` still describes what actually ran (a fixture),
while the two strings now look "real" to anything that re-derives. That asymmetry is the bug, and
it is why a recorded ladder beats a derived one.
"""

from __future__ import annotations

import pytest

from provael.assurance import AssuranceProfile, build_assurance
from provael.certify import _run_transfer_tier
from provael.config import RunConfig
from provael.evidence import transfer_status_of
from provael.mlbom import to_ml_bom_json
from provael.runner import run
from provael.suites import FIXTURE_SUITES
from provael.types import MEASURED_REAL_TRANSFER, RunReport

ISSUED = "2026-08-26T00:00:00Z"
COMMIT = "0" * 40


@pytest.fixture(scope="module")
def fixture_suite_run_wearing_a_real_policy_name() -> RunReport:
    """A run that really happened on a FIXTURE suite, relabelled with a real policy name."""
    report = run(RunConfig(policy="stub", suite="reach", attacks=["roleplay", "none"], episodes=4))
    assert report.suite in FIXTURE_SUITES, "precondition: reach must still be a fixture suite"
    return report.model_copy(update={"policy": "smolvla"})


def test_reach_and_humanoid_are_fixtures_so_a_name_check_is_not_enough() -> None:
    """The precondition the whole defect rests on: 'not stub' does not mean 'not a fixture'."""
    assert {"reach", "humanoid"} <= FIXTURE_SUITES, (
        "reach/humanoid are no longer fixtures — re-read this module before trusting it."
    )


def test_certify_reads_the_ladder_not_the_policy_and_suite_names(
    fixture_suite_run_wearing_a_real_policy_name: RunReport,
) -> None:
    report = fixture_suite_run_wearing_a_real_policy_name
    ladder = transfer_status_of(report)

    assert ladder != MEASURED_REAL_TRANSFER, (
        "a fixture-suite run earns adapter-smoke; if the ladder now calls this real transfer the "
        "bug has moved rather than been fixed."
    )
    assert _run_transfer_tier(report) == ladder, (
        "certify disagrees with the evidence ladder about the same run. This is the "
        "`policy != 'stub' and suite != 'stub'` re-derivation returning, and build_dossier embeds "
        "an attestation statement that reads the ladder — so the dossier would carry two tiers."
    )


def test_the_signed_assurance_payload_agrees_with_the_ladder(
    fixture_suite_run_wearing_a_real_policy_name: RunReport,
) -> None:
    """`real_model_run` is embedded in the attestation, so this one is signed."""
    report = fixture_suite_run_wearing_a_real_policy_name
    real = transfer_status_of(report) == MEASURED_REAL_TRANSFER

    for profile in AssuranceProfile:
        payload = build_assurance(report, profile, issued_at=ISSUED, commit=COMMIT)
        assert payload["real_model_run"] == real, (
            f"assurance profile {profile.value} put real_model_run="
            f"{payload['real_model_run']} into the signed payload while the ladder says "
            f"{real}. A signature over a wrong tier is worse than no signature."
        )


def test_every_tier_bearing_surface_gives_the_same_answer(
    fixture_suite_run_wearing_a_real_policy_name: RunReport,
) -> None:
    """One run, one tier — across the ladder, certify, assurance and the ML-BOM."""
    report = fixture_suite_run_wearing_a_real_policy_name
    ladder = transfer_status_of(report)

    answers = {
        "evidence.transfer_status_of": ladder,
        "certify._run_transfer_tier": _run_transfer_tier(report),
    }
    bom_text = to_ml_bom_json(report)
    answers["mlbom (contains the ladder's tier)"] = ladder if ladder in bom_text else "DISAGREES"

    assert len(set(answers.values())) == 1, (
        "surfaces disagree about one run's transfer tier: "
        + "; ".join(f"{k} -> {v}" for k, v in answers.items())
    )


def test_a_genuine_stub_run_is_still_labelled_scaffolding() -> None:
    """The control: the fix must not have inverted anything for an ordinary stub run."""
    report = run(RunConfig(policy="stub", suite="stub", attacks=["roleplay", "none"], episodes=4))
    assert transfer_status_of(report) != MEASURED_REAL_TRANSFER
    assert _run_transfer_tier(report) == transfer_status_of(report)
    payload = build_assurance(report, AssuranceProfile.insurer, issued_at=ISSUED, commit=COMMIT)
    assert payload["real_model_run"] is False
