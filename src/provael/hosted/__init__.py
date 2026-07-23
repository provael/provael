"""Provael hosted surface — an EXPERIMENTAL, non-production reference implementation.

**Open-core boundary (read this).** Everything a user needs to red-team a policy and produce
evidence is **free and Apache-2.0**: the CLI, every attack family (including the EAI03 ``backdoor``
screen), the ASR + 95% Wilson CI + benign-FPR control, SARIF, the GitHub Action, the Embodied AI
Security Top 10, and **local** ``provael attest`` (digest-bound, optionally Ed25519-signed with your
own key). None of that is gated.

**This module is NOT a production signing service.** It is a *reference* surface for experimenting
with a hosted attestation flow. It does **not** authenticate callers, establish tenant or artifact
ownership, or bind a job — so it must not be operated as an authoritative signing service. It is
**disabled by default**: :func:`provael.hosted.server.create_app` refuses to start unless
``PROVAEL_ENABLE_EXPERIMENTAL_HOSTED=1`` is set, and even then it signs only with the operator's own
key and labels every signature as **untrusted** (a verifier trusts a key by adding it to its own
trust store — see :mod:`provael.attest` — never because Provael served it).

``PROVAEL_HOSTED_LICENSE`` is a **local feature flag**, not authentication or authorization: it
gates the experimental assurance-report-draft endpoint on a single machine and establishes no
caller identity. The requirements for a real operated service (authenticated identity, tenant and
artifact ownership, job binding, KMS/HSM-backed signing, revocation, audit, abuse controls) are
documented in ``docs/maintainers/`` and are deliberately **not** implemented here.

Installed only with the ``[hosted]`` extra (``pip install 'provael[hosted]'``), so the default CPU
install stays lean.
"""

from __future__ import annotations

import os

#: Local feature flag gating the experimental assurance-report-draft endpoint. NOT authentication or
#: authorization — it establishes no caller identity and must never be represented as a credential.
HOSTED_LICENSE_ENV = "PROVAEL_HOSTED_LICENSE"
#: The operated instance's Ed25519 signing-key PEM (path or inline). A signature from it is the
#: OPERATOR'S key — untrusted until a verifier adds it to their trust store; not a Provael identity.
SIGNING_KEY_ENV = "PROVAEL_SIGNING_KEY"
#: Master gate: the experimental hosted server refuses to start unless this is set truthy. Disabled
#: by default because the reference server is not a production-grade, authenticated signing service.
ENABLE_HOSTED_ENV = "PROVAEL_ENABLE_EXPERIMENTAL_HOSTED"


class EntitlementError(RuntimeError):
    """Raised when the experimental assurance-report-draft endpoint is invoked without its flag."""


class HostedDisabledError(RuntimeError):
    """Raised when the experimental hosted server is started without its explicit enable flag."""


def experimental_hosted_enabled() -> bool:
    """Whether the experimental hosted server is explicitly enabled (disabled by default)."""
    return os.environ.get(ENABLE_HOSTED_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def has_entitlement() -> bool:
    """Whether the assurance-draft feature flag is set (non-empty). Not authentication."""
    return bool(os.environ.get(HOSTED_LICENSE_ENV, "").strip())


def require_entitlement() -> str:
    """Return the experimental-endpoint feature flag, or raise :class:`EntitlementError`.

    This is a **local feature flag**, not authentication: it gates the experimental
    assurance-report-draft endpoint on one machine and establishes no caller identity, ownership, or
    authorization. The free core (CLI, all attack families, ASR, SARIF, the GitHub Action, the
    Top-10, and local ``provael attest``) never calls this and is never gated.
    """
    token = os.environ.get(HOSTED_LICENSE_ENV, "").strip()
    if not token:
        raise EntitlementError(
            "This experimental endpoint is behind a local feature flag (it is NOT a paid tier and "
            f"NOT authentication). Set {HOSTED_LICENSE_ENV} to any non-empty value to enable the "
            "assurance-report-draft on this machine. The free core (CLI, all attack families, ASR, "
            "SARIF, the GitHub Action, the Top-10, and local `provael attest`) needs no flag."
        )
    return token


__all__ = [
    "HOSTED_LICENSE_ENV",
    "SIGNING_KEY_ENV",
    "ENABLE_HOSTED_ENV",
    "EntitlementError",
    "HostedDisabledError",
    "experimental_hosted_enabled",
    "has_entitlement",
    "require_entitlement",
]
