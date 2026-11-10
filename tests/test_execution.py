# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""ExecutionManifest: runtime provenance bound to the report, secret-safe, gaps explicit (Phase 8).

Pins the manifest by building it: it binds the report's canonical digest (the same one the
attestation subject uses), redacts / drops environment secrets, records unsupplied provenance in
`missing_fields` (never invented), and keeps the wall-clock OUT of the deterministic report — the
timestamps live in the manifest instead.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from provael.attest import SUBJECT_BINDING, build_statement
from provael.config import RunConfig
from provael.execution import (
    build_execution_manifest,
    redact_env,
    report_digest,
    to_execution_manifest_json,
)
from provael.report import load_report, report_json_bytes
from provael.runner import run

_REAL = Path(__file__).resolve().parent.parent / "results" / "smolvla_libero_object"


def _report():
    return run(RunConfig(policy="stub", suite="stub", attacks=["none", "instruction"], episodes=4))


def _manifest(**overrides: object):
    report = _report()
    base: dict[str, object] = {
        "run_id": "run-123", "package_version": "0.22.0", "protocol_version": "v1",
    }
    base.update(overrides)
    return build_execution_manifest(report, **base)  # type: ignore[arg-type]


def test_manifest_binds_the_projection_and_the_attestation_binds_the_file() -> None:
    report = _report()
    manifest = build_execution_manifest(report, run_id="r", package_version="0.22.0",
                                        protocol_version="v1")
    # the manifest binds the schema-aware projection, the digest a v1 attestation bound ...
    assert manifest.report_digest == report_digest(report)
    # ... and from 0.45 the attestation binds report.json's bytes: a different rule, so a
    # different digest. This test asserted they were equal until the v2 format landed.
    statement = build_statement(report, issued_at="2026-07-22T00:00:00Z", commit="c")
    assert statement.subject.binding == SUBJECT_BINDING
    assert statement.subject.digest["sha256"] == hashlib.sha256(
        report_json_bytes(report)).hexdigest()
    assert manifest.report_digest != statement.subject.digest["sha256"]


def test_env_is_allowlisted_and_secrets_redacted() -> None:
    env = {
        "PROVAEL_INTEGRATION": "1",          # allow-listed, safe -> kept
        "PROVAEL_HOSTED_LICENSE": "tok_abc",  # not allow-listed -> dropped
        "AWS_SECRET_ACCESS_KEY": "xxx",       # not allow-listed -> dropped
        "HOME": "/home/me",                   # not allow-listed -> dropped
    }
    red = redact_env(env)
    assert red == {"PROVAEL_INTEGRATION": "1"}  # only the allow-listed, non-secret var survives


def test_a_secret_named_allowlisted_var_is_redacted_not_leaked() -> None:
    # even if an allow-list ever included a secret-named var, its VALUE is redacted
    red = redact_env({"PROVAEL_LICENSE_TOKEN": "sk-123"}, allowlist=("PROVAEL_LICENSE_TOKEN",))
    assert red == {"PROVAEL_LICENSE_TOKEN": "***REDACTED***"}


def test_unsupplied_provenance_is_recorded_as_missing_not_invented() -> None:
    manifest = _manifest()  # no commit/hardware/timestamps supplied
    for gap in ("commit", "hardware", "started_at", "python_version"):
        assert gap in manifest.missing_fields
        assert getattr(manifest, gap) is None  # None, never a fabricated value


def test_supplied_provenance_clears_missing() -> None:
    manifest = _manifest(commit="abc123", hardware="cpu-x86", python_version="3.12.3",
                         os_name="linux", dep_lock_digest="d", started_at="t0", ended_at="t1",
                         accelerator="cpu", precision="fp32", repository="r")
    assert manifest.commit == "abc123" and "commit" not in manifest.missing_fields
    assert "hardware" not in manifest.missing_fields


def test_manifest_carries_evidence_state_and_verdict() -> None:
    manifest = _manifest()
    assert manifest.evidence_state == "stub"            # a stub run
    assert manifest.release_verdict == "incomplete"      # not release-grade


def test_digest_is_stable_and_sensitive() -> None:
    m = _manifest(commit="abc")
    assert m.digest() == m.digest()
    assert m.model_copy(update={"commit": "def"}).digest() != m.digest()


def test_the_report_itself_carries_no_wall_clock() -> None:
    # determinism contract: time lives in the manifest, NEVER in report.json
    report = _report()
    dumped = report.model_dump()
    for time_key in ("started_at", "ended_at", "issued_at", "timestamp", "generated_at"):
        assert time_key not in dumped
    manifest = build_execution_manifest(report, run_id="r", package_version="0.22.0",
                                        protocol_version="v1", started_at="2026-07-22T00:00:00Z")
    assert manifest.started_at == "2026-07-22T00:00:00Z"  # the manifest carries it instead


