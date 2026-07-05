"""Provael hosted surface — the open-core paid tier (v0.10.0).

**Open-core boundary (read this).** Everything a user needs to red-team a policy and produce
evidence is **free and Apache-2.0**: the CLI, every attack family (including the EAI03 ``backdoor``
screen), the ASR + 95% Wilson CI + benign-FPR control, SARIF, the GitHub Action, the Embodied AI
Security Top 10, and **local** ``provael attest`` (digest-bound, optionally Ed25519-signed with your
own key). None of that is gated.

This module is the *reference implementation* of the hosted surface. The **code is open and
self-hostable** — anyone can run :func:`provael.hosted.server.create_app` and get **self-signed**
attestations. What is sold is the **operated service**, not the code:

* the **authoritative, project-key signature** (an insurer / Notified-Body can trust one key), and
* the **insurer / Notified-Body-ready compliance report**
  (:func:`provael.hosted.report.build_insurer_report`) and a curated/managed targeted-backdoor
  screen.

Those paid surfaces are guarded by :func:`require_entitlement`, which checks the
``PROVAEL_HOSTED_LICENSE`` environment variable. The gate lives ONLY on the operated endpoints —
it never touches the free core. Installed only with the ``[hosted]`` extra
(``pip install 'provael[hosted]'``), so the default CPU install stays lean.
"""

from __future__ import annotations

import os

#: Environment variable carrying the paid hosted-tier entitlement token.
HOSTED_LICENSE_ENV = "PROVAEL_HOSTED_LICENSE"
#: Environment variable carrying the operated instance's Ed25519 signing-key PEM (path or inline).
SIGNING_KEY_ENV = "PROVAEL_SIGNING_KEY"


class EntitlementError(RuntimeError):
    """Raised when a paid hosted-tier surface is invoked without a valid entitlement."""


def has_entitlement() -> bool:
    """Whether a hosted-tier entitlement token is configured (non-empty license env var)."""
    return bool(os.environ.get(HOSTED_LICENSE_ENV, "").strip())


def require_entitlement() -> str:
    """Return the hosted-tier entitlement token, or raise :class:`EntitlementError`.

    Guards ONLY the paid, operated surfaces (the project-key-signed insurer report). The free core —
    the CLI, all attack families, ASR, SARIF, the GitHub Action, the Top-10, and local ``attest`` —
    never calls this and is never gated.
    """
    token = os.environ.get(HOSTED_LICENSE_ENV, "").strip()
    if not token:
        raise EntitlementError(
            "This is the paid Provael hosted tier: the operated, project-key-signed insurer / "
            "Notified-Body-ready attestation. The free core (CLI, all attack families incl. the "
            "backdoor screen, ASR, SARIF, the GitHub Action, the Top-10, and local `provael "
            f"attest`) needs no license. Set {HOSTED_LICENSE_ENV} to use the hosted surface, or "
            "self-host the reference server (`provael serve`) for self-signed attestations."
        )
    return token


__all__ = [
    "HOSTED_LICENSE_ENV",
    "SIGNING_KEY_ENV",
    "EntitlementError",
    "has_entitlement",
    "require_entitlement",
]
