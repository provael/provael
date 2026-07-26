"""OSCAL assessment-results export: structure, determinism, and CLI wiring."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from provael.cli import app
from provael.config import RunConfig
from provael.oscal import to_oscal, to_oscal_json
from provael.runner import run

runner = CliRunner()


def _report():  # noqa: ANN202 - test helper
    return run(
        RunConfig(
            policy="stub", suite="stub", attacks=["instruction", "visual", "injection", "action"],
            episodes=10, seed=0,
        )
    )


def test_oscal_structure() -> None:
    doc = to_oscal(_report())
    ar = doc["assessment-results"]
    assert isinstance(ar, dict)
    result = ar["results"][0]  # type: ignore[index]
    assert len(result["observations"]) == 9  # one per attack
    assert len(result["risks"]) == 4  # EAI01/02/04/05
    assert result["findings"][0]["title"] == "Adversarial Attack Success Rate"
    assert ar["metadata"]["oscal-version"] == "1.1.2"  # type: ignore[index]


def test_oscal_finding_carries_transfer_status_prop() -> None:
    # D1: the run-level honesty tier surfaces as an OSCAL prop so a GRC consumer can't misread
    # stub scaffolding as a real-transfer measurement.
    doc = to_oscal(_report())
    finding = doc["assessment-results"]["results"][0]["findings"][0]  # type: ignore[index]
    props = {p["name"]: p["value"] for p in finding["props"]}
    assert props["transfer-status"] == "stub-validated-scaffolding"


def test_oscal_is_deterministic() -> None:
    # Stable uuid5 ids + no clock => byte-identical for a deterministic run.
    assert to_oscal_json(_report()) == to_oscal_json(_report())


def test_oscal_cli_stdout_and_file(tmp_path) -> None:  # noqa: ANN001
    out = tmp_path / "run"
    assert runner.invoke(app, ["attack", "--recipe", "full-sweep", "--format", "oscal",
                               "--out", str(out)]).exit_code == 0
    assert (out / "report.oscal.json").is_file()
    res = runner.invoke(app, ["report", "--in", str(out), "--format", "oscal"])
    assert res.exit_code == 0
    assert json.loads(res.stdout)["assessment-results"]["results"]  # valid JSON to stdout


def test_oscal_carries_every_schema_required_field() -> None:
    """Required-field conformance to the OSCAL assessment-results schema (v1.1.2).

    Verified against the required arrays in NIST's own
    ``oscal_assessment-results_schema.json`` for the version this exporter declares:

        observation     -> uuid, description, methods, collected
        risk            -> uuid, title, description, statement, status
        finding         -> uuid, title, description, target
        finding-target  -> type, target-id, status (status -> state)

    `collected`, `statement` and `target` were all absent, which made every observation, risk and
    finding schema-invalid — the export loaded in no conforming OSCAL tool.
    """
    report = run(
        RunConfig(policy="stub", suite="stub", attacks=["none", "instruction", "action"], episodes=4)
    )
    doc = to_oscal(report, collected="2026-07-26T00:00:00Z")
    res = doc["assessment-results"]["results"][0]  # type: ignore[index]

    assert res["observations"]
    for obs in res["observations"]:
        assert {"uuid", "description", "methods", "collected"} <= set(obs)
        assert obs["collected"] == "2026-07-26T00:00:00Z"

    assert res["risks"]
    for risk in res["risks"]:
        assert {"uuid", "title", "description", "statement", "status"} <= set(risk)
        assert risk["statement"].strip()

    assert res["findings"]
    for finding in res["findings"]:
        assert {"uuid", "title", "description", "target"} <= set(finding)
        target = finding["target"]
        assert {"type", "target-id", "status"} <= set(target)
        assert target["type"] in {"statement-id", "objective-id"}
        # target-id is a TokenDatatype: no whitespace, no colons.
        assert not any(c.isspace() or c == ":" for c in target["target-id"])
        assert target["status"]["state"] in {"satisfied", "not-satisfied"}


def test_oscal_target_state_follows_the_release_verdict() -> None:
    """The finding's state is derived, never a hardcoded conformity conclusion.

    A stub run cannot satisfy the default release gate (it is not a real-policy measurement), so it
    must report not-satisfied rather than a fixed `satisfied`.
    """
    from provael.verdict import release_verdict

    report = run(RunConfig(policy="stub", suite="stub", attacks=["none", "instruction"], episodes=4))
    decision = release_verdict(report)
    assert decision.verdict.value != "pass"  # a stub run is `incomplete` by design

    ar = to_oscal(report)["assessment-results"]  # type: ignore[index]
    target = ar["results"][0]["findings"][0]["target"]
    assert target["status"]["state"] == "not-satisfied"
    assert target["status"]["reason"] == f"release-verdict:{decision.verdict.value}"


def test_oscal_flags_an_unrecorded_collection_time_instead_of_inventing_one() -> None:
    """A RunReport carries no wall-clock, so an unsupplied `collected` must be visibly a sentinel."""
    from provael.oscal import UNRECORDED_COLLECTED

    report = run(RunConfig(policy="stub", suite="stub", attacks=["instruction"], episodes=2))
    ar = to_oscal(report)["assessment-results"]  # type: ignore[index]
    obs = ar["results"][0]["observations"][0]
    assert obs["collected"] == UNRECORDED_COLLECTED
    assert {"name": "collected-precision", "value": "unrecorded"} in obs["props"]
