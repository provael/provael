"""Hosted open-core surface: the entitlement gate, the pure insurer report, and the free core.

The key property under test: the paid gate is real, but it lives ONLY on the operated surface — the
free core (CLI, attacks, ASR, attest, and even the insurer-report *logic*) needs neither the
``[hosted]`` extra nor an entitlement. The FastAPI server is exercised only when ``fastapi`` is
present (it is not in the default CPU test env), behind an importorskip.
"""

from __future__ import annotations

import importlib.util

import pytest

from provael.config import RunConfig
from provael.hosted import (
    ENABLE_HOSTED_ENV,
    HOSTED_LICENSE_ENV,
    EntitlementError,
    HostedDisabledError,
    has_entitlement,
    require_entitlement,
)
from provael.hosted.machinery import build_machinery_annex_pack, to_machinery_annex_pack_json
from provael.hosted.report import CONFORMITY_MAPPING, DISCLAIMERS, build_insurer_report
from provael.runner import run

_HAS_FASTAPI = importlib.util.find_spec("fastapi") is not None


def _report():
    return run(RunConfig(
        policy="stub", suite="stub", attacks=["none", "backdoor"], episodes=5, seed=0,
    ))


# --------------------------------------------------------------------------------------------
# the entitlement gate (pure stdlib — no extra needed)
# --------------------------------------------------------------------------------------------

def test_require_entitlement_raises_without_the_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(HOSTED_LICENSE_ENV, raising=False)
    assert has_entitlement() is False
    # The message must NOT sell this as a paid tier or authentication — it is a local feature flag.
    with pytest.raises(EntitlementError, match="local feature flag") as exc:
        require_entitlement()
    assert "NOT authentication" in str(exc.value)


