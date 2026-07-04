"""Signed, dated attestation bundle for a :class:`~provael.types.RunReport` (v0.7.0).

``provael attest`` turns the existing compliance evidence (:mod:`provael.compliance`) into a
**tamper-evident, offline-verifiable** artifact — the piece an auditor or insurer keeps on file.
It wraps the *same* measured evidence (calibrated redirection rate + 95% Wilson CI + the
benign-FPR control + the per-EAI breakdown + the framework crosswalk), binds it with a SHA-256
digest of the source run, stamps a UTC issuance date + the crosswalk ruleset version + the source
commit, records a per-attack transfer-test status, and wraps it all in a DSSE-style envelope.

Two layers, so the free core keeps working and nothing is over-claimed:

* **Digest layer (always on, standard-library only).** The envelope carries the SHA-256 of the
  canonical statement bytes, and the statement's ``subject`` carries the SHA-256 of the canonical
  ``report.json``. ``attest --verify`` recomputes both offline. Any change to the evidence breaks
  the digest. This proves *integrity*, not identity, and the note on the bundle says exactly that.
* **Signature layer (opt-in, needs the ``attest`` extra).** With ``pip install 'provael[attest]'``
  the envelope is signed with Ed25519 over the DSSE pre-authentication encoding and verifies
  offline against the bundled public key. Ed25519 is deterministic, so a fixed
  ``(report, issued_at, ruleset, commit, key)`` yields a byte-identical signature — the tests pin
  those and assert reproducibility.

Determinism contract: :func:`build_statement` is a pure function of the ``RunReport`` and the
issuance metadata handed to it. The wall-clock date and the git commit are read by the CLI and
*passed in*, never read here, so the report-determinism contract in :mod:`provael.types` is
preserved. ``attest`` re-runs nothing: it reuses a ``report.json`` exactly like the compliance
export, so the whole path is CPU/stub-runnable.

This is **evidence, not certification** — the same honest-scope caveats travel inside the wrapped
compliance report. Provael is an independent project and is not affiliated with ISO, the EU, NIST,
IEC, OWASP, or MITRE.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from provael.attacks.optimized import FAMILY as OPTIMIZED_FAMILY
from provael.attacks.registry import FAMILIES
from provael.compliance import to_compliance_dict
from provael.types import RunReport

#: The attestation statement format id (our own DSSE-style envelope, not in-toto conformance).
STATEMENT_FORMAT = "provael-attestation/v1"
#: The wrapped predicate's type — the compliance-evidence crosswalk.
PREDICATE_TYPE = "provael-compliance-evidence/v1"
#: DSSE payload type for the envelope.
PAYLOAD_TYPE = "application/vnd.provael.attestation+json"
#: Ruleset version for the framework crosswalk. Bump when compliance.REQUIREMENTS changes.
RULESET_VERSION = "provael-attest-ruleset/1"

ATTESTATION_JSON = "attestation.json"
ATTESTATION_PUB = "attestation.pub"

#: Attack name -> family, from the registry (e.g. ``"roleplay" -> "instruction"``).
_NAME_TO_FAMILY: dict[str, str] = {name: fam for fam, names in FAMILIES.items() for name in names}


class MissingAttestExtraError(RuntimeError):
    """Raised when cryptographic signing/verification is requested without the ``attest`` extra."""


# --------------------------------------------------------------------------------------------
# Regulatory clock — factual application dates the attestation is measured against. Dates only;
# no claim of conformity. The EU AI Act line states BOTH the statutory and the (not-yet-adopted)
# proposed date, on purpose.
# --------------------------------------------------------------------------------------------

class RegulatoryClock(BaseModel):
    """One framework's application date (factual), carried alongside the crosswalk."""

    framework_id: str
    instrument: str
    applies_from: str
    note: str


REGULATORY_CLOCK: tuple[RegulatoryClock, ...] = (
    RegulatoryClock(
        framework_id="eu-machinery",
        instrument="Regulation (EU) 2023/1230 (Machinery Regulation)",
        applies_from="2027-01-20",
        note="Applies from 20 Jan 2027; AI-enabled safety functions need a cyber-risk assessment "
        "against corruption. This is the operative route for AI-enabled robots.",
    ),
    RegulatoryClock(
        framework_id="eu-ai-act",
        instrument="Regulation (EU) 2024/1689 (AI Act), Annex I machinery",
        applies_from="2027-08-02",
        note="High-risk obligations statutory from 2 Aug 2027. A move to 2 Aug 2028 is proposed "
        "in the Digital Omnibus but NOT yet adopted; treat 2027 as binding until it is.",
    ),
    RegulatoryClock(
        framework_id="iso-10218",
        instrument="ISO 10218-1/-2:2025",
        applies_from="2025-04-01",
        note="In force since 2025; the 2025 revision adds cybersecurity requirements for "
        "industrial robots, feeding the Machinery Regulation cyber-risk assessment.",
    ),
    RegulatoryClock(
        framework_id="nist",
        instrument="NIST AI 100-2e2025 (adversarial ML taxonomy)",
        applies_from="2025",
        note="Guidance, not a compliance deadline; used here to name the attack classes.",
    ),
)


