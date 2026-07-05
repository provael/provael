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
from provael.hosted import SIGNING_KEY_ENV, EntitlementError, require_entitlement
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
    """Build the FastAPI app. Requires the ``[hosted]`` extra.

    Routes:
      * ``GET  /healthz``        — liveness + tool version (free).
      * ``POST /attest``         — report.json -> signed attestation bundle. ``?sign=false``
        (default) is a digest-only bundle that needs no extra; ``?sign=true`` needs ``[attest]``.
        Self-hosters get a self-signed bundle; the operated instance signs with the project key.
      * ``POST /insurer-report`` — report.json -> insurer / Notified-Body-ready report. **Paid:**
        guarded by :func:`provael.hosted.require_entitlement`.
    """
    try:
        from fastapi import FastAPI, HTTPException, Query
    except ImportError as exc:  # pragma: no cover - exercised via the CLI/import error path
        raise MissingHostedExtraError(
            "The hosted server needs the `hosted` extra: pip install 'provael[hosted]'."
        ) from exc

    app = FastAPI(
        title="Provael hosted attestation",
        version=__version__,
        summary="Signed ASR + compliance attestation for VLA policy red-teams (reference server).",
    )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "tool_version": __version__}

    @app.post("/attest")
    def attest_endpoint(
        report: RunReport,
        sign: bool = Query(default=False, description="Ed25519-sign (needs the [attest] extra)."),
    ) -> dict[str, Any]:
        try:
            bundle, _pub = to_bundle(
                report,
                issued_at=_issued_at(),
                commit=_commit(),
                private_key_pem=_signing_key_pem(),
                sign=sign,
            )
        except MissingAttestExtraError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result: dict[str, Any] = bundle.model_dump()
        return result

    @app.post("/insurer-report")
    def insurer_report_endpoint(report: RunReport) -> dict[str, Any]:
        try:
            require_entitlement()
        except EntitlementError as exc:
            # 402 Payment Required: this is the paid, operated surface.
            raise HTTPException(status_code=402, detail=str(exc)) from exc
        return build_insurer_report(report, issued_at=_issued_at(), commit=_commit())

    return app


__all__ = ["MissingHostedExtraError", "create_app"]
