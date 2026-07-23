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
from provael.evidence import EvidenceState, evidence_state_of, transfer_status_of
from provael.types import MEASURED_REAL_TRANSFER, STUB_VALIDATED_SCAFFOLDING, RunReport
from provael.verdict import ReleaseVerdict, release_verdict

#: The attestation statement format id (our own DSSE-style envelope, not in-toto conformance).
STATEMENT_FORMAT = "provael-attestation/v1"
#: The wrapped predicate's type — the compliance-evidence crosswalk.
PREDICATE_TYPE = "provael-compliance-evidence/v1"
#: DSSE payload type for the envelope.
PAYLOAD_TYPE = "application/vnd.provael.attestation+json"
#: Ruleset version for the framework crosswalk. Bump when compliance.REQUIREMENTS changes.
#: /2: added the CRA + ISO/IEC TR 5469 + ISO 42001/23894 rows and the D1 run-level transfer tier.
#: /3: added the eu-machinery:annex-i-part-a row (Machinery Reg Annex I Part A conformity route).
#: /4: added the optional standards-aligned `assurance` view (--profile; see provael.assurance).
RULESET_VERSION = "provael-attest-ruleset/4"

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
        framework_id="eu-cra",
        instrument="Regulation (EU) 2024/2847 (Cyber Resilience Act)",
        applies_from="2027-12-11",
        note="Main obligations apply from 2027-12-11; the earlier vulnerability/incident "
        "reporting duties apply from 2026-09-11. Products with digital elements (an AI-enabled "
        "robot qualifies) need essential cybersecurity requirements + conformity assessment. "
        "Dates factual (OJ 2024/2847); no conformity claim.",
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
    accelerator: str | None = Field(
        None, description="D6: execution device the attested run recorded, or None."
    )
    precision: str | None = Field(
        None, description="D6: compute precision the attested run recorded, or None."
    )
    evidence_state: str = Field(
        EvidenceState.LEGACY_UNVERIFIED.value,
        description="Evidence-ladder state of the attested run (provael.evidence.EvidenceState).",
    )
    release_verdict: str = Field(
        ReleaseVerdict.INCOMPLETE.value,
        description="Release verdict (provael.verdict): incomplete / fail / conditional / pass.",
    )
    regulatory_clock: list[RegulatoryClock]
    transfer: list[TransferStatus]
    predicate_type: str = PREDICATE_TYPE
    predicate: dict[str, Any] = Field(..., description="The full compliance-evidence crosswalk.")
    assurance: dict[str, Any] | None = Field(
        None,
        description="Optional standards-aligned assurance view (iso-10218-2 / iec-62443 / insurer) "
        "built by provael.assurance and embedded here when --profile is given; None otherwise.",
    )


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
    """Decomposed, fail-closed outcome of verifying a bundle offline.

    Each field names ONE established fact, because they are not interchangeable: an intact digest is
    not a signature, a cryptographically-valid signature is not a *trusted* one, and "no key given"
    is not "valid". ``overall_strict_ok`` requires the whole trusted chain and fails closed — an
    unsigned or untrusted bundle is never strict-OK. ``integrity_only_ok`` is the weaker digest-only
    check and must never be printed as plain "verified".
    """

    # Integrity layer.
    digest_ok: bool = Field(..., description="Payload SHA-256 matches the envelope digest.")
    subject_report_integrity_ok: bool | None = Field(
        None,
        description="Source report.json digest matches the signed subject; None when the source "
        "report was not supplied for an independent recheck (the embedded digest alone is not it).",
    )
    # Signature layer.
    signature_present: bool = Field(False, description="The bundle carries at least one signature.")
    signature_ok: bool | None = Field(
        None,
        description="Signature cryptographically valid; None if unsigned or no key was available.",
    )
    keyid_matches: bool | None = Field(
        None, description="The verifying key's id matches the signature's declared keyid."
    )
    signer_trusted: bool | None = Field(
        None,
        description="Signer is in the supplied trust store, active, not revoked, in window. None "
        "when no trust store was consulted — which is NOT trusted (strict fails closed on None).",
    )
    key_not_revoked: bool | None = Field(None, description="Trust-store status is not 'revoked'.")
    validity_window_ok: bool | None = Field(
        None, description="`now` is within the trusted key's validity window; None if not checked."
    )
    expected_binding_ok: bool | None = Field(
        None, description="Subject name matches the caller's expected binding; None if none given."
    )
    keyid: str | None = None
    reasons: list[str] = Field(default_factory=list)
    codes: list[str] = Field(
        default_factory=list, description="Machine-readable status codes (see verify_exit_code)."
    )

    # -- named property aliases: the exact vocabulary the docs/CLI speak --
    @property
    def payload_integrity_ok(self) -> bool:
        """The envelope payload was not altered (digest recomputes)."""
        return self.digest_ok

    @property
    def signature_cryptographically_valid(self) -> bool | None:
        """The signature verifies under the verifying key; None if not checked."""
        return self.signature_ok

    @property
    def signing_key_matches_declared_keyid(self) -> bool | None:
        """The verifying key's id equals the signature's declared keyid; None if not checked."""
        return self.keyid_matches

    @property
    def signer_identity_trusted(self) -> bool | None:
        """The signer is a trusted identity (via the trust store); None if none was consulted."""
        return self.signer_trusted

    @property
    def integrity_only_ok(self) -> bool:
        """Digest layer only: payload (and, if supplied, the source report) are intact. Proves
        integrity, NOT signer identity or trust — never surface this as plain "verified"."""
        return self.digest_ok and self.subject_report_integrity_ok is not False

    @property
    def overall_strict_ok(self) -> bool:
        """Fail-closed verdict: intact payload AND a present, cryptographically-valid,
        keyid-matching, TRUSTED, non-revoked, in-window signature. Unsigned/untrusted => False."""
        return (
            self.digest_ok
            and self.subject_report_integrity_ok is not False
            and self.expected_binding_ok is not False
            and self.signature_present
            and self.signature_ok is True
            and self.keyid_matches is True
            and self.signer_trusted is True
            and self.key_not_revoked is not False
            and self.validity_window_ok is not False
        )

    @property
    def ok(self) -> bool:
        """DEPRECATED — alias for :attr:`overall_strict_ok` (fail-closed).

        Before v0.23 ``ok`` returned ``digest_ok and signature_ok is not False``, so an *unsigned*
        or unchecked bundle passed as "ok". It no longer does. Call :attr:`overall_strict_ok` or
        :attr:`integrity_only_ok` explicitly for the property you actually mean.
        """
        return self.overall_strict_ok


