"""Reference hosted attestation server (the ``[hosted]`` extra).

A small, self-hostable FastAPI app that turns a posted ``report.json`` into a signed attestation
bundle and (for entitled callers) an insurer / Notified-Body-ready compliance report. The **code is
open and Apache-2.0**; running it yourself yields **self-signed** attestations. The paid tier is the
**operated** instance: it holds the authoritative **project signing key** and grants the
``/insurer-report`` entitlement — see :mod:`provael.hosted`.

``fastapi`` is imported lazily inside :func:`create_app`, so this module imports fine on the CPU
core; calling :func:`create_app` without the extra raises a clear, actionable error rather than an
``ImportError`` traceback. This is a runtime service, so it stamps a wall-clock issuance time — it
is deliberately outside the deterministic ``report.json`` path, which never embeds wall-clock time.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from provael import __version__
from provael.attest import MissingAttestExtraError, to_bundle
from provael.hosted import (
    ENABLE_HOSTED_ENV,
    SIGNING_KEY_ENV,
    EntitlementError,
    HostedDisabledError,
    experimental_hosted_enabled,
    require_entitlement,
)
from provael.hosted.report import build_insurer_report
from provael.types import RunReport


class MissingHostedExtraError(RuntimeError):
    """Raised when the hosted server is started without the ``[hosted]`` extra installed."""


def _issued_at() -> str:
    """Wall-clock issuance timestamp (runtime service — not the deterministic report path)."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _commit() -> str:
    """Source commit the ruleset came from (env override, else the tool version)."""
    return os.environ.get("PROVAEL_COMMIT", "").strip() or f"provael-{__version__}"


def _signing_key_pem() -> bytes | None:
    """The operated instance's project signing key (PEM), from ``PROVAEL_SIGNING_KEY``.

    The value may be a path to a PEM file or the inline PEM itself. ``None`` when unset (a self-host
    with no configured key), in which case signing uses an ephemeral (self-signed) key.
    """
    raw = os.environ.get(SIGNING_KEY_ENV, "").strip()
    if not raw:
        return None
    if raw.startswith("-----BEGIN"):
        return raw.encode("utf-8")
    path = raw
    if os.path.isfile(path):
        with open(path, "rb") as fh:
            return fh.read()
    return None


def create_app() -> Any:
    """Build the FastAPI app. EXPERIMENTAL and disabled by default; requires the ``[hosted]`` extra.

    Refuses to start unless ``PROVAEL_ENABLE_EXPERIMENTAL_HOSTED`` is set — this is a reference
    surface, not a production, authenticated signing service. It does not authenticate callers or
    bind ownership, and every signature it produces is the **operator's own key**, untrusted until a
    verifier adds it to its trust store. No Provael/project authority is ever asserted.

    Routes:
      * ``GET  /healthz``         — liveness + tool version + the experimental boundary.
      * ``POST /attest``          — report.json -> attestation bundle. Default digest-only.
        ``?sign=true`` signs with the operator's OWN key (``PROVAEL_SIGNING_KEY``) and returns its
        public key; it refuses to mint a throwaway ephemeral key whose public half is discarded.
      * ``POST /assurance-report`` — report.json -> a structured assurance-report **draft** (an
        evidence export, NOT an insurer / Notified-Body opinion), behind the
        ``PROVAEL_HOSTED_LICENSE`` local feature flag.
    """
    if not experimental_hosted_enabled():
        raise HostedDisabledError(
            "The Provael hosted server is EXPERIMENTAL and disabled by default: it is a reference "
            "surface, not a production, authenticated signing service (no caller identity, no "
            "ownership binding, no job binding). Set "
            f"{ENABLE_HOSTED_ENV}=1 to run it locally at your own risk."
        )
    try:
        from fastapi import FastAPI, HTTPException, Query
    except ImportError as exc:  # pragma: no cover - exercised via the CLI/import error path
        raise MissingHostedExtraError(
            "The hosted server needs the `hosted` extra: pip install 'provael[hosted]'."
        ) from exc

    app = FastAPI(
        title="Provael hosted attestation (EXPERIMENTAL — not a production signing service)",
        version=__version__,
        summary="Experimental reference server. Signatures are the operator's own key and are "
        "untrusted until a verifier adds them to its own trust store.",
    )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {
            "status": "ok",
            "tool_version": __version__,
            "mode": "experimental",
            "signing": "operator-key-only; untrusted by default",
        }

    @app.post("/attest")
    def attest_endpoint(
        report: RunReport,
        sign: bool = Query(default=False, description="Sign with the OPERATOR's key (needs one)."),
    ) -> dict[str, Any]:
        key_pem = _signing_key_pem()
        if sign and key_pem is None:
            # Never mint a throwaway ephemeral key whose public half we would then discard.
            raise HTTPException(
                status_code=400,
                detail=(
                    "Refusing to sign with a throwaway ephemeral key (its public half would be "
                    "discarded, so nobody could verify it). Configure PROVAEL_SIGNING_KEY with the "
                    "operator's own key, or omit ?sign for a digest-only bundle."
                ),
            )
        try:
            bundle, pub = to_bundle(
                report,
                issued_at=_issued_at(),
                commit=_commit(),
                private_key_pem=key_pem,
                sign=sign,
            )
        except MissingAttestExtraError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "bundle": bundle.model_dump(),
            # the operator's public key travels with the bundle so a caller CAN verify it — it is
            # the operator's key, not a Provael/project authority, and untrusted by default.
            "operator_public_key_pem": pub.decode("utf-8") if pub is not None else None,
            "trust_note": (
                "This signature is the operator's own key, NOT a Provael or project authority. It "
                "is untrusted until you add this key to your own trust store "
                "(provael attest --verify --trust-store)."
            ),
        }

    @app.post("/assurance-report")
    def assurance_report_endpoint(report: RunReport) -> dict[str, Any]:
        try:
            require_entitlement()
        except EntitlementError as exc:
            # 403 Forbidden: a local feature flag is missing (NOT payment, NOT authentication).
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return build_insurer_report(report, issued_at=_issued_at(), commit=_commit())

    return app


__all__ = ["MissingHostedExtraError", "create_app"]
