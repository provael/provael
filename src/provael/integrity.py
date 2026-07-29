"""Checkpoint supply-chain integrity — a pre-load control for the CI gate.

WHAT THIS IS, AND WHAT IT IS NOT
--------------------------------
This is a **supply-chain control**, not an adversarial-robustness measurement. It answers "are we
about to load the weights we think we are, in a format that is safe to load?" — a question with a
yes/no answer, checked once, before any policy is instantiated.

It is **not** an attack, it produces **no attack-success rate**, and it does **not** reduce one. A
checkpoint that passes every check here can still be driven off-task by a reworded instruction at
exactly the rate the ASR says. Nothing in this module may be reported as, aggregated into, or
described as moving an ASR. The two live in the same evidence pack because an assessor needs both;
they are not the same claim and must never be added together.

WHY IT EXISTS
-------------
Provael's own ``SECURITY.md`` documents **CVE-2026-25874** — LeRobot unauthenticated
pickle-deserialization RCE (CVSS 9.8), affecting ``lerobot`` through ``0.5.1``, in the
async-inference ``PolicyServer`` which ``pickle.loads`` untrusted payloads over an unauthenticated
gRPC endpoint (TCP/50051). Provael never starts that PolicyServer, so *that* path is not reachable
through Provael — but the same class of risk reaches any tool that loads a third-party checkpoint,
because loading a pickle executes it. The tool named the risk publicly and the reusable Action did
not check for it.

EAI MAPPING
-----------
**EAI03 — Model & pipeline poisoning, backdoors & supply chain.** The mapping is in the title:
this is checkpoint supply-chain integrity. It is deliberately NOT filed under EAI07, whose entry
declares CPS/firmware/comms/teleoperation out of scope; that scoping is about *attacks Provael
does not run*, and it would be wrong to imply this control closes any part of it. The
PolicyServer RCE that motivates this has an EAI07 flavour, but what the gate actually inspects is
the checkpoint artifact, which is EAI03.

Note EAI03 is ``attacks-implemented`` (the ``backdoor`` family screens objective-decoupled
triggers). This control sits alongside that, not inside it: the backdoor family produces a rate,
this produces a verdict.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

#: The EAI risk this control belongs to. See the module docstring for why not EAI07.
INTEGRITY_EAI_ID = "EAI03"

#: Artifact filename written into the run's output directory.
INTEGRITY_JSON = "checkpoint-integrity.json"

#: Format id for the emitted artifact.
INTEGRITY_FORMAT = "provael-checkpoint-integrity/v1"

#: Weight-file suffixes that execute arbitrary code on load. `.bin`/`.pt`/`.pth`/`.ckpt` are
#: torch archives (zip-wrapped pickles); `.pkl` is a bare pickle. Loading any of them from an
#: untrusted source is equivalent to running its author's code.
PICKLE_SUFFIXES: tuple[str, ...] = (".bin", ".pt", ".pth", ".ckpt", ".pkl", ".pickle")

#: The safe alternative: a length-prefixed tensor container with no code path.
SAFETENSORS_SUFFIX = ".safetensors"


class CheckpointFormat(StrEnum):
    """What kind of weights the checkpoint ships."""

    safetensors = "safetensors"
    #: Pickle-format weights present and no safetensors alternative.
    pickle = "pickle"
    #: Both present — loadable safely, so `prefer_safetensors` is satisfiable.
    mixed = "mixed"
    #: No recognised weight file (e.g. a hub id that was never fetched locally).
    unknown = "unknown"


class IntegrityVerdict(StrEnum):
    """Outcome of the pre-load check."""

    passed = "pass"
    #: A check failed. The gate must not load the policy.
    failed = "fail"
    #: Checks were deliberately skipped by an explicit opt-out. Never the default.
    skipped = "skipped"


class CheckpointIntegrity(BaseModel):
    """The emitted evidence record. Carries no rate, by construction."""

    format: str = INTEGRITY_FORMAT
    eai_id: str = INTEGRITY_EAI_ID
    checkpoint: str
    verdict: IntegrityVerdict
    digest_sha256: str | None = Field(
        None, description="SHA-256 over the checkpoint's weight files, or None when not computed."
    )
    expected_digest: str | None = Field(
        None, description="The digest the caller pinned. None means nothing was pinned."
    )
    digest_match: bool | None = Field(
        None, description="None when no digest was pinned (which is itself a failure by default)."
    )
    checkpoint_format: CheckpointFormat = CheckpointFormat.unknown
    pickle_allowed: bool = False
    findings: list[str] = Field(default_factory=list)
    note: str = Field(
        "Supply-chain control, not an adversarial-robustness result. This verdict is not an "
        "attack-success rate and does not reduce one.",
        description="Travels with the record so the distinction survives being pasted elsewhere.",
    )


def _weight_files(path: Path) -> list[Path]:
    """Every recognised weight file under ``path``, sorted for determinism."""
    suffixes = (*PICKLE_SUFFIXES, SAFETENSORS_SUFFIX)
    if path.is_file():
        return [path] if path.suffix in suffixes else []
    return sorted(p for p in path.rglob("*") if p.is_file() and p.suffix in suffixes)


def detect_format(path: Path) -> CheckpointFormat:
    """Classify the checkpoint's weight format."""
    files = _weight_files(path)
    if not files:
        return CheckpointFormat.unknown
    has_safe = any(f.suffix == SAFETENSORS_SUFFIX for f in files)
    has_pickle = any(f.suffix in PICKLE_SUFFIXES for f in files)
    if has_safe and has_pickle:
        return CheckpointFormat.mixed
    return CheckpointFormat.safetensors if has_safe else CheckpointFormat.pickle