# --------------------------------------------------------------------------------------------
# Local trust store — the ONLY thing that turns a cryptographically-valid signature into a
# *trusted* one. Absent a trust store, a valid signature is authentic-but-untrusted (self-signed or
# unknown signer) and strict verification fails closed. This is the verifier's own trust anchor; it
# is never shipped inside a bundle (a bundle vouching for its own signer would be circular).
# --------------------------------------------------------------------------------------------

#: Local trust-store format id.
TRUST_STORE_FORMAT = "provael-trust-store/v1"


class TrustedKey(BaseModel):
    """One trusted signer in a local trust store."""

    keyid: str = Field(..., description="First 16 hex chars of SHA-256(public-key PEM).")
    public_key_pem: str = Field(..., description="Ed25519 SubjectPublicKeyInfo PEM (text).")
    subject: str = Field(..., description="Human label for the signer (organisation / project).")
    not_before: str | None = Field(None, description="UTC ISO-8601; key invalid before this.")
    not_after: str | None = Field(None, description="UTC ISO-8601; key invalid after this.")
    status: str = Field("active", description="'active' | 'revoked'.")
    revocation_reason: str | None = None
    revoked_at: str | None = Field(
        None, description="UTC ISO-8601 revocation timestamp, if revoked."
    )


class TrustStore(BaseModel):
    """A local set of trusted signing keys — the verifier's trust anchor for strict verification."""

    format: str = TRUST_STORE_FORMAT
    keys: list[TrustedKey] = Field(default_factory=list)

    def find(self, keyid: str) -> TrustedKey | None:
        """The trusted key with this keyid, or None."""
        return next((k for k in self.keys if k.keyid == keyid), None)


def load_trust_store(path: Path) -> TrustStore:
    """Load a local trust store (JSON) from ``path``."""
    return TrustStore.model_validate_json(path.read_text(encoding="utf-8"))


