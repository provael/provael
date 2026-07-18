"""Cross-architecture transfer study: one attack battery vs many VLA architectures.

**Question.** Do the *same* templated attacks move different VLA architectures, or is a redirection
an artifact of one codebase's glue? This runs the shared **instruction / visual / injection**
battery (plus the benign ``none`` control) against multiple backends through the *same* runner and
scoring path, and reports **per-(family × architecture)** ASR with a **95% Wilson CI** and the
**benign-FPR** control the repo already computes. It REUSES :mod:`provael.runner` and
:mod:`provael.scoring.asr` — no ASR is reimplemented here.

**Defensive, sim-only.** No real-robot/hardware code, no real-world-harm payloads: the battery
perturbs only the observation/instruction a policy receives in simulation.

**What runs where.**

* **CPU stub** (default) — the deterministic :class:`~provael.policies.stub.StubPolicy` ×
  :class:`~provael.suites.stub.StubSuite`. Byte-deterministic, no GPU/network, CI-green. These rows
  are properties of the fixture, **not** a real VLA — no cross-architecture transfer is claimed from
  them.
* **SmolVLA** (LeRobot) and **π0** (openpi) — gated behind ``PROVAEL_INTEGRATION=1`` **and** the
  ``[lerobot]`` / ``[openpi]`` extra (and, for π0, a running openpi policy server). Because
  ``[openpi]`` and ``[lerobot]`` pin conflicting numpy majors, each real architecture is run in its
  **own environment** and the per-architecture reports are merged offline by :func:`merge_reports`.
  Off the gated path these rows are honestly marked ``pending``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from provael import __version__
from provael.calibration import wilson_ci
from provael.config import RunConfig
from provael.policies.registry import policy_is_ready
from provael.report import write_report
from provael.runner import run
from provael.scoring.asr import by_family, matched_benign_fpr
from provael.types import RunReport

#: The shared battery: the benign control + the three transfer-tested templated families.
BATTERY: list[str] = ["none", "instruction", "visual", "injection"]
#: The families reported as rows (the ``none`` control becomes the benign-FPR, not a row).
FAMILIES: list[str] = ["instruction", "visual", "injection"]

_INTEGRATION = os.environ.get("PROVAEL_INTEGRATION") == "1"


@dataclass(frozen=True)
class Architecture:
    """A target backend: a registry policy + the suite it is red-teamed in, and its gating extra."""

    key: str
    label: str
    policy: str
    suite: str
    extra: str | None  # optional extra required for the real path; None => CPU-ready (stub)


#: The architectures under study. ``stub`` always runs (CPU, deterministic); the two real
#: flow-matching backends are gated. SmolVLA is π0-as-ported-into-LeRobot's cousin; ``openpi`` is π0
#: as served by Physical Intelligence's own stack — a genuine cross-*framework* pair.
ARCHITECTURES: tuple[Architecture, ...] = (
    Architecture("stub", "CPU stub (deterministic fixture)", "stub", "stub", None),
    Architecture("smolvla", "SmolVLA — LeRobot flow-matching", "smolvla", "libero", "lerobot"),
    Architecture("pi0", "pi0 — openpi flow-matching", "openpi", "libero", "openpi"),
)

_HONESTY = (
    "Sim-only, defensive. CPU-stub rows are properties of the deterministic fixture, NOT a real "
    "VLA - no cross-architecture transfer is claimed from them. SmolVLA and pi0 rows are measured "
    "only on the gated real path (PROVAEL_INTEGRATION=1 + the extra, and for pi0 a running openpi "
    "server), run in separate envs and merged offline; until then they are 'pending'. Every rate "
    "is read against its benign-FPR control. No 'first' claim is made."
)


class FamilyStat(BaseModel):
    """One (architecture × family) cell: ASR + its Wilson CI + the benign control, or pending."""

    architecture: str
    family: str
    status: str  # "measured" | "pending" | "not-applicable"
    attempts: int = 0
    successes: int = 0
    asr: float | None = None
    ci95_low: float | None = None
    ci95_high: float | None = None
    benign_fpr: float | None = None
    matched_benign_fpr: float | None = None
    note: str = ""


class StudySummary(BaseModel):
    """The machine-readable cross-architecture table (deterministic: no wall-clock)."""

    format: str = "provael-cross-arch-study/v1"
    tool_version: str
    battery: list[str]
    families: list[str]
    episodes: int
    seed: int
    rows: list[FamilyStat]
    honesty: str


def _arch_ready(arch: Architecture) -> bool:
    """Whether ``arch`` can be measured in this environment (stub always; real => gated)."""
    if arch.extra is None:
        return True
    return _INTEGRATION and policy_is_ready(arch.policy)


def _pending_reason(arch: Architecture) -> str:
    server = " + a running openpi server" if arch.key == "pi0" else " (GPU)"
    return f"gated: needs provael[{arch.extra}] + PROVAEL_INTEGRATION=1{server}"


def run_arch(arch: Architecture, *, episodes: int = 10, seed: int = 0) -> RunReport | None:
    """Run the battery against one architecture, or ``None`` when it is gated/unavailable here.

    Uses the shipped :func:`provael.runner.run` unchanged, so the ASR / CI / benign-FPR are computed
    by the same code every other Provael run uses.
    """
    if not _arch_ready(arch):
        return None
    config = RunConfig(
        policy=arch.policy, suite=arch.suite, attacks=BATTERY, episodes=episodes, seed=seed
    )
    return run(config)


def family_rows(arch: Architecture, report: RunReport) -> list[FamilyStat]:
    """Per-family rows for a measured architecture (ASR + Wilson CI + benign controls)."""
    fam = by_family(report.results)
    mbf = matched_benign_fpr(report.results)
    rows: list[FamilyStat] = []
    for family in FAMILIES:
        stat = fam.get(family)
        if stat is None or stat.attempts == 0:
            rows.append(FamilyStat(
                architecture=arch.key, family=family, status="not-applicable",
                note="no applicable episodes in this suite",
            ))
            continue
        lo, hi = wilson_ci(stat.successes, stat.attempts)
        rows.append(FamilyStat(
            architecture=arch.key, family=family, status="measured",
            attempts=stat.attempts, successes=stat.successes, asr=stat.asr,
            ci95_low=lo, ci95_high=hi,
            benign_fpr=report.benign_fpr, matched_benign_fpr=mbf,
        ))
    return rows


def pending_rows(arch: Architecture) -> list[FamilyStat]:
    """Placeholder rows for an architecture not measured in this environment."""
    reason = _pending_reason(arch)
    return [
        FamilyStat(architecture=arch.key, family=family, status="pending", note=reason)
        for family in FAMILIES
    ]


def build_study(
    *, episodes: int = 10, seed: int = 0,
    architectures: tuple[Architecture, ...] = ARCHITECTURES,
) -> tuple[StudySummary, dict[str, RunReport]]:
    """Run the study across ``architectures`` and return the summary + the measured reports.

    On CPU only ``stub`` is measured; the gated backends yield ``pending`` rows. Deterministic given
    fixed ``episodes``/``seed`` (the stub run is byte-stable and the summary carries no timestamp).
    """
    rows: list[FamilyStat] = []
    reports: dict[str, RunReport] = {}
    for arch in architectures:
        report = run_arch(arch, episodes=episodes, seed=seed)
        if report is None:
            rows.extend(pending_rows(arch))
        else:
            reports[arch.key] = report
            rows.extend(family_rows(arch, report))
    summary = StudySummary(
        tool_version=__version__, battery=BATTERY, families=FAMILIES,
        episodes=episodes, seed=seed, rows=rows, honesty=_HONESTY,
    )
    return summary, reports


def merge_reports(
    reports: dict[str, RunReport], *, episodes: int = 10, seed: int = 0
) -> StudySummary:
    """Build the summary from per-architecture reports produced in separate (gated) environments.

    Because ``[openpi]`` and ``[lerobot]`` cannot co-install, the real SmolVLA and π0 runs happen in
    different envs; run each with :func:`run_arch` there, persist the report, then combine them.
    Architectures with no supplied report are marked ``pending``.
    """
    rows: list[FamilyStat] = []
    for arch in ARCHITECTURES:
        report = reports.get(arch.key)
        rows.extend(family_rows(arch, report) if report is not None else pending_rows(arch))
    return StudySummary(
        tool_version=__version__, battery=BATTERY, families=FAMILIES,
        episodes=episodes, seed=seed, rows=rows, honesty=_HONESTY,
    )


def summary_json(summary: StudySummary) -> str:
    """Deterministic, indented JSON for the summary table (no trailing newline)."""
    return summary.model_dump_json(indent=2)


def _label(key: str) -> str:
    return next((a.label for a in ARCHITECTURES if a.key == key), key)


def render_table(summary: StudySummary, console: object | None = None) -> None:
    """Print the architecture × family × ASR × CI × benign-FPR table (Rich)."""
    from rich.console import Console
    from rich.table import Table

    out = console if console is not None else Console()
    table = Table(title="Cross-architecture transfer — ASR by (architecture × family)")
    table.add_column("architecture", style="cyan", no_wrap=True)
    table.add_column("family")
    table.add_column("ASR (95% CI)", justify="right")
    table.add_column("n", justify="right")
    table.add_column("benign-FPR", justify="right")
    table.add_column("status")
    for row in summary.rows:
        if (
            row.status == "measured"
            and row.asr is not None
            and row.ci95_low is not None
            and row.ci95_high is not None
        ):
            asr = f"{row.asr * 100:.1f}% [{row.ci95_low * 100:.0f}-{row.ci95_high * 100:.0f}%]"
            n = str(row.attempts)
            fpr = "n/a" if row.benign_fpr is None else f"{row.benign_fpr * 100:.1f}%"
        else:
            asr = n = fpr = "—"
        table.add_row(_label(row.architecture), row.family, asr, n, fpr, row.status)
    out.print(table)  # type: ignore[attr-defined]
    out.print(f"[dim]{summary.honesty}[/dim]")  # type: ignore[attr-defined]


#: Filename of the machine-readable summary within a study's output directory.
SUMMARY_JSON = "summary.json"


def write_study(
    summary: StudySummary, reports: dict[str, RunReport], out_dir: Path
) -> Path:
    """Write the summary JSON + each measured architecture's byte-deterministic RunReport.

    Layout: ``<out_dir>/summary.json`` and ``<out_dir>/<arch>/report.{json,md}`` (via
    :func:`provael.report.write_report`). Returns ``out_dir``.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / SUMMARY_JSON).write_text(summary_json(summary) + "\n", encoding="utf-8")
    for key, report in reports.items():
        write_report(report, out_dir / key)
    return out_dir


__all__ = [
    "BATTERY",
    "FAMILIES",
    "SUMMARY_JSON",
    "Architecture",
    "ARCHITECTURES",
    "FamilyStat",
    "StudySummary",
    "run_arch",
    "family_rows",
    "pending_rows",
    "build_study",
    "merge_reports",
    "summary_json",
    "render_table",
    "write_study",
]
