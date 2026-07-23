# The Provael™ open-core promise

**Version 1.0 — 2026-07-23.** A durable stewardship pledge. This page states, plainly and with a
date, what will **always** be free in Provael™ and what the single paid surface is — so a team can
adopt the open core without worrying it will be hollowed out later. It complements the technical
[open-core boundary](https://github.com/provael/provael/blob/main/README.md#open-core-boundary-free-vs-paid)
in the README; where the two ever disagree, **the more generous reading of this promise wins.**

## Always free — Apache-2.0, forever

Everything you need to red-team a VLA policy and produce evidence is free, open-source
(Apache-2.0), and runs on a plain CPU with no account and no key:

- The **CLI** and the entire engine (policies, suites, runner, report).
- **Every attack family** — including the EAI03 `backdoor` objective-decoupled trigger *screen*.
  New attack families we ship are free too.
- The **ASR + 95% Wilson CI + benign false-positive control + clean-task-success control**, and
  **predicate calibration**.
- The per-family **transfer-test** (rate + CI + benign-FPR + honest `real-transfer` /
  `stub-validated` label).
- Every **evidence export**: SARIF, OSCAL, AVID, the CycloneDX ML-BOM, and the compliance crosswalk.
- The **GitHub Action** for CI gating.
- The **Embodied AI Security Top 10** — a separate, CC-BY-SA community document (see below).
- **Local `attest`** — a digest-bound, Ed25519-signed attestation **signed with *your own* key**,
  including the `--profile` assurance views.
- The **self-hosted reference server** (`provael serve`, the `[hosted]` extra) producing
  *self-signed* attestations.

## The single paid surface

Exactly one thing is sold, and it is an **operated service, not code**:

- The **authoritative, project-key-signed attestation** — one key an insurer or Notified Body can
  trust — and the **insurer / Notified-Body-ready compliance report** built on top of it.

The paid entitlement check lives **only** on the operated service; it never touches the free core,
and the open tool never gates the local stub or real-model path.

## The commitment

- **We will never move a feature from free to paid.** A capability that is free today stays free.
- The free core will **never be crippled** to sell the paid surface — no artificial limits, no
  "community edition" nerfs, no telemetry required to run it.
- If a future paid capability is added, it will be **additive** (a new operated service), and this
  page will be updated with a new dated version — the free list above only ever grows.
- The **Embodied AI Security Top 10** is a community standard under **CC-BY-SA**, kept deliberately
  **unbranded and donatable** — it is not a Provael™ product and will never be paywalled. Provael™
  (the tool + name) is a trademark; the standard is separate. See
  [TRADEMARKS](https://github.com/provael/provael/blob/main/README.md#trademarks).

*Signed by the maintainers, 2026-07-23. Supersedes no prior promise; this is v1.0.*