def test_serialisation_is_stable() -> None:
    m = _manifest(commit="abc")
    assert to_execution_manifest_json(m) == to_execution_manifest_json(m)


def test_committed_execution_manifest_is_honest_and_matches_a_fresh_build() -> None:
    report = load_report(_REAL)
    manifest = build_execution_manifest(
        report, run_id="smolvla-libero-2026-06-06", package_version="0.15.0",
        protocol_version="provael-redteam/v1", commit="smolvla-libero-2026-06-06",
        started_at="2026-06-06T00:00:00Z", ended_at="2026-06-06T00:00:00Z",
        repository="https://github.com/provael/provael",
    )
    # the legacy artifact's unknown runtime provenance is recorded as missing, never fabricated
    for gap in ("python_version", "os", "hardware", "accelerator"):
        assert gap in manifest.missing_fields
    assert manifest.report_digest == report_digest(report)  # bound to the report
    assert manifest.evidence_state == "legacy-unverified"
    # drift guard vs the checked-in manifest
    fresh = to_execution_manifest_json(manifest)
    assert fresh == (_REAL / "execution-manifest.json").read_text(encoding="utf-8")


def test_package_versions_are_recorded_and_their_absence_is_a_stated_gap() -> None:
    """Manifest schema 4 (P1.1): the stack's versions live here, never in report.json."""
    from provael.execution import EXECUTION_MANIFEST_VERSION
    from provael.runtime_versions import TRACKED_PACKAGES, installed_versions

    versions = installed_versions()
    assert set(versions) == set(TRACKED_PACKAGES)
    recorded = _manifest(package_versions=versions)
    assert recorded.manifest_schema_version == EXECUTION_MANIFEST_VERSION == 4
    assert recorded.package_versions == versions
    assert "package_versions" not in recorded.missing_fields
    # A package that is not installed is recorded as such, by name, not dropped.
    partial = _manifest(package_versions={"lerobot": None, "numpy": "2.2.6"})
    assert partial.package_versions == {"lerobot": None, "numpy": "2.2.6"}
    gap = _manifest()
    assert gap.package_versions is None and "package_versions" in gap.missing_fields
    assert "package_versions" not in _report().model_dump(), "never in the deterministic report"


def test_the_checkpoint_digest_is_carried_when_the_caller_supplies_it() -> None:
    manifest = _manifest(checkpoint_digest="ab" * 32)
    assert manifest.checkpoint_digest == "ab" * 32
    assert _manifest().checkpoint_digest is None


def test_every_committed_report_still_digests_to_the_manifest_beside_it() -> None:
    """A schema bump must leave every committed report digesting to the digest its manifest binds.

    The projection strips what a report did not declare (`attest._RESULT_FIELDS_ADDED_IN` and the
    tables beside it), and this is the test that notices a field added without a registration,
    at the top of the report, on an episode, or nested in `calibration` or `deployed_policy`.

    The twenty schema-2 shards of 9 August 2026 are excluded by their declared schema: their
    manifests (provael 0.32.0) bound a digest that no later release reproduces, before or after
    this change, and they say so by declaring schema 2.
    """
    import json

    checked = 0
    for path in sorted((_REAL.parent).rglob("report.json")):
        manifest_path = path.parent / "execution-manifest.json"
        if not manifest_path.is_file():
            continue
        if json.loads(path.read_text(encoding="utf-8")).get("schema_version") == 2:
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert report_digest(load_report(path)) == manifest["report_digest"], path
        checked += 1
    assert checked >= 100, f"only {checked} committed reports were checked"


def test_the_suite_config_digest_is_filled_from_the_report_s_predicates() -> None:
    """P1.7: null on every headline manifest so far, because nothing recorded the predicate."""
    from provael.execution import predicate_config_digest
    from provael.types import PredicateIdentity

    report = _report()
    assert set(report.predicates) == {"reach"}
    manifest = build_execution_manifest(report, run_id="r", package_version="0", protocol_version="v")
    assert manifest.suite_config_digest == predicate_config_digest(report) is not None
    # A different predicate on the task is a different suite config.
    moved = report.model_copy(update={"predicates": {"reach": PredicateIdentity.build(
        kind="scalar-threshold", rule="danger above 0.7", signal="danger", threshold=0.7,
        source="calibration")}})
    assert predicate_config_digest(moved) != manifest.suite_config_digest
    # An earlier report recorded no predicate, so its manifest says so rather than guessing.
    legacy = load_report(_REAL)
    assert predicate_config_digest(legacy) is None
    assert build_execution_manifest(
        legacy, run_id="r", package_version="0", protocol_version="v").suite_config_digest is None
