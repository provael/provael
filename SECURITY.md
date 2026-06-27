# Security Policy

`provael` is a **defensive, simulation-only** security-research tool. This file covers
reporting vulnerabilities **in the tool itself** (the code, the package, the CI/release
pipeline). For the scope and responsible-**use** expectations of what the tool *does* —
sim-only by default, no physical robots, no real-world-harm payloads — see
[SAFETY.md](SAFETY.md).

## Supported versions

| Version | Supported |
| --- | --- |
| latest `0.3.x` on [PyPI](https://pypi.org/project/provael/) | ✅ |
| `< 0.3.0` | ❌ |

Fixes land in the latest release — please reproduce on the current version before reporting.

## Reporting a vulnerability

Please report security issues **privately — do not open a public issue**:

- **Preferred:** open a [GitHub private security advisory](https://github.com/provael/provael/security/advisories/new).
- **Email:** **getprovael@gmail.com** — use this if you can't open an advisory.

Please include reproduction steps, affected version(s), and impact. Good-faith reports are
welcome and credited unless you'd prefer to stay anonymous.

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
