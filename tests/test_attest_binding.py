# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The v2 attestation format: report.json byte binding and the fixed-size signed record.

WHY THIS EXISTS. A v1 statement bound the report's model projection, because callers handed
`provael.attest` an already parsed report, and one edit to a published report.json reproduced that
digest: deleting a field whose stored value equals its default, which loading restores. v2 (0.45)
binds the SHA-256 of the file's bytes. Its signature covers a 306-byte record naming the statement
instead of the statement itself (tens of kilobytes), so an Ed25519 key held in AWS KMS can sign it:
KMS signs pure Ed25519 only over a raw message of at most 4096 bytes.

Pinned here: the v1 bundles an earlier release issued still verify, by the v1 rule; the v2 subject
is what `sha256sum report.json` prints; the signed message is the same size for every run;
provael's signatures are plain RFC 8032 Ed25519 that an outside implementation checks both ways;
and a signature cannot be moved between statement formats or payload types.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from provael.assurance import AssuranceProfile, build_assurance
from provael.attest import (
    EXIT_MALFORMED,
    EXIT_OK,
    EXIT_SIGNATURE_INVALID,
    EXIT_SUBJECT_MISMATCH,
    EXIT_UNSIGNED,
    PAYLOAD_TYPE,
    SIGNED_RECORD_TYPE,
    STATEMENT_FORMAT,
    STATEMENT_FORMAT_V1,
    SUBJECT_BINDING,
    V1_SUBJECT_RULE,
    AttestationBundle,
    AttestationSignature,
    TrustedKey,
    TrustStore,
    keyid_of,
    load_bundle,
    record_signing_message,
    signed_record,
    to_bundle,
    verify_bundle,
    verify_exit_code,
)
from provael.config import RunConfig
from provael.report import ReportArtifact, report_json_bytes, write_report
from provael.runner import run
from provael.types import RunReport

_HAS_CRYPTO = importlib.util.find_spec("cryptography") is not None
_needs_crypto = pytest.mark.skipif(not _HAS_CRYPTO, reason="requires the `attest` extra (cryptography)")

REPO = Path(__file__).resolve().parent.parent
V1 = REPO / "tests" / "fixtures" / "attestation_v1"
SMOLVLA = REPO / "results" / "smolvla_libero_object" / "report.json"
TIMING = REPO / "results" / "timing" / "libero_object_timing" / "report.json"

#: The frozen v1 fixtures, by SHA-256 (see tests/fixtures/attestation_v1/README.md). If one of these
#: moves, the file is no longer what an earlier release issued, and every assertion below about
#: "old bundles still verify" would be testing something else.
V1_FIXTURE_SHA256 = {
    "fixture.pub": "3a85cd22de2429707082b659251919616eb1e5a1772db21c472a51ff1d948948",
    "insurer_unsigned.attestation.json":
        "353627fe17e1120bbd91272826427725643f8a918d5511b3cb3018e8ca9b88c3",
    "smolvla_libero_object.attestation.json":
        "cef9e9d56899402c36c83d4095bcfb0ad61e88eda5e5db0224c5263a51607fd9",
    "timing_libero_object.attestation.json":
        "0591f27706b859f908fc59c338a80344d6cdb5b3c862ed5234c2e048ced09d1c",
}
V1_SIGNED = {
    "smolvla_libero_object.attestation.json": SMOLVLA,
    "timing_libero_object.attestation.json": TIMING,
}

_ISSUED = "2026-09-28T00:00:00Z"
_COMMIT = "attestation-v2-test"


def _stub() -> RunReport:
    return run(RunConfig(policy="stub", suite="stub", attacks=["none", "instruction"], episodes=3))


