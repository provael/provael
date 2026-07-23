"""ExecutionManifest — runtime provenance, bound to the deterministic report by digest (Phase 8).

``report.json`` is byte-deterministic and must stay that way, so it carries NO wall-clock time or
machine identity. Everything that necessarily does — timestamps, OS/Python, hardware, the code
commit and dirty state, the checkpoint revision, environment — lives here, in a separate manifest
bound to the report by its SHA-256 digest. The builder is a pure function of the report plus
provenance passed in by the caller (the CLI gathers it), so the manifest is testable and never leaks
a secret: env vars are allow-listed and secret-looking values are redacted. Fields the caller could
not supply are recorded in ``missing_fields`` — an honest gap, never an invented value.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from provael.attest import canonical_json, sha256_hex
from provael.evidence import evidence_state_of
from provael.types import RunReport
from provael.verdict import release_verdict

#: ExecutionManifest format version.
EXECUTION_MANIFEST_VERSION = 1

#: Environment-variable names allowed into the manifest. Anything else is dropped entirely; an
#: allow-listed name whose value looks secret is redacted (belt and braces).
ENV_ALLOWLIST: tuple[str, ...] = (
    "PROVAEL_INTEGRATION",
    "PROVAEL_REQUIRE_REAL_INTEGRATION",
    "PROVAEL_ENABLE_EXPERIMENTAL_HOSTED",
    "MUJOCO_GL",
    "PYOPENGL_PLATFORM",
    "PROVAEL_SMOLVLA_LIBERO_CKPT",
)
_SECRET_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "LICENSE", "CREDENTIAL", "PEM")
_REDACTED = "***REDACTED***"

#: Provenance fields the caller SHOULD supply; any left None is reported in ``missing_fields``.
_PROVENANCE_FIELDS = (
    "repository", "commit", "python_version", "os", "dep_lock_digest",
    "hardware", "accelerator", "precision", "started_at", "ended_at",
)


def redact_env(env: dict[str, str], allowlist: tuple[str, ...] = ENV_ALLOWLIST) -> dict[str, str]:
    """Keep only allow-listed env vars, redacting any whose NAME looks like a secret."""
    out: dict[str, str] = {}
    for name in allowlist:
        if name in env:
            secret = any(marker in name.upper() for marker in _SECRET_MARKERS)
            out[name] = _REDACTED if secret else env[name]
    return out


class ExecutionManifest(BaseModel):
    """Runtime provenance for one run, bound to its report by ``report_digest``."""

    manifest_schema_version: int = EXECUTION_MANIFEST_VERSION
    run_id: str
    protocol_id: str = "provael-redteam"
    protocol_version: str
    designation: str = Field("exploratory", description="'exploratory' | 'confirmatory'.")
    # code
    repository: str | None = None
    commit: str | None = None
    dirty: bool | None = None
    diff_digest: str | None = None
    package_version: str
    report_schema_version: int
    # platform
    os: str | None = None
    python_version: str | None = None
    dep_lock_digest: str | None = None
    hardware: str | None = None
    accelerator: str | None = None
    precision: str | None = None
    # policy / suite
    policy: str
    checkpoint_repo: str | None = None
    checkpoint_revision: str | None = None
    checkpoint_digest: str | None = None
    suite: str
    suite_config_digest: str | None = None
    # run
    seeds: int
    horizon: int
    attacks: list[str] = Field(default_factory=list)
    action_schema_digest: str | None = None
    # evidence
    evidence_state: str
    release_verdict: str
    report_digest: str
    # provenance
    started_at: str | None = None
    ended_at: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    network_policy: str = "offline-cpu-core"
    deviations: list[str] = Field(default_factory=list)
    skipped_checks: list[str] = Field(default_factory=list)
    operator: str | None = None
    reviewer: str | None = None
    missing_fields: list[str] = Field(
        default_factory=list,
        description="Provenance fields the caller could not supply — an explicit gap, never faked.",
    )

    def digest(self) -> str:
        """Stable SHA-256 of the canonical manifest."""
        return sha256_hex(canonical_json(json.loads(self.model_dump_json())))


def report_digest(report: RunReport) -> str:
    """The canonical report.json digest a manifest binds to (matches the attestation subject)."""
    return sha256_hex(canonical_json(json.loads(report.model_dump_json())))


def build_execution_manifest(
    report: RunReport,
    *,
    run_id: str,
    package_version: str,
    protocol_version: str,
    repository: str | None = None,
    commit: str | None = None,
    dirty: bool | None = None,
    diff_digest: str | None = None,
    python_version: str | None = None,
    os_name: str | None = None,
    dep_lock_digest: str | None = None,
    hardware: str | None = None,
    accelerator: str | None = None,
    precision: str | None = None,
    checkpoint_repo: str | None = None,
    checkpoint_revision: str | None = None,
    checkpoint_digest: str | None = None,
    suite_config_digest: str | None = None,
    action_schema_digest: str | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
    env: dict[str, str] | None = None,
    operator: str | None = None,
    reviewer: str | None = None,
    designation: str = "exploratory",
    deviations: list[str] | None = None,
    skipped_checks: list[str] | None = None,
) -> ExecutionManifest:
    """Build the execution manifest (pure): binds the report digest, redacts env, records gaps.

    Provenance the caller does not supply (commit, hardware, timestamps, ...) is left None and its
    field name recorded in ``missing_fields`` — never invented.
    """
    accel = accelerator if accelerator is not None else report.accelerator
    prec = precision if precision is not None else report.precision
    values: dict[str, str | bool | None] = {
        "repository": repository, "commit": commit, "python_version": python_version,
        "os": os_name, "dep_lock_digest": dep_lock_digest, "hardware": hardware,
        "accelerator": accel, "precision": prec, "started_at": started_at, "ended_at": ended_at,
    }
    missing = [name for name in _PROVENANCE_FIELDS if values.get(name) is None]
    return ExecutionManifest(
        run_id=run_id,
        protocol_version=protocol_version,
        designation=designation,
        repository=repository,
        commit=commit,
        dirty=dirty,
        diff_digest=diff_digest,
        package_version=package_version,
        report_schema_version=report.schema_version,
        os=os_name,
        python_version=python_version,
        dep_lock_digest=dep_lock_digest,
        hardware=hardware,
        accelerator=accel,
        precision=prec,
        policy=report.policy,
        checkpoint_repo=checkpoint_repo,
        checkpoint_revision=checkpoint_revision,
        checkpoint_digest=checkpoint_digest,
        suite=report.suite,
        suite_config_digest=suite_config_digest,
        seeds=report.seeds,
        horizon=report.horizon,
        attacks=list(report.attacks),
        action_schema_digest=action_schema_digest,
        evidence_state=evidence_state_of(report).value,
        release_verdict=release_verdict(report).verdict.value,
        report_digest=report_digest(report),
        started_at=started_at,
        ended_at=ended_at,
        env=redact_env(env or {}),
        deviations=list(deviations or []),
        skipped_checks=list(skipped_checks or []),
        operator=operator,
        reviewer=reviewer,
        missing_fields=missing,
    )


def to_execution_manifest_json(manifest: ExecutionManifest) -> str:
    """Serialise a manifest to stable, indented JSON (keys sorted; trailing newline)."""
    return json.dumps(json.loads(manifest.model_dump_json()), indent=2, sort_keys=True) + "\n"


__all__ = [
    "EXECUTION_MANIFEST_VERSION",
    "ENV_ALLOWLIST",
    "ExecutionManifest",
    "redact_env",
    "report_digest",
    "build_execution_manifest",
    "to_execution_manifest_json",
]
