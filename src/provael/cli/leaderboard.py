# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The `leaderboard` sub-app's commands: `build` and `verify`."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from provael import __version__
from provael.attest import (
    MissingAttestExtraError,
    generate_private_key_pem,
    public_key_pem,
)
from provael.cli._shared import _err, _fail, _git_commit, _out, _render_leaderboard, leaderboard_app
from provael.leaderboard import (
    LEADERBOARD_JSON,
    MAINTAINER_RUN,
    THIRD_PARTY_SUBMISSION,
    UNATTRIBUTED,
    build_leaderboard,
    load_leaderboard,
    verify_leaderboard,
)


@leaderboard_app.command("build")
def leaderboard_build(
    runs: Annotated[
        list[str] | None,
        typer.Option(help="Run dir(s), glob(s), or report.json path(s). Quote globs."),
    ] = None,
    real: Annotated[
        Path | None,
        typer.Option(
            "--real",
            help="Build the public real board from this results dir (requires a non-stub run; "
            "stamps a UTC date, source commit, and an inputs digest).",
        ),
    ] = None,
    sign: Annotated[
        bool, typer.Option("--sign", help="Ed25519-sign the board (needs the `attest` extra).")
    ] = False,
    key: Annotated[
        Path | None,
        typer.Option("--key", help="Ed25519 private-key PEM to sign with. Omit for ephemeral."),
    ] = None,
    out: Annotated[Path, typer.Option(help="Output directory for leaderboard.json.")] = Path(
        "leaderboard/results"
    ),
    submitted_by: Annotated[
        str | None,
        typer.Option(
            "--submitted-by",
            help="Attribute every produced row to this submitter (a GitHub handle or org). "
            "Omit to leave rows unattributed.",
        ),
    ] = None,
    provenance: Annotated[
        str,
        typer.Option(
            "--provenance",
            help=f"How these rows reached the board: {MAINTAINER_RUN} | "
            f"{THIRD_PARTY_SUBMISSION} | {UNATTRIBUTED}.",
        ),
    ] = UNATTRIBUTED,
) -> None:
    """Aggregate report.json files into a ranked leaderboard.json (deterministic; real + signed)."""
    if provenance not in {MAINTAINER_RUN, THIRD_PARTY_SUBMISSION, UNATTRIBUTED}:
        _fail(
            f"unknown --provenance {provenance!r}; expected one of {MAINTAINER_RUN}, "
            f"{THIRD_PARTY_SUBMISSION}, {UNATTRIBUTED}"
        )
        return
    if submitted_by is None and provenance != UNATTRIBUTED:
        _fail(f"--provenance {provenance} needs --submitted-by (who is being attributed?)")
        return
    source = [str(real)] if real is not None else (runs or ["runs"])
    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if real is not None else None
    commit = (_git_commit() or f"v{__version__}") if real is not None else None

    sign_key: bytes | None = None
    ephemeral = False
    if sign:
        try:
            sign_key = key.read_bytes() if key is not None else generate_private_key_pem()
        except MissingAttestExtraError as exc:
            _fail(str(exc))
            return
        ephemeral = key is None

    try:
        out_path, leaderboard = build_leaderboard(
            source, out, generated_at=generated_at, commit=commit,
            sign_key=sign_key, require_real=real is not None,
            submitted_by=submitted_by, provenance=provenance,
        )
    except FileNotFoundError as exc:
        _fail(str(exc))
        return
    except ValueError as exc:  # require_real on a stub-only input
        _fail(str(exc))
        return

    pub_path: Path | None = None
    if sign and ephemeral and sign_key is not None:
        pub_path = out / (LEADERBOARD_JSON.replace(".json", ".pub"))
        pub_path.write_bytes(public_key_pem(sign_key))

    _render_leaderboard(leaderboard)
    if leaderboard.inputs_digest is not None:
        _out.print(f"inputs digest: [dim]{leaderboard.inputs_digest[:16]}…[/dim]")
    if leaderboard.signature is not None:
        _out.print(f"signature: ed25519  keyid {leaderboard.signature.keyid}")
    _out.print(f"\nWrote [cyan]{out_path}[/cyan]"
               + (f" and [cyan]{pub_path}[/cyan]" if pub_path is not None else ""))
    if sign and ephemeral:
        _err.print("[yellow]note:[/yellow] signed with an ephemeral key (integrity, not identity). "
                   "Pass --key to sign with your organisation key.")


@leaderboard_app.command("verify")
def leaderboard_verify(
    board: Annotated[Path, typer.Option("--in", help="Path to a leaderboard.json to verify.")],
    pubkey: Annotated[Path, typer.Option("--pubkey", help="Ed25519 public-key PEM.")],
) -> None:
    """Verify a signed leaderboard offline against a public key."""
    try:
        loaded = load_leaderboard(board)
    except (FileNotFoundError, ValidationError):
        _fail(f"{board} is not a readable leaderboard.json")
        return
    if loaded.signature is None:
        _fail("leaderboard is unsigned — nothing to verify", code=1)
        return
    try:
        ok = verify_leaderboard(loaded, pubkey.read_bytes())
    except MissingAttestExtraError as exc:
        _fail(str(exc))
        return
    if ok:
        _out.print(f"[green]leaderboard OK[/green]  keyid {loaded.signature.keyid}")
    else:
        _fail("leaderboard signature INVALID", code=1)
