# Security Policy

`provael` is a **defensive, simulation-only** security-research tool. For the scope and
responsible-use expectations of what the tool *does*, see [SAFETY.md](SAFETY.md). This file
covers reporting vulnerabilities **in the tool itself**.

## Supported versions

The latest released `0.2.x` on [PyPI](https://pypi.org/project/provael/) receives fixes.
Older versions are not maintained.

## Reporting a vulnerability

Please report security issues **privately** — do not open a public issue.

- Preferred: open a [GitHub private security advisory](https://github.com/provael/provael/security/advisories/new).
- We aim to acknowledge within a few days and to coordinate a fix and disclosure timeline
  with you.

When reporting, please include reproduction steps, affected version(s), and impact. Reports
made in good faith are welcome and credited (unless you prefer otherwise).

## Scope notes

- The core installs no GPU/ML stack and makes no network calls; real policies and the LIBERO
  simulator are isolated behind the optional `[lerobot]` extra and a `PROVAEL_INTEGRATION=1`
  gate.
- The tool ships **no real-world-harm payloads** and drives **no physical robots**. Misuse
  against systems you do not own or have permission to test is out of scope and not condoned.
