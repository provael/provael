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

## Scope notes

- The core installs no GPU/ML stack and makes no network calls; real policies and the LIBERO
  simulator are isolated behind the optional `[lerobot]` extra and a `PROVAEL_INTEGRATION=1`
  gate. Releases publish to PyPI via OIDC trusted publishing (no stored tokens).
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
  verified against the `smolvla_libero` path. Pinning Provael's extra to that fixed release is a
  tracked follow-up (the `smolvla_libero` glue is verified only against `0.5.1` today).

## Scope under the EU Cyber Resilience Act

Regulation (EU) 2024/2847. Article 14 reporting obligations apply from **11 September 2026**;
the Regulation applies in full from 11 December 2027.

Two different questions get asked here, and they have different answers.

### Does the CRA place obligations on this repository?

We have not taken legal advice, and we are not going to publish a scope conclusion we cannot
back. What we can state is the test and the facts.

The test for manufacturer obligations is whether a product with digital elements is made
available on the EU market **in the course of a commercial activity**. Free and open-source
software supplied outside a commercial activity is not in scope.

The facts, as of 5 September 2026:

- `provael` is Apache-2.0 and published free on PyPI and GitHub.
- Paid assessment services are offered against it, at listed prices.
- Nothing has sold. Zero customers, zero revenue.
- There is no legal entity. The project is maintained by one natural person.

Whether offering paid services alongside freely-licensed software makes that software
"supplied in the course of a commercial activity" is the open question, and it is not one this
project gets to settle by asserting an answer in its own security policy.

The **open-source software steward** route is cleaner, because it turns on a checkable fact
rather than a judgement. A steward under Article 3(14) must be a *legal person*. There is no
entity here, so the Article 24 steward obligations — which also begin on 11 September 2026 —
do not attach on that basis. If an entity is incorporated, this section changes with it.

### Does the CRA place obligations on you, if you integrate Provael?

If your product is in CRA scope, the reporting duty is yours. Provael does not discharge it and
does not emit a CRA notification. What it can evidence is one narrow thing: whether a learned
policy behaves unsafely under adversarial instruction or observation, measured with a control
arm. Open a discussion and we will make the handoff explicit rather than leave you guessing.

### What we did instead of a scope claim

Published the disclosure route and the response timings above before the date rather than
after. That is useful whichever way the scope question lands, and being early costs nothing.
