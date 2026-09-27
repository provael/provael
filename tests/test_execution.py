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