# --------------------------------------------------------------------------------------------
# Statement models.
# --------------------------------------------------------------------------------------------

class AttestationSubject(BaseModel):
    """What is being attested: the run under test, bound by the digest of its report.json."""

    name: str = Field(..., description="policy x suite, e.g. 'stub x stub'.")
    digest: dict[str, str] = Field(..., description="Digest of the canonical report.json (sha256).")


class TransferStatus(BaseModel):
    """Per-attack honesty flag: is this a real-VLA transfer measurement or stub scaffolding?"""

    attack: str
    family: str
    status: str = Field(
        ..., description="'measured-real-transfer' | 'stub-validated-scaffolding'."
    )
    note: str


class AttestationStatement(BaseModel):
    """The signed payload: the compliance evidence plus its issuance and honesty metadata."""

    format: str = STATEMENT_FORMAT
    tool_version: str
    ruleset: str
    issued_at: str = Field(..., description="UTC ISO-8601 issuance timestamp (…Z).")
    commit: str = Field(..., description="Source commit (or tool version) the ruleset came from.")
    subject: AttestationSubject
    regulatory_clock: list[RegulatoryClock]
    transfer: list[TransferStatus]
    predicate_type: str = PREDICATE_TYPE
    predicate: dict[str, Any] = Field(..., description="The full compliance-evidence crosswalk.")


class AttestationSignature(BaseModel):
    """One Ed25519 signature over the DSSE pre-authentication encoding of the payload."""

    keyid: str = Field(..., description="First 16 hex chars of SHA-256(public-key PEM).")
    alg: str = "ed25519"
    sig: str = Field(..., description="Base64-encoded raw Ed25519 signature.")


class AttestationBundle(BaseModel):
    """DSSE-style envelope: the base64 payload, its digest, and zero or more signatures."""

    payloadType: str = PAYLOAD_TYPE
    payload: str = Field(..., description="Base64 of the canonical statement JSON.")
    payloadSha256: str = Field(..., description="Hex SHA-256 of the canonical statement bytes.")
    signed: bool
    signatures: list[AttestationSignature]
    note: str


class VerifyResult(BaseModel):
    """Outcome of verifying a bundle offline."""

    digest_ok: bool
    signature_ok: bool | None = Field(
        None, description="True/False if a signature was checked, None if unsigned / no key given."
    )
    keyid: str | None = None
    reasons: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Overall pass: digest intact and, if a signature was checked, it verified."""
        return self.digest_ok and self.signature_ok is not False


# --------------------------------------------------------------------------------------------
# Canonicalisation + DSSE PAE.
# --------------------------------------------------------------------------------------------

def _canonical(obj: Any) -> bytes:
    """Canonical JSON bytes: keys sorted, no incidental whitespace. Stable across runs."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pae(payload_type: str, payload: bytes) -> bytes:
    """DSSE pre-authentication encoding (what actually gets signed)."""
    t = payload_type.encode("utf-8")
    return b"DSSEv1 %d %b %d %b" % (len(t), t, len(payload), payload)


# --------------------------------------------------------------------------------------------
# Ed25519 backend (lazy — needs the ``attest`` extra).
# --------------------------------------------------------------------------------------------