def test_require_entitlement_passes_with_a_license(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(HOSTED_LICENSE_ENV, "tok_123")
    assert has_entitlement() is True
    assert require_entitlement() == "tok_123"


# --------------------------------------------------------------------------------------------
# the insurer report is a pure function — no server, no fastapi, no license needed
# --------------------------------------------------------------------------------------------

def test_insurer_report_is_pure_and_structured() -> None:
    report = _report()
    out = build_insurer_report(report, issued_at="2026-07-05T00:00:00Z", commit="deadbeef")
    assert out["format"] == "provael-assurance-report-draft/v1"  # a draft, not an insurer opinion
    assert out["issued_at"] == "2026-07-05T00:00:00Z"
    assert set(out) >= {
        "attestation_statement", "compliance_crosswalk", "conformity_mapping",
        "disclaimers", "executive_summary", "subject",
    }
    assert len(out["conformity_mapping"]) == len(CONFORMITY_MAPPING) == 3
    assert out["disclaimers"] == list(DISCLAIMERS)
    # Honesty: the crosswalk carries the benign control and the transfer statuses.
    assert out["executive_summary"]["benign_fpr"] == 0.0
    assert "not affiliated" in " ".join(DISCLAIMERS)


def test_insurer_report_is_deterministic_given_fixed_metadata() -> None:
    report = _report()
    a = build_insurer_report(report, issued_at="2026-07-05T00:00:00Z", commit="abc")
    b = build_insurer_report(report, issued_at="2026-07-05T00:00:00Z", commit="abc")
    assert a == b


def test_insurer_report_carries_p04_honesty_signals() -> None:
    # D4: the exec summary now reads the headline against both intervals + the transfer tier, so an
    # insurer can't take a stub number as real.
    es = build_insurer_report(_report(), issued_at="2026-07-05T00:00:00Z", commit="x")[
        "executive_summary"
    ]
    assert es["transfer_status"] == "stub-validated-scaffolding"
    assert es["anytime_ci"] is not None and es["wilson_ci95"] is not None
    assert es["matched_benign_fpr"] == 0.0
    assert es["seeds"] == 5 and es["preliminary"] is False  # 5 seeds -> banked


# --------------------------------------------------------------------------------------------
# the EU Machinery Annex III evidence-pack (D3) — a pure function, gated at the server layer
# --------------------------------------------------------------------------------------------

def test_machinery_annex_pack_maps_the_cyber_ehsrs_and_is_honest() -> None:
    pack = build_machinery_annex_pack(_report(), issued_at="2026-07-05T00:00:00Z", commit="x")
    assert pack["format"] == "provael-machinery-annex-iii-pack/v1"
    assert pack["applies_from"] == "2027-01-20"
    ehsrs = {row["ehsr_id"]: row for row in pack["annex_iii_evidence"]}
    assert set(ehsrs) == {"Annex III, 1.1.9", "Annex III, 1.2.1"}  # the two cyber EHSRs
    assert all(row["transfer_status"] == "stub-validated-scaffolding" for row in ehsrs.values())
    assert "attestation_statement" in pack and pack["disclaimers"] == list(DISCLAIMERS)
    # Deterministic given fixed issuance metadata.
    assert to_machinery_annex_pack_json(
        _report(), issued_at="2026-07-05T00:00:00Z", commit="x"
    ) == to_machinery_annex_pack_json(_report(), issued_at="2026-07-05T00:00:00Z", commit="x")


# --------------------------------------------------------------------------------------------
# the free core does not require the [hosted] extra
# --------------------------------------------------------------------------------------------

def test_free_core_runs_without_the_hosted_extra() -> None:
    # A full stub red-team + the gate + the report logic all resolve without fastapi/uvicorn.
    report = _report()
    assert report.successes == 10  # backdoor fired on the planted stub (2 attacks x 5 episodes)
    # Building the (paid-surface) report logic needs no extra and no server.
    build_insurer_report(report, issued_at="2026-07-05T00:00:00Z", commit="x")


def test_create_app_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    # EXPERIMENTAL and off unless explicitly enabled — checked before anything else, so this holds
    # whether or not fastapi is installed.
    monkeypatch.delenv(ENABLE_HOSTED_ENV, raising=False)
    from provael.hosted.server import create_app

    with pytest.raises(HostedDisabledError, match="disabled by default"):
        create_app()


def test_create_app_without_fastapi_raises_a_clear_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    if _HAS_FASTAPI:
        pytest.skip("fastapi is installed; the missing-extra path is not exercisable here")
    monkeypatch.setenv(ENABLE_HOSTED_ENV, "1")  # get past the disabled-by-default gate
    from provael.hosted.server import MissingHostedExtraError, create_app

    with pytest.raises(MissingHostedExtraError, match="hosted"):
        create_app()


# --------------------------------------------------------------------------------------------
# the reference server (only when the [hosted] extra is present)
# --------------------------------------------------------------------------------------------

@pytest.mark.skipif(not _HAS_FASTAPI, reason="requires the `hosted` extra")
def test_server_builds_with_expected_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENABLE_HOSTED_ENV, "1")
    from provael.hosted.server import create_app

    app = create_app()
    paths = {getattr(r, "path", "") for r in app.routes}
    # /insurer-report is gone: the endpoint is the honestly-named assurance-report DRAFT.
    assert {"/healthz", "/attest", "/assurance-report"} <= paths
    assert "/insurer-report" not in paths


@pytest.mark.skipif(not _HAS_FASTAPI, reason="requires the `hosted` extra")
def test_attest_refuses_to_sign_with_a_throwaway_ephemeral_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The server must never mint an ephemeral key whose public half it then discards.
    monkeypatch.setenv(ENABLE_HOSTED_ENV, "1")
    monkeypatch.delenv("PROVAEL_SIGNING_KEY", raising=False)
    from fastapi.testclient import TestClient

    from provael.hosted.server import create_app

    report = _report()
    client = TestClient(create_app())
    resp = client.post("/attest?sign=true", json=report.model_dump(mode="json"))
    assert resp.status_code == 400
    assert "ephemeral" in resp.json()["detail"]
    # digest-only still works and asserts no signer authority
    ok = client.post("/attest", json=report.model_dump(mode="json"))
    assert ok.status_code == 200
    assert ok.json()["bundle"]["signed"] is False