def digest_checkpoint(path: Path) -> str | None:
    """SHA-256 over the checkpoint's weight files, order-independent and path-independent.

    Hashes each file's bytes, sorts the per-file digests, and hashes the concatenation — so the
    result does not depend on directory layout or traversal order, and a caller can pin it once
    and re-check it anywhere. Returns None when there is nothing to hash, which the caller must
    treat as a failure rather than as a match.
    """
    files = _weight_files(path)
    if not files:
        return None
    per_file = sorted(hashlib.sha256(f.read_bytes()).hexdigest() for f in files)
    return hashlib.sha256("\n".join(per_file).encode()).hexdigest()


def verify_checkpoint(
    checkpoint: str,
    path: Path | None,
    *,
    expected_digest: str | None = None,
    allow_pickle: bool = False,
    require_pinned_digest: bool = True,
) -> CheckpointIntegrity:
    """Check a checkpoint BEFORE the policy is loaded. Fails closed by default.

    Fail-closed is the default on both axes, matching how the rest of the gate handles defaults
    (``fail-on-regression`` defaults true):

    * **No pinned digest is a failure**, not a pass. "We did not check" and "we checked and it
      matched" must never produce the same verdict — that is the whole value of the control.
      ``require_pinned_digest=False`` is the explicit opt-out.
    * **Pickle weights are refused** unless ``allow_pickle``. Loading a pickle executes it, so an
      unpinned pickle checkpoint is arbitrary code execution with extra steps. Where both formats
      are present the checkpoint is loadable safely, so ``mixed`` passes and the finding says to
      prefer safetensors.

    Args:
        checkpoint: Identity of the checkpoint (hub id or path), recorded in the evidence.
        path: Local path to the fetched checkpoint, or None when it was never fetched.
        expected_digest: The digest the caller pinned.
        allow_pickle: Explicit opt-in to loading pickle-format weights.
        require_pinned_digest: Whether an absent pin is a failure. Default True.
    """
    findings: list[str] = []
    fmt = CheckpointFormat.unknown
    actual: str | None = None

    if path is None or not path.exists():
        findings.append(
            f"checkpoint {checkpoint!r} was not fetched locally, so nothing could be verified — "
            "pin a local path to check it before load"
        )
    else:
        fmt = detect_format(path)
        actual = digest_checkpoint(path)
        if actual is None:
            findings.append(f"no recognised weight files under {path} — nothing to digest")

    match: bool | None = None
    if expected_digest:
        match = actual is not None and actual == expected_digest
        if not match:
            findings.append(
                f"digest MISMATCH: pinned {expected_digest[:16]}… but computed "
                f"{(actual or 'nothing')[:16]}… — refusing to load"
            )
    elif require_pinned_digest:
        findings.append(
            "no checkpoint digest was pinned. Failing closed: an unverified checkpoint is the "
            "supply-chain risk this control exists for. Pass the digest, or opt out explicitly."
        )

    if fmt is CheckpointFormat.pickle and not allow_pickle:
        findings.append(
            "checkpoint ships pickle-format weights and no safetensors. Loading a pickle executes "
            "it (cf. CVE-2026-25874). Refusing without an explicit opt-in; prefer safetensors."
        )
    elif fmt is CheckpointFormat.mixed:
        findings.append(
            "both safetensors and pickle weights are present — load the safetensors and do not "
            "fall back to the pickle."
        )
    elif fmt is CheckpointFormat.pickle and allow_pickle:
        findings.append(
            "pickle-format weights loaded under an explicit opt-in. This is code execution from "
            "the checkpoint author; it is accepted here, not made safe."
        )

    blocking = [
        f for f in findings
        if "MISMATCH" in f or "Failing closed" in f or "Refusing without" in f
        or "was not fetched" in f or "nothing to digest" in f
    ]
    verdict = IntegrityVerdict.failed if blocking else IntegrityVerdict.passed

    return CheckpointIntegrity(
        checkpoint=checkpoint,
        verdict=verdict,
        digest_sha256=actual,
        expected_digest=expected_digest,
        digest_match=match,
        checkpoint_format=fmt,
        pickle_allowed=allow_pickle,
        findings=findings,
    )


def skipped_record(checkpoint: str, reason: str) -> CheckpointIntegrity:
    """The record for an explicit opt-out — visible in the evidence, never silent."""
    return CheckpointIntegrity(
        checkpoint=checkpoint,
        verdict=IntegrityVerdict.skipped,
        findings=[f"checkpoint integrity checks were skipped by explicit opt-out: {reason}"],
    )


__all__ = [
    "INTEGRITY_EAI_ID",
    "INTEGRITY_JSON",
    "INTEGRITY_FORMAT",
    "PICKLE_SUFFIXES",
    "SAFETENSORS_SUFFIX",
    "CheckpointFormat",
    "IntegrityVerdict",
    "CheckpointIntegrity",
    "detect_format",
    "digest_checkpoint",
    "verify_checkpoint",
    "skipped_record",
]