def keyid_of(public_key_pem_bytes: bytes) -> str:
    """Keyid (first 16 hex of SHA-256(PEM)) of a public-key PEM — for building a trust store."""
    return _keyid(public_key_pem_bytes)


def _within_window(now: str | None, not_before: str | None, not_after: str | None) -> bool | None:
    """Whether ``now`` (ISO-8601, …Z) is within [not_before, not_after]; None if uncheckable.

    ISO-8601 UTC timestamps in the same ``…Z`` format sort lexicographically, so a string compare is
    a correct window test without pulling in a date parser. Returns None when there is nothing to
    check (no ``now`` given, or the key carries no window).
    """
    if now is None or (not_before is None and not_after is None):
        return None
    before_ok = not_before is None or now >= not_before
    after_ok = not_after is None or now <= not_after
    return before_ok and after_ok


def _report_digest(report: RunReport | dict[str, Any]) -> str:
    """The canonical report.json digest — what :func:`build_statement` binds as the subject."""
    obj = json.loads(report.model_dump_json()) if isinstance(report, RunReport) else report
    return _sha256_hex(_canonical(obj))


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
    # Phase 2: the run-level status comes from the ONE shared evidence-derived helper; the optimized
    # family keeps its per-family override below (GPU-gated, not yet measured).
    real = transfer_status_of(report) == MEASURED_REAL_TRANSFER
    rows: list[TransferStatus] = []
    for attack in report.attacks:
        if attack == "none":
            continue
        family = _NAME_TO_FAMILY.get(attack, "unknown")
        if family == OPTIMIZED_FAMILY:
            rows.append(TransferStatus(
                attack=attack, family=family, status=STUB_VALIDATED_SCAFFOLDING,
                note="Search-based scaffolding validated on the deterministic stub; real-VLA "
                "transfer is GPU-gated and not yet measured.",
            ))
        elif real:
            rows.append(TransferStatus(
                attack=attack, family=family, status=MEASURED_REAL_TRANSFER,
                note=f"Measured against a real policy ({report.policy} x {report.suite}).",
            ))
        else:
            rows.append(TransferStatus(
                attack=attack, family=family, status=STUB_VALIDATED_SCAFFOLDING,
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
    assurance: dict[str, Any] | None = None,
) -> AttestationStatement:
    """Build the attestation statement (pure): wraps the SAME compliance evidence as the export.

    ``assurance`` (optional) is a standards-aligned view built by :mod:`provael.assurance` and
    embedded verbatim into the signed payload; it is ``None`` for the default (no-profile) bundle,
    so existing attestations are unchanged apart from the schema/ruleset bump.
    """
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
        accelerator=report.accelerator,
        precision=report.precision,
        evidence_state=evidence_state_of(report).value,
        release_verdict=release_verdict(report).verdict.value,
        regulatory_clock=list(REGULATORY_CLOCK),
        transfer=_transfer_status(report),
        predicate=to_compliance_dict(report),
        assurance=assurance,
    )


