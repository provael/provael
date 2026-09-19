# Security Policy

`provael` is a **defensive, simulation-only** security-research tool. This file covers
reporting vulnerabilities **in the tool itself** (the code, the package, the CI/release
pipeline). For the scope and responsible-**use** expectations of what the tool *does* —
sim-only by default, no physical robots, no real-world-harm payloads — see
[SAFETY.md](SAFETY.md).

## Supported versions

Deliberately version-free: a pinned version line goes stale between releases and silently
tells a reporter their finding is out of scope.

| Version | Supported |
| --- | --- |
| the latest release on [PyPI](https://pypi.org/project/provael/) | ✅ |
| any earlier release | ❌ (please reproduce on the latest) |

Fixes land in the latest release — please reproduce on the current version before reporting.

## Reporting a vulnerability

Please report security issues **privately — do not open a public issue**:

- **Preferred:** open a [GitHub private security advisory](https://github.com/provael/provael/security/advisories/new).
- **Email:** **hello@provael.com** — use this if you can't open an advisory.

<!-- This address must match the Contact: line in the website's .well-known/security.txt. The two
     disagreed (security.txt said hello@provael.com, this file said a gmail address), which leaves a
     researcher choosing between two channels with no way to tell which is monitored — at exactly
     the moment you want the report to arrive somewhere. Both sides now pin the same literal and
     each repo tests its own copy, because they are different runtimes and cannot share a constant:
     tests/test_security_contact.py here, check-facts.mjs there. Change one, change both. -->


Please include reproduction steps, affected version(s), and impact. Good-faith reports are
welcome and credited unless you'd prefer to stay anonymous.

A machine-readable **security.txt** ([RFC 9116](https://www.rfc-editor.org/rfc/rfc9116)) is served at
<https://www.provael.com/.well-known/security.txt>.

## Disclosure timeline

- We aim to **acknowledge within 3 business days**.
- We follow a **90-day coordinated-disclosure window**: we'll confirm the issue, work a fix,
  and coordinate public disclosure (with credit) within 90 days of your report. If a fix ships
  earlier we disclose earlier; if more time is genuinely required we'll agree it with you.

## Regulatory context, stated so you know what we are and are not

One dated statement of the facts, and no scope conclusion this project is not in a position to draw.
As of **19 September 2026**:

- `provael` is Apache-2.0 software, published free on PyPI and GitHub, and maintained by **one
  natural person**. There is **no legal entity** behind it.
- Paid assessment services are offered against it at listed prices. Nothing has sold: zero customers,
  zero revenue.
- **No legal advice has been taken** on whether the EU Cyber Resilience Act (Regulation (EU)
  2024/2847) places manufacturer obligations on this project. The test is whether a product with
  digital elements is made available on the EU market *in the course of a commercial activity*;
  whether offering paid services beside freely-licensed software meets it is the open question, and
  it is counsel's to settle, not this file's. Until it is settled this project claims **neither**
  that it is in scope **nor** that it is exempt.
- The Act's **open-source software steward** route (Article 3(14)) is available only to a *legal
  person*. There is no entity here, so the project is **not** a steward and does not claim the
  steward obligations or their later reporting date. If an entity is incorporated, this section
  changes with it — and counsel is asked before it does.
- What the timetable would mean if the project were in scope: manufacturer reporting under Article 14
  applies from 11 September 2026 (early warning within 24 hours of awareness of an actively exploited
  vulnerability or severe incident, notification within 72 hours, a final report within 14 days of a
  corrective measure being available, or within a month of the 72-hour notification for a severe
  incident, through the ENISA Single Reporting Platform); steward reporting under Article 24(3)
  applies from 11 December 2027, per Article 71(2). Source: [European Commission, Cyber Resilience
  Act reporting obligations](https://digital-strategy.ec.europa.eu/en/policies/cra-reporting),
  verified 12 September 2026.

The disclosure route and the response timings above are published now, whichever way the scope
question lands: a disclosure policy written under deadline pressure is worse than one written
without it, and anyone integrating this harness into a product that *is* in scope needs to know what
they can expect from upstream.

### If you are a manufacturer in scope

If an actively exploited vulnerability in Provael contributes to a reportable incident on your
product, mail **hello@provael.com** with **REPORTABLE** in the subject line. We will treat it as an
acknowledge-within-24-hours case and give you what we know in writing, whether or not we agree the
vulnerability is ours. That is a tighter commitment than the ordinary timeline above, and it is
scoped deliberately: it exists so your 24-hour clock is not spent waiting on us.

We are not your CSIRT and cannot report on your behalf. The notification duty is yours.

## Scope notes

- The core installs no GPU/ML stack and makes no network calls; real policies and the LIBERO
  simulator are isolated behind the optional `[lerobot]` extra and a `PROVAEL_INTEGRATION=1`
  gate. Releases publish to PyPI via OIDC trusted publishing (no stored tokens).

### Network egress, by path

Three paths, three different answers; stating them together is what stops the CPU claim being read
as a claim about the GPU path.

| path | downloads and egress | credentials |
| --- | --- | --- |
| **CPU CLI** (`pip install provael`, the `stub` / `reach` / `humanoid` suites, every export) | none at run time. `pip install` itself reaches PyPI once. | none read; the execution manifest's environment block is an allow-list (`provael.execution.ENV_ALLOWLIST`) and secrets never reach an artifact |
| **optional model loaders** (`[lerobot]`, `[openvla]`, `[openpi]`) | the Hugging Face Hub for the checkpoint the run names (and LeRobot's simulator assets); `[openpi]` opens a websocket to the policy server the operator configures. Nothing else. | a Hub token if the checkpoint is gated, supplied by the operator's own environment; never logged, never written into `report.json` or the manifest |
| **customer execution** (a paid assessment) | the customer's network, under the customer's policy; the isolated-environment variant limits egress to the checkpoint host — see [the procedure](docs/maintainers/private-assessment-procedure.md) | granted and revoked by the customer's access owner |

`provael serve` (the `[hosted]` extra) binds loopback only unless `--allow-remote` is passed, has no
authentication, and is not used for private workloads.
- The tool ships **no real-world-harm payloads** and drives **no physical robots**. Misuse
  against systems you do not own or have permission to test is out of scope and not condoned —
  see [SAFETY.md](SAFETY.md).

## Dependency advisories (supply-chain hygiene, not Provael findings)

These are advisories in **optional dependencies**, tracked here for transparency. They are **not
vulnerabilities in Provael**, and the core install (6 deps, no GPU/ML stack) is unaffected.

- **[CVE-2026-25874](https://nvd.nist.gov/vuln/detail/CVE-2026-25874) — LeRobot unauthenticated
  pickle-deserialization RCE (CVSS 9.8), affecting `lerobot` through `0.5.1`.** The flaw is in
  LeRobot's **async-inference `PolicyServer`**, which `pickle.loads` untrusted payloads over an
  unauthenticated gRPC endpoint (TCP/50051). Provael's optional `[lerobot]` extra pins
  `lerobot==0.5.1` (an affected version), **but Provael never starts that PolicyServer or any gRPC
  endpoint** — it uses LeRobot only for **in-process** policy loading and the LIBERO simulator,
  behind the `[lerobot]` extra and the `PROVAEL_INTEGRATION=1` gate. So the vulnerable code path is
  not reachable through Provael, on CPU or GPU. If you **separately** run LeRobot's async inference,
  follow the upstream advisory (fixed in LeRobot PR #3048, which replaces pickle with
  safetensors + JSON) — require auth/mTLS on the PolicyServer and upgrade once a fixed release is
  verified against the `smolvla_libero` path. **Pinning Provael's extra to that fixed release is a
  bounded, explicit exception, not a forgotten one:** the pin stays at `0.5.1` until a fixed
  release has been validated against the supported checkpoint on a GPU (the adapter's per-step
  rollout was read off this version's evaluator, and 0.6.x moved import paths and raised the torch
  floor — `pyproject.toml` records why), and it moves by a validated run, never by a version-string
  edit. Enabling LeRobot's separate inference server is not a shortcut to that and is not done.

## Scope under the EU Cyber Resilience Act

Regulation (EU) 2024/2847. Article 14 reporting obligations apply from **11 September 2026**;
the Regulation applies in full from 11 December 2027.

Two different questions get asked here, and they have different answers.

### Does the CRA place obligations on this repository?

The facts are the dated statement under *Regulatory context* above, and they are not repeated here
so that the two sections cannot drift apart: no entity, no counsel taken, the steward route
unavailable to a natural person, the manufacturer question open. This project does not settle that
question by asserting an answer in its own security policy.

### Does the CRA place obligations on you, if you integrate Provael?

If your product is in CRA scope, the reporting duty is yours. Provael does not discharge it and
does not emit a CRA notification. What it can evidence is one narrow thing: whether a learned
policy behaves unsafely under adversarial instruction or observation, measured with a control
arm. Open a discussion and we will make the handoff explicit rather than leave you guessing.

### What we did instead of a scope claim

Published the disclosure route and the response timings above before the date rather than
after. That is useful whichever way the scope question lands, and being early costs nothing.