def _key(seed: bytes) -> tuple[bytes, bytes]:
    """A deterministic Ed25519 key pair as (private PKCS8 PEM, public SPKI PEM)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(seed).digest())
    priv = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    pub = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return priv, pub


def _store(pub: bytes) -> TrustStore:
    return TrustStore(keys=[TrustedKey(keyid=keyid_of(pub), public_key_pem=pub.decode(),
                                       subject="test")])


def _statement(bundle: AttestationBundle) -> dict[str, Any]:
    return json.loads(base64.b64decode(bundle.payload))  # type: ignore[no-any-return]


def _reencode(bundle: AttestationBundle, statement: dict[str, Any], **update: Any) -> dict[str, Any]:
    """The bundle with a rewritten payload and a matching envelope digest (an intact-looking lie)."""
    payload = json.dumps(statement, sort_keys=True, separators=(",", ":")).encode("utf-8")
    doc: dict[str, Any] = json.loads(bundle.model_dump_json())
    doc.update(payload=base64.b64encode(payload).decode("ascii"),
               payloadSha256=hashlib.sha256(payload).hexdigest(), **update)
    return doc


# --------------------------------------------------------------------------------------------
# v1: what an earlier release issued keeps verifying, by the v1 rule
# --------------------------------------------------------------------------------------------

def test_frozen_v1_fixtures_are_byte_identical() -> None:
    for name, digest in V1_FIXTURE_SHA256.items():
        assert hashlib.sha256((V1 / name).read_bytes()).hexdigest() == digest, name


@_needs_crypto
@pytest.mark.parametrize("name", sorted(V1_SIGNED))
def test_frozen_v1_bundles_still_verify_strict_with_their_reports(name: str) -> None:
    store = _store((V1 / "fixture.pub").read_bytes())
    r = verify_bundle(load_bundle(V1 / name), trust_store=store,
                      subject_report_bytes=V1_SIGNED[name].read_bytes())
    assert r.statement_format == STATEMENT_FORMAT_V1 and r.subject_binding == V1_SUBJECT_RULE
    assert r.subject_report_integrity_ok is True and r.overall_strict_ok is True
    assert verify_exit_code(r) == EXIT_OK
    assert any("model projection" in reason for reason in r.reasons), (
        "a v1 verdict must say it checked the projection, not the file"
    )


def test_frozen_v1_digest_only_sample_is_integrity_only() -> None:
    r = verify_bundle(load_bundle(V1 / "insurer_unsigned.attestation.json"),
                      subject_report_bytes=SMOLVLA.read_bytes())
    assert r.integrity_only_ok is True and r.subject_report_integrity_ok is True
    assert r.overall_strict_ok is False and verify_exit_code(r) == EXIT_UNSIGNED


def test_the_edit_v1_could_not_see_fails_v2() -> None:
    raw = SMOLVLA.read_bytes()
    doc = json.loads(raw)
    # `applicable` is stored as its default, so deleting it changes the file and not the report
    # that loads from it.
    assert doc["results"][0]["applicable"] is True
    del doc["results"][0]["applicable"]
    edited = (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode("utf-8")
    assert edited != raw

    v1 = verify_bundle(load_bundle(V1 / "insurer_unsigned.attestation.json"),
                       subject_report_bytes=edited)
    assert v1.subject_report_integrity_ok is True, "the v1 blind spot this format exists to close"

    bundle, _ = to_bundle(ReportArtifact.from_bytes(raw), issued_at=_ISSUED, commit=_COMMIT,
                          sign=False)
    v2 = verify_bundle(bundle, subject_report_bytes=edited)
    assert v2.subject_report_integrity_ok is False
    assert verify_exit_code(v2) == EXIT_SUBJECT_MISMATCH


# --------------------------------------------------------------------------------------------
# v2: the subject is the file
# --------------------------------------------------------------------------------------------

def test_v2_subject_is_what_sha256sum_prints(tmp_path: Path) -> None:
    write_report(_stub(), tmp_path)
    on_disk = (tmp_path / "report.json").read_bytes()
    bundle, _ = to_bundle(ReportArtifact.read(tmp_path), issued_at=_ISSUED, commit=_COMMIT,
                          sign=False)
    statement = _statement(bundle)
    assert statement["format"] == STATEMENT_FORMAT
    assert statement["subject"]["binding"] == SUBJECT_BINDING
    assert statement["subject"]["digest"]["sha256"] == hashlib.sha256(on_disk).hexdigest()

    # The committed real report too: the subject is its bytes, whichever release wrote them.
    real, _ = to_bundle(ReportArtifact.read(SMOLVLA), issued_at=_ISSUED, commit=_COMMIT,
                        sign=False)
    assert _statement(real)["subject"]["digest"]["sha256"] == hashlib.sha256(
        SMOLVLA.read_bytes()).hexdigest()


def test_report_json_is_written_as_lf_bytes(tmp_path: Path) -> None:
    report = _stub()
    write_report(report, tmp_path)
    written = (tmp_path / "report.json").read_bytes()
    assert written == report_json_bytes(report) and b"\r" not in written
    artifact = ReportArtifact.read(tmp_path)
    assert artifact.raw == written and ReportArtifact.read(tmp_path / "report.json") == artifact
    assert ReportArtifact.of(artifact) is artifact
    assert ReportArtifact.of(report).raw == written


def test_v2_catches_a_byte_a_line_ending_and_a_parsed_stand_in() -> None:
    artifact = ReportArtifact.read(SMOLVLA)
    bundle, _ = to_bundle(artifact, issued_at=_ISSUED, commit=_COMMIT, sign=False)

    ok = verify_bundle(bundle, subject_report_bytes=artifact.raw)
    assert ok.subject_report_integrity_ok is True and ok.integrity_only_ok is True

    for changed in (artifact.raw + b" ", artifact.raw.replace(b"\n", b"\r\n")):
        r = verify_bundle(bundle, subject_report_bytes=changed)
        assert r.subject_report_integrity_ok is False
        assert verify_exit_code(r) == EXIT_SUBJECT_MISMATCH

    # A parsed report cannot say which bytes it came from, so it cannot stand in for the file.
    parsed = verify_bundle(bundle, subject_report=artifact.report)
    assert parsed.subject_report_integrity_ok is False and "SUBJECT_BYTES_REQUIRED" in parsed.codes
    assert verify_exit_code(parsed) == EXIT_SUBJECT_MISMATCH


# --------------------------------------------------------------------------------------------
# the signed record: fixed size, under the KMS limit, plain Ed25519
# --------------------------------------------------------------------------------------------

def test_the_signed_message_is_fixed_size_and_under_the_kms_limit() -> None:
    small = ReportArtifact.of(_stub())
    large = ReportArtifact.read(SMOLVLA)
    assurance = build_assurance(large, AssuranceProfile.insurer, issued_at=_ISSUED,
                                commit=_COMMIT)
    sizes = set()
    for artifact, extra in ((small, None), (large, assurance)):
        bundle, _ = to_bundle(artifact, issued_at=_ISSUED, commit=_COMMIT, sign=False,
                              assurance=extra)
        payload = base64.b64decode(bundle.payload)
        record = signed_record(payload, _statement(bundle)["subject"]["digest"]["sha256"])
        sizes.add((len(record), len(record_signing_message(record))))
        if extra is not None:
            assert len(payload) > 4096, "the statement itself would not fit a KMS raw message"
    assert sizes == {(306, 363)}


def test_the_record_is_plain_canonical_json_over_the_payload_received() -> None:
    bundle, _ = to_bundle(_stub(), issued_at=_ISSUED, commit=_COMMIT, sign=False)
    payload = base64.b64decode(bundle.payload)
    subject = _statement(bundle)["subject"]["digest"]["sha256"]
    expected = json.dumps({
        "format": "provael-signed-record/v1",
        "payload_type": PAYLOAD_TYPE,
        "statement_sha256": hashlib.sha256(payload).hexdigest(),
        "subject_binding": SUBJECT_BINDING,
        "subject_sha256": subject,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert signed_record(payload, subject) == expected
    kind = SIGNED_RECORD_TYPE.encode()
    assert record_signing_message(expected) == (
        b"DSSEv1 %d %b %d %b" % (len(kind), kind, len(expected), expected)
    )


@_needs_crypto
@pytest.mark.parametrize(
    ("secret", "message", "signature"),
    [  # RFC 8032 section 7.1, TEST 1 and TEST 2
        ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60", "",
         "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e3970"
         "1cf9b46bd25bf5f0595bbe24655141438e7a100b"),
        ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb", "72",
         "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613"
         "d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ],
    ids=["rfc8032-test1", "rfc8032-test2"],
)
def test_the_signer_is_rfc8032_ed25519(secret: str, message: str, signature: str) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from provael.attest import _sign  # the one primitive every bundle signature goes through

    pem = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(secret)).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    assert _sign(pem, bytes.fromhex(message)).hex() == signature


@_needs_crypto
def test_signatures_interoperate_with_an_outside_ed25519_both_ways() -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    artifact = ReportArtifact.of(_stub())
    priv, pub = _key(b"interop")

    # provael signs; an independent Ed25519 verifier checks the record message.
    bundle, _ = to_bundle(artifact, issued_at=_ISSUED, commit=_COMMIT, private_key_pem=priv)
    payload = base64.b64decode(bundle.payload)
    message = record_signing_message(signed_record(payload, artifact.sha256))
    public = serialization.load_pem_public_key(pub)
    public.verify(base64.b64decode(bundle.signatures[0].sig), message)  # type: ignore[union-attr]

    # An outside signer (standing in for a KMS key) is handed only the 363-byte message; the
    # bundle it completes verifies strict.
    unsigned, _ = to_bundle(artifact, issued_at=_ISSUED, commit=_COMMIT, sign=False)
    outside = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"interop").digest())
    signed = unsigned.model_copy(update={
        "signed": True,
        "signatures": [AttestationSignature(
            keyid=keyid_of(pub), sig=base64.b64encode(outside.sign(message)).decode("ascii"),
        )],
    })
    r = verify_bundle(signed, trust_store=_store(pub), subject_report_bytes=artifact.raw)
    assert r.overall_strict_ok is True and verify_exit_code(r) == EXIT_OK


# --------------------------------------------------------------------------------------------
# a signature cannot move between formats or payload types
# --------------------------------------------------------------------------------------------

@_needs_crypto
def test_a_signature_cannot_cross_formats_or_payload_types() -> None:
    artifact = ReportArtifact.of(_stub())
    priv, pub = _key(b"confusion")
    store = _store(pub)
    bundle, _ = to_bundle(artifact, issued_at=_ISSUED, commit=_COMMIT, private_key_pem=priv)
    assert verify_bundle(bundle, trust_store=store).overall_strict_ok is True

    # 1. The envelope relabelled as another payload type.
    doc = json.loads(bundle.model_dump_json())
    doc["payloadType"] = SIGNED_RECORD_TYPE
    r = verify_bundle(doc, trust_store=store)
    assert r.statement_format_ok is False and r.overall_strict_ok is False
    assert verify_exit_code(r) == EXIT_MALFORMED

    # 2. The signed record presented AS the payload: the verifier before 0.45 checked a signature
    #    over PAE(payloadType, payload) for any payloadType, so this read as a valid signature.
    record = signed_record(base64.b64decode(bundle.payload), artifact.sha256)
    transplanted = AttestationBundle(
        payloadType=SIGNED_RECORD_TYPE, payload=base64.b64encode(record).decode("ascii"),
        payloadSha256=hashlib.sha256(record).hexdigest(), signed=True,
        signatures=bundle.signatures, note="",
    )
    r = verify_bundle(transplanted, trust_store=store)
    assert r.overall_strict_ok is False and r.integrity_only_ok is False
    assert verify_exit_code(r) == EXIT_MALFORMED

    # 3. A v2 statement relabelled v1: the v1 rule signs the statement, which nobody signed.
    relabelled = _statement(bundle)
    relabelled["format"] = STATEMENT_FORMAT_V1
    r = verify_bundle(_reencode(bundle, relabelled), trust_store=store)
    assert r.signature_ok is False and verify_exit_code(r) == EXIT_SIGNATURE_INVALID

    # 4. A v1 bundle relabelled v2: its signature covers the statement, not a record.
    old = load_bundle(V1 / "smolvla_libero_object.attestation.json")
    promoted = _statement(old)
    promoted["format"] = STATEMENT_FORMAT
    promoted["subject"]["binding"] = SUBJECT_BINDING
    r = verify_bundle(_reencode(old, promoted), trust_store=_store((V1 / "fixture.pub").read_bytes()))
    assert r.signature_ok is False and verify_exit_code(r) == EXIT_SIGNATURE_INVALID

    # 5. A format nobody defined.
    future = _statement(bundle)
    future["format"] = "provael-attestation/v3"
    r = verify_bundle(_reencode(bundle, future), trust_store=store)
    assert "UNSUPPORTED_STATEMENT_FORMAT" in r.codes and verify_exit_code(r) == EXIT_MALFORMED


@pytest.mark.parametrize(
    "payload",
    [
        b"[]",
        b"\xff\xfe\x00not utf-8",
        b"[" * 100_000 + b"]" * 100_000,
        b'{"format": "provael-attestation/v2", "subject": "not an object"}',
        b'{"format": "provael-attestation/v2", "subject": {"digest": "not an object"}}',
        b'{"format": "provael-attestation/v2", "subject": {"name": 7, "digest": {"sha256": 7}}}',
    ],
    ids=["array", "bad-utf8", "deep-nesting", "subject-string", "digest-string", "wrong-types"],
)
def test_a_hostile_payload_is_a_failed_result_never_an_exception(payload: bytes) -> None:
    bundle = AttestationBundle(
        payload=base64.b64encode(payload).decode("ascii"),
        payloadSha256=hashlib.sha256(payload).hexdigest(), signed=True,
        signatures=[AttestationSignature(keyid="0" * 16, sig=base64.b64encode(b"x" * 64).decode())],
        note="",
    )
    r = verify_bundle(bundle, subject_report_bytes=b"{}", expected_subject_name="stub x stub")
    assert r.overall_strict_ok is False and r.integrity_only_ok is False
    assert verify_exit_code(r) == EXIT_MALFORMED
