# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The `study` sub-app's commands: `cross-arch` and `eai04`."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape

from provael.cli._shared import _out, study_app
from provael.studies.cross_arch import (
    build_eai04_study,
    build_study,
    render_eai04_table,
    render_table,
    write_eai04_study,
    write_study,
)


@study_app.command("cross-arch")
def study_cross_arch(
    episodes: Annotated[int, typer.Option(help="Episodes per attack (distinct seeds).")] = 10,
    seed: Annotated[int, typer.Option(help="Base random seed.")] = 0,
    out: Annotated[
        Path | None, typer.Option(help="Write summary.json + per-architecture RunReports here.")
    ] = None,
) -> None:
    """Cross-architecture transfer study: the instruction/visual/injection battery vs SmolVLA + pi0.

    Runs the deterministic CPU-stub battery (no GPU/network) and prints the per-(family x
    architecture) ASR with a 95% Wilson CI and the benign-FPR control. SmolVLA and pi0 stay
    'pending' unless run on the gated real path (PROVAEL_INTEGRATION=1 + the `lerobot` / `openpi`
    extra). Reuses the shipped runner + scoring — no ASR is reimplemented.
    """
    summary, reports = build_study(episodes=episodes, seed=seed)
    render_table(summary, _out)
    if out is not None:
        write_study(summary, reports, out)
        _out.print(f"[green]Wrote[/green] {escape(str(out))}/ (summary.json + per-arch reports)")


@study_app.command("eai04")
def study_eai04(
    episodes: Annotated[int, typer.Option(help="Episodes per attack (distinct seeds).")] = 10,
    seed: Annotated[int, typer.Option(help="Base random seed.")] = 0,
    out: Annotated[
        Path | None, typer.Option(help="Write summary.json + the reference RunReport here.")
    ] = None,
) -> None:
    """EAI04 action-space transfer study: action/action_space vectors × {reach, SmolVLA, pi0}.

    Runs the deterministic CPU ``reach`` keep-out reference (ASR + 95% Wilson CI + benign-FPR +
    Succ-But-Unsafe + BH-FDR + preliminary) and marks the real SmolVLA/pi0 LIBERO legs
    NOT-APPLICABLE: these out-of-band-directive attacks do not reach a real VLA, so no real-policy
    EAI04 transfer is obtainable through this mechanism. Reuses the runner + scoring — no ASR
    reimplemented, no second harness.
    """
    summary, reports = build_eai04_study(episodes=episodes, seed=seed)
    render_eai04_table(summary, _out)
    if out is not None:
        write_eai04_study(summary, reports, out)
        _out.print(f"[green]Wrote[/green] {escape(str(out))}/ (summary.json + reference report)")
