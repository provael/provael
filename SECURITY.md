# Security Policy

`provael` is a **defensive, simulation-only** security-research tool. This file covers
reporting vulnerabilities **in the tool itself** (the code, the package, the CI/release
pipeline). For the scope and responsible-**use** expectations of what the tool *does* —
sim-only by default, no physical robots, no real-world-harm payloads — see
[SAFETY.md](SAFETY.md).

## Supported versions

| Version | Supported |
| --- | --- |
| latest `0.16.x` on [PyPI](https://pypi.org/project/provael/) | ✅ |
| `< 0.16.0` | ❌ |

Fixes land in the latest release — please reproduce on the current version before reporting.

## Reporting a vulnerability

Please report security issues **privately — do not open a public issue**:

- **Preferred:** open a [GitHub private security advisory](https://github.com/provael/provael/security/advisories/new).
- **Email:** **getprovael@gmail.com** — use this if you can't open an advisory.

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