def to_bundle(
    report: RunReport,
    *,
    issued_at: str,
    commit: str,
    ruleset: str = RULESET_VERSION,
    private_key_pem: bytes | None = None,
    sign: bool = True,
    assurance: dict[str, Any] | None = None,
) -> tuple[AttestationBundle, bytes | None]:
    """Build a bundle from a report. Returns ``(bundle, public_key_pem_or_None)``.

    ``sign=True`` (default) signs with Ed25519 (needs the ``attest`` extra); an ephemeral key is
    generated when ``private_key_pem`` is None, and its public PEM is returned so the caller can
    write it next to the bundle. ``sign=False`` yields a digest-only bundle and returns None.
    ``assurance`` (optional) is embedded into the signed statement (see :func:`build_statement`).
    """
    statement = build_statement(
        report, issued_at=issued_at, commit=commit, ruleset=ruleset, assurance=assurance
    )
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
    trust_store: TrustStore | None = None,
    subject_report: RunReport | dict[str, Any] | None = None,
    expected_subject_name: str | None = None,
    now: str | None = None,
) -> VerifyResult:
    """Verify a bundle offline, fail-closed, establishing each fact independently.

    - **Payload integrity** (always): the base64 payload recomputes to the envelope digest.
    - **Subject-report integrity** (only if ``subject_report`` is given): the report you hold
      hashes to the digest the signed subject binds — the embedded digest alone is not that check.
    - **Signature**: presence + cryptographic validity + keyid match, against the supplied public
      key or, absent that, the trust-store key carrying the signature's keyid.
    - **Signer trust** (ONLY via ``trust_store``): a valid signature from an unknown key is
      authentic but UNTRUSTED. Revocation and the validity window (needs ``now``) are checked here.

    ``overall_strict_ok`` holds only when the whole trusted chain does; ``integrity_only_ok`` is the
    weaker digest-only check. Malformed input degrades to a failed result, never an exception leak.
    """
    b = (
        bundle if isinstance(bundle, AttestationBundle)
        else AttestationBundle.model_validate(bundle)
    )
    reasons: list[str] = []
    codes: list[str] = []

    # -- payload integrity --
    try:
        payload_bytes = base64.b64decode(b.payload, validate=True)
    except ValueError:
        return VerifyResult(
            digest_ok=False,
            reasons=["payload is not valid base64 (malformed bundle)"],
            codes=["MALFORMED"],
        )
    digest_ok = _sha256_hex(payload_bytes) == b.payloadSha256
    reasons.append("payload digest matches" if digest_ok else "payload digest MISMATCH (tampered)")
    codes.append("PAYLOAD_OK" if digest_ok else "PAYLOAD_DIGEST_MISMATCH")

    statement: dict[str, Any] = {}
    if digest_ok:
        try:
            statement = json.loads(payload_bytes)
        except json.JSONDecodeError:
            statement = {}

    # -- subject-report integrity (independent recheck, only when a source report is supplied) --
    subject_report_integrity_ok: bool | None = None
    if subject_report is not None:
        claimed = statement.get("subject", {}).get("digest", {}).get("sha256")
        subject_report_integrity_ok = (
            claimed is not None and _report_digest(subject_report) == claimed
        )
        reasons.append(
            "subject report digest matches the attested subject" if subject_report_integrity_ok
            else "subject report digest MISMATCH (report != attested subject)"
        )
        codes.append("SUBJECT_OK" if subject_report_integrity_ok else "SUBJECT_REPORT_MISMATCH")

    # -- expected binding --
    expected_binding_ok: bool | None = None
    if expected_subject_name is not None:
        expected_binding_ok = statement.get("subject", {}).get("name") == expected_subject_name
        reasons.append(
            "subject binding matches expectation" if expected_binding_ok
            else "subject binding MISMATCH (not the expected run)"
        )
        codes.append("BINDING_OK" if expected_binding_ok else "BINDING_MISMATCH")

    # -- signature layer --
    signature_present = bool(b.signed and b.signatures)
    keyid: str | None = b.signatures[0].keyid if b.signatures else None
    signature_ok: bool | None = None
    keyid_matches: bool | None = None
    signer_trusted: bool | None = None
    key_not_revoked: bool | None = None
    validity_window_ok: bool | None = None

    if not signature_present:
        reasons.append("bundle is digest-only (unsigned) — integrity only, NOT a trusted signature")
        codes.append("UNSIGNED")
    else:
        trusted_key = trust_store.find(keyid) if (trust_store is not None and keyid) else None
        verify_pem = public_key_pem_bytes
        if verify_pem is None and trusted_key is not None:
            verify_pem = trusted_key.public_key_pem.encode("utf-8")

        if verify_pem is None:
            reasons.append("signature present but no public key or trust store — not checked")
            codes.append("NO_KEY")
        else:
            keyid_matches = _keyid(verify_pem) == keyid
            if not keyid_matches:
                reasons.append("verifying key id does not match the signature keyid")
                codes.append("KEYID_MISMATCH")
            try:
                signature = base64.b64decode(b.signatures[0].sig, validate=True)
                signature_ok = _verify(verify_pem, signature, _pae(b.payloadType, payload_bytes))
            except ValueError:
                signature_ok = False
            reasons.append(
                "signature cryptographically valid" if signature_ok else "signature INVALID"
            )
            codes.append("SIGNATURE_VALID" if signature_ok else "SIGNATURE_INVALID")

        # -- signer trust — established ONLY via the trust store --
        if trust_store is None:
            reasons.append("no trust store supplied — signer identity is UNTRUSTED")
            codes.append("SIGNER_UNTRUSTED")
        elif trusted_key is None:
            signer_trusted = False
            reasons.append(f"signer keyid {keyid} is not in the trust store — UNTRUSTED")
            codes.append("SIGNER_UNTRUSTED")
        else:
            key_not_revoked = trusted_key.status != "revoked"
            if not key_not_revoked:
                reasons.append(
                    f"trusted key is REVOKED ({trusted_key.revocation_reason or 'no reason given'})"
                )
                codes.append("KEY_REVOKED")
            validity_window_ok = _within_window(now, trusted_key.not_before, trusted_key.not_after)
            if validity_window_ok is False:
                reasons.append(
                    "outside the trusted key's validity window (expired / not yet valid)"
                )
                codes.append("OUTSIDE_VALIDITY_WINDOW")
            signer_trusted = bool(
                key_not_revoked
                and validity_window_ok is not False
                and keyid_matches is True
                and signature_ok is True
            )
            if signer_trusted:
                reasons.append(f"signer trusted: {trusted_key.subject}")
                codes.append("SIGNER_TRUSTED")

    result = VerifyResult(
        digest_ok=digest_ok,
        subject_report_integrity_ok=subject_report_integrity_ok,
        signature_present=signature_present,
        signature_ok=signature_ok,
        keyid_matches=keyid_matches,
        signer_trusted=signer_trusted,
        key_not_revoked=key_not_revoked,
        validity_window_ok=validity_window_ok,
        expected_binding_ok=expected_binding_ok,
        keyid=keyid,
        reasons=reasons,
        codes=codes,
    )
    if result.overall_strict_ok:
        result.codes.append("STRICT_OK")
    elif result.integrity_only_ok:
        result.codes.append("INTEGRITY_ONLY")
    return result


