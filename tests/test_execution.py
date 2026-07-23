"""ExecutionManifest: runtime provenance bound to the report, secret-safe, gaps explicit (Phase 8).

Pins the manifest by building it: it binds the report's canonical digest (the same one the
attestation subject uses), redacts / drops environment secrets, records unsupplied provenance in
`missing_fields` (never invented), and keeps the wall-clock OUT of the deterministic report — the
timestamps live in the manifest instead.
"""

from __future__ import annotations

from provael.attest import build_statement
from provael.config import RunConfig
from provael.execution import (
    build_execution_manifest,
    redact_env,
    report_digest,
    to_execution_manifest_json,
)
from provael.runner import run


def _report():
    return run(RunConfig(policy="stub", suite="stub", attacks=["none", "instruction"], episodes=4))


def _manifest(**overrides: object):
    report = _report()
    base: dict[str, object] = {
        "run_id": "run-123", "package_version": "0.22.0", "protocol_version": "v1",
    }
    base.update(overrides)
    return build_execution_manifest(report, **base)  # type: ignore[arg-type]


def test_manifest_binds_the_same_report_digest_as_the_attestation() -> None:
    report = _report()
    manifest = build_execution_manifest(report, run_id="r", package_version="0.22.0",
                                        protocol_version="v1")
    # the manifest's report_digest matches both the standalone digest and the attestation subject
    assert manifest.report_digest == report_digest(report)
    statement = build_statement(report, issued_at="2026-07-22T00:00:00Z", commit="c")
    assert manifest.report_digest == statement.subject.digest["sha256"]


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
