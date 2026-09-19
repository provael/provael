# Provael attestation — the signed evidence bundle

> **Independent project. Not affiliated with or endorsed by ISO, the EU, NIST, IEC, OWASP, or
> MITRE. Not legal advice.** An attestation is **evidence, not certification**. It proves that a
> specific Provael run produced specific numbers and that nobody changed them afterwards. It does
> **not** assert that a system is compliant, certified, or safe.

`provael attest` takes the compliance evidence you already get from `report --format compliance`
and turns it into a **tamper-evident, dated, offline-verifiable bundle** — the artifact an auditor,
a customer's security team, or an insurer keeps on file. It re-runs nothing: it reuses
`report.json`, exactly like the compliance export, so the whole path is CPU/stub-runnable.

## What the bundle proves (and what it does not)

| It proves | It does not prove |
| --- | --- |
| The wrapped evidence is **intact** — a SHA-256 digest binds the exact run; any edit breaks it. | That the system is **compliant** or **certified**. It is one input to a conformity file, not the conclusion. |
| **When** it was issued (UTC), against **which ruleset** and **source commit**. | That the numbers **transfer to real hardware**. Provael measures a policy's decision in simulation. |
| **Who** issued it, when signed with a known key (Ed25519, offline-verifiable). | Anything about attacks Provael does not run. Absence of a finding is not proof of safety. |

The honest-scope caveats from [compliance](compliance/index.md) — adversarial-only, evidence-not-
certification, behavioural-not-worst-case — travel *inside* the bundle, because the bundle wraps
the same compliance report verbatim.

## Two layers, so the free core keeps working

1. **Digest layer — always on, standard-library only.** The envelope carries the SHA-256 of the
   canonical statement, and the statement's `subject` carries the SHA-256 of the canonical
   `report.json`. `provael attest --verify` recomputes both with no network and no extra
   dependency. This is integrity, not identity: it proves the evidence was not altered, not who
   produced it.
2. **Signature layer — opt-in, needs the `attest` extra.** With `pip install 'provael[attest]'`
   the envelope is signed with **Ed25519** over the DSSE pre-authentication encoding and verifies
   offline against the bundled public key. Ed25519 is deterministic, so a fixed
   `(report, issued_at, ruleset, commit, key)` yields a byte-identical signature.

The free core stays six light dependencies. `attest --no-sign` produces a digest-only bundle
without the extra; the signed bundle needs the extra, and the CLI says so with a clear install hint.

## Issue and verify

```bash
# Issue against the CPU stub (an ephemeral key is generated and its public half written alongside)
provael attest --policy stub --suite stub --out runs/attest

# Or attest a prior run without re-running it
provael attest --in runs/calib --out runs/attest

# Sign with your organisation key instead of an ephemeral one
provael attest --in runs/calib --key org-ed25519.pem --out runs/attest

# Verify offline — recomputes the digest and checks the signature
provael attest --verify runs/attest/attestation.json --pubkey runs/attest/attestation.pub
```

`attest` writes `attestation.json` (the bundle), `attestation.pub` (the public key, for ephemeral
signing), and `report.compliance.md` (the human-readable evidence) into `--out`.

## What is inside the bundle

A DSSE-style envelope: `payloadType`, a base64 `payload`, its `payloadSha256`, and a `signatures`
array. The payload decodes to a statement with:

- `subject` — `policy x suite` plus the SHA-256 digest of the source `report.json`.
- `predicate` — the **full compliance crosswalk**: the ASR with its 95% Wilson CI, the benign-FPR
  control, the per-EAI breakdown, and every mapped requirement across the EU AI Act, the EU
  Machinery Regulation, ISO 10218:2025, NIST AI 100-2 / AI RMF, and IEC 62443, each with its
  `evidence-present` / `gap` status.
- `transfer` — a per-attack honesty flag: `measured-real-transfer` for a real policy run, or
  `stub-validated-scaffolding` for the stub and for the search-based `optimized` family (whose real
  transfer is GPU-gated).
- `regulatory_clock`, `issued_at`, `commit`, `ruleset`, `tool_version`.

### The deployed policy, not only the checkpoint (schema 6)

