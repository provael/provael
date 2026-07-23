# Migration: report schema v2 & deprecated terms

The evidence-integrity pass added report **schema version 2** and renamed several APIs so a claim
names exactly what it establishes. Everything is **additive and backward-readable**: old
`report.json` files still load, and no legacy value is silently reinterpreted.

## `RunReport` — schema 1 → 2

| schema 1 (legacy) | schema 2 | Notes |
|---|---|---|
| `asr` = headline | `asr` = **all-episode** observed-unsafe rate | Relabelled, value unchanged. The headline is now `adversarial_asr`. |
| — | `adversarial_asr` / `adversarial_attempts` / `adversarial_successes` | Benign control excluded by role. Recomputed from `results` for a legacy report — never reinterpreting `asr`. |
| — | `roles` | attack → `benign-control` / `adversarial-treatment`. |
| — | `evidence_state` | The evidence ladder. Absent ⇒ read as `legacy-unverified`. |
| — | `schema_version` | `1` if absent. |

`RunReport.adversarial_headline()` returns the honest `(rate, successes, attempts)` for any report,
recomputing from `results` when the stored fields are absent. `scoring.asr.reconcile(report)` recovers
the full breakdown (adversarial-only, all-episode, per-attack N/A) from a legacy artifact without
editing it.

## Deprecated / renamed APIs

| Old | New | Why |
|---|---|---|
| `VerifyResult.ok` (True for unsigned) | `overall_strict_ok` / `integrity_only_ok` | Fail-closed. `ok` is now a deprecated alias for `overall_strict_ok`. |
| `transfer_status` (2-state) | `evidence_state` (`provael.evidence`) | Finer-grained; `transfer_status` retained as a derived, deprecated view. |
| `/insurer-report` | `/assurance-report` | Structured evidence **draft**, not an insurer/Notified-Body opinion. |
| `MOTION_SLICE = (1, 4)` | `ActionSchema` (`provael.scoring.action_schema`) | The suite declares its real action layout; incompatible ⇒ N/A, not a guessed slice. |
| binary pass/fail | `ReleaseVerdict` (`provael.verdict`) | `incomplete` / `fail` / `conditional` / `pass`. |
| `PROVAEL_HOSTED_LICENSE` "paid tier" | local **feature flag** | Not authentication; the hosted server is experimental and disabled by default. |

## Attestation goldens

Adding fields to `RunReport` grows its canonical serialization, so the **derived** attestation golden
(`results/smolvla_libero_object/attestation.insurer.json`) is regenerated from the unchanged source
`report.json`. The source result JSON is never edited to match a new schema. Regenerate a derived
bundle explicitly; the legacy artifact reads `evidence_state: legacy-unverified` and a public
evidence manifest (`provael evidence-manifest`) surfaces the honest split.

## Verifying a bundle after the change

```bash
# Strict (default): fails closed unless the signer is in your trust store
provael attest --verify bundle.json --trust-store trust.json

# Integrity-only: grades just the digest layer — never printed as plain "verified"
provael attest --verify bundle.json --integrity-only
```
