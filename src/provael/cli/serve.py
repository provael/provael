# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The `serve` command: the operated/hosted surface, gated on the `hosted` extra."""

from __future__ import annotations

from typing import Annotated

import typer

from provael.cli._shared import _fail, _out, app
from provael.hosted.bounds import ALLOW_REMOTE_FLAG, MAX_BODY_BYTES, is_loopback


@app.command()
def serve(
    host: Annotated[
        str, typer.Option(help="Bind host. Loopback only unless --allow-remote is given.")
    ] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535, help="Bind port.")] = 8000,
    allow_remote: Annotated[
        bool,
        typer.Option(
            ALLOW_REMOTE_FLAG,
            help="Permit a bind host other than loopback. The server has no authentication layer, "
            "so a wider bind exposes it to everything that can reach the interface; opt in "
            "only behind something that authenticates.",
        ),
    ] = False,
) -> None:
    """Run the EXPERIMENTAL reference hosted server (needs the `hosted` extra).

    Not a production signing service: it does not authenticate callers or bind ownership, and every
    signature it produces is the operator's OWN key — untrusted until a verifier adds it to a trust
    store. Disabled by default; set `PROVAEL_ENABLE_EXPERIMENTAL_HOSTED=1` to run it. The free CLI,
    attacks, ASR, SARIF, the Action and local `attest` are never gated.

    Serving-layer bounds (issue #229): binds loopback unless `--allow-remote` is given, reads at
    most MAX_BODY_BYTES per request, and never puts a traceback in a response body.
    """
    # Checked before anything is imported or started: an open port is the failure mode, and the
    # refusal must not depend on which extras are installed.
    if not is_loopback(host) and not allow_remote:
        _fail(
            f"Refusing to bind {host!r}: this server has no authentication layer, so any host "
            f"other than loopback (127.0.0.1 / ::1 / localhost) exposes it to the whole "
            f"interface. Pass {ALLOW_REMOTE_FLAG} to opt in, behind something that authenticates."
        )
        return
    try:
        import uvicorn

        from provael.hosted import HostedDisabledError
        from provael.hosted.server import MissingHostedExtraError, create_app
    except ImportError:
        _fail("The hosted server needs the `hosted` extra: pip install 'provael[hosted]'.")
        return
    try:
        application = create_app()
    except (MissingHostedExtraError, HostedDisabledError) as exc:
        _fail(str(exc))
        return
    exposure = "loopback only" if is_loopback(host) else f"REMOTE bind ({ALLOW_REMOTE_FLAG})"
    _out.print(
        f"Provael hosted (EXPERIMENTAL, operator-key-only) on "
        f"[cyan]http://{host}:{port}[/cyan]  —  {exposure}, request bodies capped at "
        f"{MAX_BODY_BYTES // (1024 * 1024)} MiB  —  Ctrl-C to stop"
    )
    uvicorn.run(application, host=host, port=port)