Since 0.42.0 the signed `report.json` carries `deployed_policy` beside `model`. `model` is the
checkpoint that was **requested**; `deployed_policy` is what the adapter **resolved at load**: the
concrete policy class, the checkpoint it loaded and that checkpoint's Hub revision (read from the
local cache, never the network), the action unnormaliser it actually applied (mode plus a digest
over the exact statistics), the controller convention (action dimension, chunk length, executed
steps per chunk, clamp, post-processing pipeline), and one digest over all of them. The reason is
Tai (2026, arXiv:2606.03724): the same normalised model output becomes a different physical action
under a different unnormaliser, and on LIBERO-Goal a metadata mismatch takes success from 28/28 to
2/28 with nothing about the checkpoint changed. Two reports that agree on `model` and differ on
`deployed_policy.digest` are reports on two executable policies, and `combine` refuses to pool them.

The field is optional and registered under schema 6, so an older `report.json` still loads and
still digests to its own bytes — an attestation issued before 0.42.0 keeps verifying. Where an
adapter cannot resolve a part it records `null`, never a guess; the three scaffolding adapters
(`openvla`, `openpi`, `groot`) have never run and record nothing.

### The regulatory clock

Factual application dates, carried so the evidence is legible against the calendar buyers care
about. Dates only — no claim of conformity:

- **EU Machinery Regulation (EU) 2023/1230** — applies **20 January 2027**. AI-enabled safety
  functions need a cyber-risk assessment against corruption; this is the operative route for
  AI-enabled robots.
- **EU AI Act (EU) 2024/1689, Annex I machinery** — high-risk obligations were statutory from
  **2 August 2027**. Regulation (EU) 2026/1744 (Digital Omnibus on AI), in the OJ on
  **24 July 2026** and in force **27 July 2026**, moved embedded Annex I application to
  **2 August 2028** — the operative date. Plan against 2028; 2027 is the superseded baseline.
- **ISO 10218-1/-2:2025** — in force since 2025; the revision adds cybersecurity requirements for
  industrial robots, feeding the Machinery Regulation cyber-risk assessment.
- **NIST AI 100-2e2025** — adversarial-ML taxonomy; guidance, not a compliance deadline.

## Standards-aligned assurance profiles (`--profile`)

`--profile <iso-10218-2|iec-62443|insurer>` embeds a standards-aligned **assurance view** in the
signed statement (under `assurance`), mapping the *same* measured ASR + EAI findings + per-family
transfer results onto a framing an assessor or underwriter reads. Nothing is re-measured or
re-scored — it reuses the shipped scoring, the compliance crosswalk, and the insurer report.

- **`iso-10218-2`** — the per-EAI ASR as **ISO 10218-2:2025 cyber-risk-assessment evidence**,
  alongside **Provael's own** mapping to an **IEC 62443 SL2** target (a collaborative-robot cell's
  typical security level, which is an IEC 62443 determination from exposure). ISO 10218 does not
  require IEC 62443: the 2025 revision adds cybersecurity requirements to the extent they apply to
  industrial robot safety, and names IEC 62443 only in its informative Bibliography. Evidence
  *input* to the assessment, not a security-level achievement.
- **`iec-62443`** — the ASR mapped to the applicable IEC 62443 foundational requirements (FR3 System
  Integrity; FR7 Resource Availability for the freeze/availability facet), toward an **SL2** case.
- **`insurer`** — the insurer-consumable summary: the headline ASR with its Wilson CI + benign-FPR,
  plus the honest **which-families-transfer-on-the-real-model** table (per family: ASR, n, 95% Wilson
  CI, benign-FPR, and `measured-real-transfer` vs `stub-validated-scaffolding`).

Every profile also carries a **third-party cert-readiness cross-reference** — which functional- and
AI-safety frameworks (NVIDIA Halos, UL 4600, ISO/PAS 8800, ISO 21448 SOTIF, ISO/IEC TR 5469) this
evidence is an *input* to. This is a readiness cross-reference, **not** a certification and **not**
an endorsement by any of those owners.