#: ``attest --verify`` exit codes — one per distinguishable verification state (fail-closed).
EXIT_OK = 0
EXIT_DIGEST_MISMATCH = 3
EXIT_UNSIGNED = 4
EXIT_SIGNATURE_INVALID = 5
EXIT_UNTRUSTED_SIGNER = 6
EXIT_KEYID_MISMATCH = 7
EXIT_KEY_REVOKED_OR_EXPIRED = 8
EXIT_SUBJECT_MISMATCH = 9
EXIT_MALFORMED = 10


def verify_exit_code(result: VerifyResult, *, integrity_only: bool = False) -> int:
    """Map a VerifyResult to a distinct, fail-closed exit code.

    ``integrity_only=True`` grades only the digest layer (exit 0 when ``integrity_only_ok``); the
    default strict grading requires the whole trusted chain.
    """
    if "MALFORMED" in result.codes:
        return EXIT_MALFORMED
    if not result.digest_ok:
        return EXIT_DIGEST_MISMATCH
    if result.subject_report_integrity_ok is False or result.expected_binding_ok is False:
        return EXIT_SUBJECT_MISMATCH
    if integrity_only:
        return EXIT_OK if result.integrity_only_ok else EXIT_DIGEST_MISMATCH
    if not result.signature_present:
        return EXIT_UNSIGNED
    if result.signature_ok is False:
        return EXIT_SIGNATURE_INVALID
    if result.keyid_matches is False:
        return EXIT_KEYID_MISMATCH
    if result.key_not_revoked is False or result.validity_window_ok is False:
        return EXIT_KEY_REVOKED_OR_EXPIRED
    if result.signer_trusted is not True:
        return EXIT_UNTRUSTED_SIGNER
    return EXIT_OK if result.overall_strict_ok else EXIT_UNTRUSTED_SIGNER


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
    "TRUST_STORE_FORMAT",
    "TrustedKey",
    "TrustStore",
    "load_trust_store",
    "keyid_of",
    "verify_exit_code",
    "EXIT_OK",
    "EXIT_DIGEST_MISMATCH",
    "EXIT_UNSIGNED",
    "EXIT_SIGNATURE_INVALID",
    "EXIT_UNTRUSTED_SIGNER",
    "EXIT_KEYID_MISMATCH",
    "EXIT_KEY_REVOKED_OR_EXPIRED",
    "EXIT_SUBJECT_MISMATCH",
    "EXIT_MALFORMED",
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
