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

- An attestation signed with a **published, stable project key** — one key an insurer or Notified
  Body can add to its trust store, rather than verifying a different operator key per run — and
  the **compliance report** built on top of it.

  Deliberately not called *authoritative*: a signature proves who signed, never that the signer
  is to be believed. Trust is the verifier's decision, made by adding a key to their own store
  (see :mod:`provael.attest`), and the reference server labels every signature it makes as
  untrusted for exactly that reason.

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
  (the tool + name) is an unregistered mark with a published policy; the standard is separate. See
  [TRADEMARKS.md](https://github.com/provael/provael/blob/main/TRADEMARKS.md).

*Signed by the maintainers, 2026-07-23. Supersedes no prior promise; this is v1.0.*

## The commercial surface

> *Moved here from the repository README on 20 September 2026, when the README was cut to what a new reader needs. The text is as it stood there; links were re-pointed.*


Provael is open core. The CLI, every attack family, calibration, SARIF/OSCAL/ML-BOM, and the
GitHub Action are Apache-2.0, forever. The paid surface is operated work a solo tool can't sign
for: a hosted real-VLA (GPU) transfer run, a leaderboard entry signed with a published, stable
project key (which a verifier may choose to trust — no signature is authoritative on its own), and a
compliance dossier.


The rungs and their prices are stated once, on the website, which computes its entry price from
the rungs rather than restating it: [provael.com/pricing](https://www.provael.com/pricing).
[/pricing](https://www.provael.com/pricing) wins on any disagreement.

A free PV-SCAN of your nearest public checkpoint comes with any of the paid rungs:
[www.provael.com/assessment](https://www.provael.com/assessment). Provael is maintained by one
person, and every commercial page says so before you commit to anything.

Run Provael? Add yourself to [docs/adopters.md](adopters.md) via PR — the self-reported
sign-up sheet, which is empty. The measured distribution figures are a separate page at
[provael.com/adopters](https://provael.com/adopters); an empty sign-up sheet is not an empty user
base.

## The boundary, capability by capability

> *Moved here from the repository README on 20 September 2026, when the README was cut to what a new reader needs. The text is as it stood there; links were re-pointed.*


Provael is **open-core**. Everything needed to red-team a policy and produce evidence is free and
Apache-2.0 — a durable, dated commitment:
**[the open-core promise](open-core-promise.md)** (we will never move a feature from free to paid).
The intended paid surface is a **future operated service**; the in-repo hosted server is an
**experimental reference**, not that service.

| Capability | Free (Apache-2.0) | Future operated service |
| --- | :---: | :---: |
| CLI, all attack families (incl. the `backdoor` EAI03 screen), ASR + 95% CI + benign control | ✅ | |
| `transfer-test`, SARIF, the GitHub Action, the Embodied AI Security Top 10 | ✅ | |
| Measured defenses (`--defense`), `provael mitigation`, the Action's `defense` input | ✅ | |
| `provael certify` incl. the `risk_reduction_measures` dossier section | ✅ | |
| **Local `attest`** (digest-bound; Ed25519-signed with *your* key, verified against *your* trust store) + the leaderboard | ✅ | |
| **Experimental** reference server (`provael serve`, `[hosted]` extra) — disabled by default; operator-key, **untrusted by default** | ✅ | |
| **Authenticated, trusted signing** (a KMS-backed key an assessor can trust) — [production requirements](maintainers/hosted-production-requirements.md) | | ⏳ not built |
| **Assurance-report draft** at scale (a structured evidence export, **not** an insurer / Notified-Body opinion) | | ⏳ not built |

```bash
pip install 'provael[hosted]'
PROVAEL_ENABLE_EXPERIMENTAL_HOSTED=1 provael serve   # experimental reference server (operator-key, untrusted)
```

It binds **loopback only** (`--host 127.0.0.1`); any wider bind needs the explicit `--allow-remote`
opt-in, because the server has no authentication layer. Request bodies are capped at 16 MiB and
refused with 413 rather than buffered, and an internal failure answers with a stable error shape and
a request id — the traceback goes to the operator's log, never the response.

The experimental endpoint is behind a **local feature flag** (`PROVAEL_HOSTED_LICENSE`) that is
**not** authentication and lives **only** on the reference server — it never touches the free core.
The assurance-report draft maps a `provael attest` bundle to the **EU Machinery Regulation
2023/1230** (applies **2027-01-20**), the **AI Act** Annex-I machinery route (applies
**2028-08-02**, deferred from a statutory **2027-08-02** by Regulation (EU) 2026/1744, the Digital
Omnibus, in force 27 Jul 2026), and **ISO 10218:2025** —
see
[docs/compliance/machinery-reg-2027.md](https://github.com/provael/provael/blob/main/docs/compliance/machinery-reg-2027.md).
**Evidence, not certification.**