def generate_private_key_pem() -> bytes:
    """Generate a fresh Ed25519 private key as PKCS8 PEM bytes."""
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError as exc:  # pragma: no cover - exercised via the CLI error path
        raise MissingAttestExtraError(
            "Signing an attestation needs the `attest` extra: pip install 'provael[attest]' "
            "(or pass --no-sign for a digest-only bundle)."
        ) from exc
    key = Ed25519PrivateKey.generate()
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def public_key_pem(private_key_pem: bytes) -> bytes:
    """Derive the SubjectPublicKeyInfo PEM for an Ed25519 private-key PEM."""
    try:
        from cryptography.hazmat.primitives import serialization
    except ImportError as exc:  # pragma: no cover
        raise MissingAttestExtraError(
            "Reading a key needs the `attest` extra: pip install 'provael[attest]'."
        ) from exc
    key = serialization.load_pem_private_key(private_key_pem, password=None)
    return key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _sign(private_key_pem: bytes, message: bytes) -> bytes:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = serialization.load_pem_private_key(private_key_pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("attest signing key must be an Ed25519 private key (PKCS8 PEM)")
    return key.sign(message)


def _verify(public_key_pem_bytes: bytes, signature: bytes, message: bytes) -> bool:
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:  # pragma: no cover
        raise MissingAttestExtraError(
            "Verifying a signature needs the `attest` extra: pip install 'provael[attest]'."
        ) from exc
    key = serialization.load_pem_public_key(public_key_pem_bytes)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("attest public key must be an Ed25519 public key (SPKI PEM)")
    try:
        key.verify(signature, message)
        return True
    except InvalidSignature:
        return False


def _keyid(public_key_pem_bytes: bytes) -> str:
    return _sha256_hex(public_key_pem_bytes)[:16]


# --------------------------------------------------------------------------------------------
# Shared digest + sign/verify helpers (reused by provael.leaderboard — one crypto path, not two).
# --------------------------------------------------------------------------------------------

def canonical_json(obj: Any) -> bytes:
    """Canonical JSON bytes (keys sorted, no incidental whitespace). Stable across runs."""
    return _canonical(obj)


def sha256_hex(data: bytes) -> str:
    """Hex SHA-256 of ``data``."""
    return _sha256_hex(data)


def sign_bytes(private_key_pem: bytes, payload_type: str, payload: bytes) -> tuple[str, str]:
    """Ed25519-sign ``payload`` over the DSSE PAE. Returns ``(keyid, base64 signature)``."""
    pub = public_key_pem(private_key_pem)
    signature = _sign(private_key_pem, _pae(payload_type, payload))
    return _keyid(pub), base64.b64encode(signature).decode("ascii")


def verify_bytes(
    public_key_pem_bytes: bytes, payload_type: str, payload: bytes, signature_b64: str
) -> bool:
    """Verify an Ed25519 signature produced by :func:`sign_bytes` (offline)."""
    signature = base64.b64decode(signature_b64)
    return _verify(public_key_pem_bytes, signature, _pae(payload_type, payload))


# --------------------------------------------------------------------------------------------
# Builders.
# --------------------------------------------------------------------------------------------

def _transfer_status(report: RunReport) -> list[TransferStatus]:
    """One honesty row per real attack: measured real transfer vs stub scaffolding."""
    real = report.policy != "stub" and report.suite != "stub"
    rows: list[TransferStatus] = []
    for attack in report.attacks:
        if attack == "none":
            continue
        family = _NAME_TO_FAMILY.get(attack, "unknown")
        if family == OPTIMIZED_FAMILY:
            rows.append(TransferStatus(
                attack=attack, family=family, status="stub-validated-scaffolding",
                note="Search-based scaffolding validated on the deterministic stub; real-VLA "
                "transfer is GPU-gated and not yet measured.",
            ))
        elif real:
            rows.append(TransferStatus(
                attack=attack, family=family, status="measured-real-transfer",
                note=f"Measured against a real policy ({report.policy} x {report.suite}).",
            ))
        else:
            rows.append(TransferStatus(
                attack=attack, family=family, status="stub-validated-scaffolding",
                note="Numbers are properties of the deterministic CPU stub, not a real VLA. "
                "Re-run against a real model for a transfer measurement.",
            ))
    return rows


def build_statement(
    report: RunReport,
    *,
    issued_at: str,
    commit: str,
    ruleset: str = RULESET_VERSION,
) -> AttestationStatement:
    """Build the attestation statement (pure): wraps the SAME compliance evidence as the export."""
    report_digest = _sha256_hex(_canonical(json.loads(report.model_dump_json())))
    return AttestationStatement(
        tool_version=report.tool_version,
        ruleset=ruleset,
        issued_at=issued_at,
        commit=commit,
        subject=AttestationSubject(
            name=f"{report.policy} x {report.suite}",
            digest={"sha256": report_digest},
        ),
        regulatory_clock=list(REGULATORY_CLOCK),
        transfer=_transfer_status(report),
        predicate=to_compliance_dict(report),
    )


def to_bundle(
    report: RunReport,
    *,
    issued_at: str,
    commit: str,
    ruleset: str = RULESET_VERSION,
    private_key_pem: bytes | None = None,
    sign: bool = True,
) -> tuple[AttestationBundle, bytes | None]:
    """Build a bundle from a report. Returns ``(bundle, public_key_pem_or_None)``.

    ``sign=True`` (default) signs with Ed25519 (needs the ``attest`` extra); an ephemeral key is
    generated when ``private_key_pem`` is None, and its public PEM is returned so the caller can
    write it next to the bundle. ``sign=False`` yields a digest-only bundle and returns None.
    """
    statement = build_statement(report, issued_at=issued_at, commit=commit, ruleset=ruleset)
    payload_bytes = _canonical(json.loads(statement.model_dump_json()))
    payload_b64 = base64.b64encode(payload_bytes).decode("ascii")
    payload_digest = _sha256_hex(payload_bytes)

    if not sign:
        return (
            AttestationBundle(
                payload=payload_b64,
                payloadSha256=payload_digest,
                signed=False,
                signatures=[],
                note="Digest-only: SHA-256 integrity binding, not a cryptographic signature. "
                "Install 'provael[attest]' to sign with Ed25519.",
            ),
            None,
        )

    priv_pem = private_key_pem if private_key_pem is not None else generate_private_key_pem()
    pub_pem = public_key_pem(priv_pem)
    signature = _sign(priv_pem, _pae(PAYLOAD_TYPE, payload_bytes))
    ephemeral = private_key_pem is None
    return (
        AttestationBundle(
            payload=payload_b64,
            payloadSha256=payload_digest,
            signed=True,
            signatures=[
                AttestationSignature(
                    keyid=_keyid(pub_pem),
                    sig=base64.b64encode(signature).decode("ascii"),
                )
            ],
            note=(
                "Ed25519 over the DSSE pre-authentication encoding. Verify offline: "
                "provael attest --verify <bundle> --pubkey <key>. "
                + ("Signed with an ephemeral key — proves integrity, not signer identity; "
                   "pass --key to sign with your organisation key."
                   if ephemeral else "Signed with the supplied key.")
            ),
        ),
        pub_pem,
    )


def verify_bundle(
    bundle: AttestationBundle | dict[str, Any],
    *,
    public_key_pem_bytes: bytes | None = None,
) -> VerifyResult:
    """Verify a bundle offline: recompute the digest, and check the signature if a key is given."""
    b = (
        bundle if isinstance(bundle, AttestationBundle)
        else AttestationBundle.model_validate(bundle)
    )
    reasons: list[str] = []

    payload_bytes = base64.b64decode(b.payload)
    digest_ok = _sha256_hex(payload_bytes) == b.payloadSha256
    reasons.append("payload digest matches" if digest_ok else "payload digest MISMATCH (tampered)")

    signature_ok: bool | None = None
    keyid: str | None = b.signatures[0].keyid if b.signatures else None
    if not b.signed or not b.signatures:
        reasons.append("bundle is digest-only (unsigned)")
    elif public_key_pem_bytes is None:
        reasons.append("signature present but no public key supplied — signature not checked")
    else:
        if _keyid(public_key_pem_bytes) != b.signatures[0].keyid:
            reasons.append("supplied public key does not match the signature keyid")
        signature = base64.b64decode(b.signatures[0].sig)
        signature_ok = _verify(public_key_pem_bytes, signature, _pae(b.payloadType, payload_bytes))
        reasons.append("signature verified" if signature_ok else "signature INVALID")

    return VerifyResult(
        digest_ok=digest_ok, signature_ok=signature_ok, keyid=keyid, reasons=reasons
    )


# --------------------------------------------------------------------------------------------
# I/O.
# --------------------------------------------------------------------------------------------

def to_bundle_json(bundle: AttestationBundle) -> str:
    """Serialise a bundle to stable, indented JSON (keys sorted; no trailing newline)."""
    return json.dumps(json.loads(bundle.model_dump_json()), indent=2, sort_keys=True)


def write_bundle(bundle: AttestationBundle, path: Path) -> Path:
    """Write the bundle JSON to ``path`` (parent dirs created). Returns ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_bundle_json(bundle) + "\n", encoding="utf-8")
    return path


def load_bundle(path: Path) -> AttestationBundle:
    """Load and validate a bundle from ``path``."""
    return AttestationBundle.model_validate_json(path.read_text(encoding="utf-8"))


__all__ = [
    "STATEMENT_FORMAT",
    "PREDICATE_TYPE",
    "PAYLOAD_TYPE",
    "RULESET_VERSION",
    "ATTESTATION_JSON",
    "ATTESTATION_PUB",
    "REGULATORY_CLOCK",
    "MissingAttestExtraError",
    "RegulatoryClock",
    "AttestationSubject",
    "TransferStatus",
    "AttestationStatement",
    "AttestationSignature",
    "AttestationBundle",
    "VerifyResult",
    "build_statement",
    "to_bundle",
    "verify_bundle",
    "to_bundle_json",
    "write_bundle",
    "load_bundle",
    "generate_private_key_pem",
    "public_key_pem",
    "canonical_json",
    "sha256_hex",
    "sign_bytes",
    "verify_bytes",
]
