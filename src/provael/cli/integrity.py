# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The `verify-checkpoint` command: checkpoint integrity, independent of any run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape
from rich.table import Table

from provael.cli._shared import _err, _fail, _out, app
from provael.integrity import (
    INTEGRITY_JSON,
    IntegrityVerdict,
    trust_checkpoint_code,
    verify_checkpoint,
)


@app.command("verify-checkpoint")
def verify_checkpoint_cmd(
    checkpoint: Annotated[
        str, typer.Option("--checkpoint", help="Checkpoint identity (hub id or path) to record.")
    ],
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Local path to the fetched checkpoint to hash, classify and "
                     "read for code it would make lerobot fetch or run."),
    ] = None,
    digest: Annotated[
        str | None,
        typer.Option("--digest", help="Pinned SHA-256 the checkpoint must match. Required unless "
                     "--no-require-digest is passed."),
    ] = None,
    allow_pickle: Annotated[
        bool,
        typer.Option("--allow-pickle/--no-allow-pickle",
                     help="Explicitly opt in to loading pickle-format weights (code execution)."),
    ] = False,
    require_digest: Annotated[
        bool,
        typer.Option("--require-digest/--no-require-digest",
                     help="Fail when no digest is pinned. ON by default — fail closed."),
    ] = True,
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Directory to write checkpoint-integrity.json into."),
    ] = None,
) -> None:
    """Verify a checkpoint BEFORE loading it — a supply-chain control, not an ASR.

    Fails closed: an unpinned digest, an un-opted-in pickle checkpoint, and a checkpoint whose
    config or processor files would make lerobot fetch or run unreviewed code all exit non-zero,
    so a gate that forgets to pin gets a failure rather than a silent pass. The last is the check
    `provael attack` makes before it loads a LeRobot policy, and PROVAEL_TRUST_CHECKPOINT_CODE=1
    accepts it here as there. This produces a verdict, not a rate; it does not reduce attack
    success (see `provael.integrity`).
    """
    record = verify_checkpoint(
        checkpoint, path,
        expected_digest=digest, allow_pickle=allow_pickle, require_pinned_digest=require_digest,
        trust_checkpoint_code=trust_checkpoint_code(),
    )
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        (out / INTEGRITY_JSON).write_text(
            json.dumps(json.loads(record.model_dump_json()), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    table = Table(title="Checkpoint integrity (supply chain, not an ASR)")
    table.add_column("field", style="cyan", no_wrap=True)
    table.add_column("value")
    table.add_row("checkpoint", record.checkpoint)
    table.add_row("EAI", f"{record.eai_id} — model & pipeline poisoning, backdoors & supply chain")
    table.add_row("format", record.checkpoint_format.value)
    shown = f"{record.digest_sha256[:32]}…" if record.digest_sha256 else "—"
    table.add_row("digest", shown)
    table.add_row("digest match", "—" if record.digest_match is None else str(record.digest_match))
    table.add_row("verdict", record.verdict.value)
    _out.print(table)
    for finding in record.findings:
        # Escaped: a finding can quote a string from the checkpoint's own files.
        _err.print(f"[yellow]•[/yellow] {escape(finding)}")

    if record.verdict is IntegrityVerdict.failed:
        _fail("checkpoint integrity FAILED — refusing to load. See the findings above.")