A worked example over the real SmolVLA×LIBERO run is committed at
[`results/smolvla_libero_object/attestation.insurer.json`](https://github.com/provael/provael/blob/main/results/smolvla_libero_object/attestation.insurer.json)
(digest-only for byte-reproducibility; `pip install 'provael[attest]'` and drop `--no-sign` to add
the Ed25519 signature):

```bash
provael attest --run results/smolvla_libero_object --profile insurer --out runs/attest
```

## Honest scope

- **Simulation only.** An attestation records a policy's *decision* under attack in sim, not a
  hardware outcome. See [sim-predicts-real](sim-predicts-real.md) for what that does and does not
  transfer.
- **Real-VLA transfer is narrow today.** On a real **SmolVLA × LIBERO** policy, only the
  **instruction** family currently transfers: it redirects the policy **100% (10/10), 95% CI
  [72–100%]** against a **0% benign control** (sim-only, one task, `n = 10`); other instruction
  attacks land lower (roughly 60–80%). Everything else in the catalogue is validated on the
  deterministic CPU stub, where numbers are properties of the fixture, not a real VLA.
- **The `optimized` family is stub-validated scaffolding.** The black-box search is exercised on the
  stub; its real SmolVLA × LIBERO transfer is **GPU-gated and not yet measured**, so the bundle
  flags it `stub-validated-scaffolding` and no cross-model transfer is claimed.
- The out-of-scope list in [SAFETY.md](https://github.com/provael/provael/blob/main/SAFETY.md)
  applies unchanged. Provael tests the AI
  decision layer; it does not test firmware, radios, or mechanical safety.

## Open-core

The CLI, the attacks, the calibrated ASR, SARIF, the GitHub Action, and local `attest` are free and
Apache-2.0 — anyone can self-attest their own runs. The **hosted attestation, signed with a published project key** —
signed with Provael's key and backed by a real-VLA (GPU) transfer run rather than the stub — is the
paid surface. The open tool never gates the local stub path.

*Independent · not legal advice · evidence, not certification. See [compliance](compliance/index.md)
for the full crosswalk.*

## `provael attest`, as the README described it

> *Moved here from the repository README on 20 September 2026, when the README was cut to what a new reader needs. The text is as it stood there; links were re-pointed.*


`attest` wraps that **same** compliance evidence into a **tamper-evident, dated, offline-verifiable
bundle** — the artifact an auditor or insurer keeps on file. It binds the run with a SHA-256 digest,
stamps a UTC date + the crosswalk ruleset + the source commit, records a per-attack transfer-test
status, and wraps it in a DSSE-style envelope:

```bash
uv run provael attest --policy stub --suite stub --out runs/attest   # issue a bundle + public key
# Verification is FAIL-CLOSED. Integrity-only grades just the digest layer:
uv run provael attest --verify runs/attest/attestation.json --integrity-only
# Strict verification needs a trust store — a valid signature from an unknown key is UNTRUSTED:
uv run provael attest --verify runs/attest/attestation.json --trust-store trust.json
```

Verification names the exact property it establishes: an unsigned bundle, or a valid signature from
a key that is not in *your* trust store, is **never** reported as "verified" — integrity, signature
validity, and signer trust are distinct. The digest layer is standard-library and always on.
Cryptographic **Ed25519 signing** rides the optional `provael[attest]` extra (`--no-sign` gives a
digest-only bundle without it). It re-runs nothing and is **evidence, not certification** — see
[docs/attestation.md](https://github.com/provael/provael/blob/main/docs/attestation.md).

`--profile <iso-10218-2|iec-62443|insurer>` embeds a **standards-aligned assurance view**: the per-EAI
ASR as **ISO 10218-2:2025** cyber-risk-assessment evidence routed to **IEC 62443 SL2**, or a
structured **assurance-report draft** (an evidence export for a qualified assessor, *not* an insurer
or conformity-assessment opinion) with the honest *which-families-transfer-on-the-real-model* table
(ASR + 95% Wilson CI + benign-FPR + the `evidence_state` ladder + `measured-real-transfer` vs
`stub-validated-scaffolding`), plus a
third-party cert-readiness cross-reference (NVIDIA Halos / UL 4600 / ISO 21448 / ISO/PAS 8800). A
worked example over the real SmolVLA×LIBERO run is committed at
[`results/smolvla_libero_object/attestation.insurer.json`](https://github.com/provael/provael/blob/main/results/smolvla_libero_object/attestation.insurer.json).

```bash
uv run provael attest --run results/smolvla_libero_object --profile insurer --out runs/attest
```

> **Open-core.** The CLI, attacks, calibrated ASR, SARIF, the GitHub Action and local `attest`
> (including the `--profile` assurance views) are free and Apache-2.0. A **future operated service**
> (an authenticated, KMS-backed signing service with a trusted key) is the intended paid surface; the
> in-repo hosted server is an **experimental reference**, disabled by default, that signs only with
> the operator's own (untrusted-by-default) key. The open tool never gates the local stub path.
