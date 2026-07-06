# Machinery Regulation 2027 — mapping `provael attest` evidence to conformity

This card maps the evidence in a **`provael attest`** bundle to the instruments that govern
AI-enabled robots and machinery in the EU. It is a companion to
[COMPLIANCE.md](../COMPLIANCE.md) and the [per-persona cards](../crosswalk/README.md).

> **Evidence, not certification. Not legal advice.** This documents what a Provael attestation
> *measures*; it is not a conformity certificate and confers no legal presumption of conformity.
> Dates are the factual application dates carried in `provael.attest.REGULATORY_CLOCK`; confirm
> against the primary text. Provael is an independent project, not affiliated with ISO, the EU,
> NIST, IEC, OWASP, or MITRE.

## Why this matters now

An AI model that chooses a robot's actions is, under the new EU regime, a **safety-related
component of machinery**. Two clocks are running:

- **EU Machinery Regulation (EU) 2023/1230** — **applies 20 January 2027**. It brings AI-enabled
  safety functions and "self-evolving behaviour" in scope, requires protection against corruption of
  safety functions, and routes AI safety components toward third-party conformity assessment.
- **EU AI Act (EU) 2024/1689, Annex I machinery** — high-risk obligations (robustness, accuracy,
  cybersecurity under **Art. 15**) are **statutory from 2 August 2027**. A move to **2 August 2028**
  is *proposed* in the Digital Omnibus but **not yet adopted**; treat 2027 as binding until it is.
- **ISO 10218-1/-2:2025** — **in force since 2025**; the revision adds cybersecurity requirements
  for industrial robots, feeding the Machinery Regulation's cyber-risk assessment.

A Provael attestation is **an input to** that assessment: a dated, digest-bound, signed record of
how a policy behaved under red-team, with every rate carrying its 95% Wilson CI and benign control.

## What a `provael attest` bundle carries → where it maps

| Attestation evidence (in the bundle) | Instrument · date | How it is used |
| --- | --- | --- |
| **Subject digest** — SHA-256 of the canonical `report.json` binding the run | Machinery Reg 2023/1230 · **2027-01-20** | Tamper-evident identity of the tested configuration for the technical file |
| **Per-EAI ASR + 95% Wilson CI + benign-FPR control** (the compliance predicate) | AI Act Annex-I machinery, **Art. 15** · **2027-08-02** (proposed 2028-08-02, not adopted) | Robustness / accuracy evidence against the adversarial threat classes |
| **Per-family transfer-test** (rate + CI + benign control + `real-transfer`/`stub-scaffolding`) | AI Act **Art. 15** robustness | Honest scope: what was measured on a real policy vs the deterministic stub |
| **EAI04 action-integrity + EAI03 backdoor-screen** evidence | ISO 10218-1/-2:2025 (monitored stop / cyber) · **2025** | Action sanity-bounds + supply-chain / backdoor screening inputs |
| **EAI08 authorization / excessive-agency** evidence (self-authorization + scope-escalation rate vs a benign control) | ISO 10218-1/-2:2025 (monitored standstill / least-agency) · **2025** · OWASP **ASI03** | Evidence that guarded actions require an operator token; input to least-privilege / human-in-the-loop controls |
| **Regulatory clock** (factual application dates, stamped in the statement) | all of the above | Names the instrument + date each artifact is measured against — no conformity claimed |
| **Ed25519 signature** (optional; project-key on the operated hosted tier) | Machinery Reg — "prefer signed/attested weights" | An authoritative, offline-verifiable signer for a Notified Body / insurer |

## Honest scope

- Provael measures **redirection / activation in simulation**, a robustness signal — not physical
  harm and not a real-world exploit.
- **Cross-model transfer is only claimed where a real policy was run.** The EAI03 `backdoor`, EAI04
  `action`, and EAI08 `authorization` families are **stub-validated** today; the real SmolVLA ×
  LIBERO path is GPU-gated. The transfer-status label on every row says which is which.
- The **hosted, project-key-signed** insurer / Notified-Body-ready report (see
  [the hosted surface README](https://github.com/provael/provael/blob/main/src/provael/hosted/README.md))
  is the paid tier; the free core produces the same evidence, self-signed or digest-bound.
