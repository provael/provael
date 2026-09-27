# Attestation v1 fixtures — never regenerate

Real `provael-attestation/v1` bundles, frozen so every later verifier is tested against bundles an
earlier release actually issued. Generated on 28 September 2026 from provael `e95fcdd` (the
attestation, compliance and assurance code identical to the v0.44.0 tag), before the v2 format
(report.json byte binding, signed record) landed:

- `smolvla_libero_object.attestation.json` and `timing_libero_object.attestation.json`: signed,
  over `results/smolvla_libero_object` (no declared schema) and
  `results/timing/libero_object_timing` (schema 5), `issued_at` `2026-09-28T00:00:00Z`, commit
  `attestation-v1-fixture`.
- The key is derived, not stored: `Ed25519PrivateKey.from_private_bytes(sha256(b"provael-attestation-v1-fixture"))`.
  `fixture.pub` is its public key.
- `insurer_unsigned.attestation.json`: a byte copy of the committed v1 digest-only sample
  `results/smolvla_libero_object/attestation.insurer.json` as it stood before v2.

`tests/test_attest_binding.py` pins each file's SHA-256. If one changes, the fixture is no longer
what an old release issued, and the test fails on purpose.
