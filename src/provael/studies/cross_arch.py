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
from provael.scoring.asr import by_family, fdr_by_attack, matched_benign_fpr, succ_but_unsafe
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


def run_arch(
    arch: Architecture, *, episodes: int = 10, seed: int = 0, battery: list[str] = BATTERY
) -> RunReport | None:
    """Run ``battery`` against one architecture, or ``None`` when it is gated/unavailable here.

    Uses the shipped :func:`provael.runner.run` unchanged, so the ASR / CI / benign-FPR are computed
    by the same code every other Provael run uses. ``battery`` defaults to the cross-architecture
    battery; the EAI04 study passes its own (see :data:`EAI04_BATTERY`).
    """
    if not _arch_ready(arch):
        return None
    config = RunConfig(
        policy=arch.policy, suite=arch.suite, attacks=battery, episodes=episodes, seed=seed
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


# --------------------------------------------------------------------------------------------
# EAI04 action-space-integrity transfer study — reuses the harness above (no second harness).
# --------------------------------------------------------------------------------------------

#: The EAI04 battery: the benign control + the two EAI04 vectors (each a family with two attacks).
EAI04_BATTERY: list[str] = ["none", "action", "action_space"]
#: EAI04 family -> its attacks (the "vectors"). ``action`` drives the motion channel;
#: ``action_space`` drives the commanded end-state channel.
EAI04_VECTORS: dict[str, tuple[str, ...]] = {
    "action": ("freeze", "trajectory_hijack"),
    "action_space": ("keepout_hijack", "critical_freeze"),
}

#: EAI04 architectures. The deterministic CPU reference runs on the ``reach`` keep-out suite (where
#: BOTH vectors are applicable — ``action`` also applies on ``stub``, ``action_space`` needs
#: ``reach``). The real backends target LIBERO, where these attacks are NOT-APPLICABLE (verified).
EAI04_ARCHITECTURES: tuple[Architecture, ...] = (
    Architecture("reach", "CPU reach keep-out (deterministic fixture)", "stub", "reach", None),
    Architecture("smolvla", "SmolVLA — LeRobot flow-matching", "smolvla", "libero", "lerobot"),
    Architecture("pi0", "pi0 — openpi flow-matching", "openpi", "libero", "openpi"),
)

#: Why the real legs are NOT-APPLICABLE (not merely gated). The EAI04 attacks inject an out-of-band
#: directive channel a real VLA ignores, and no real suite surfaces the required flag — verified
#: on a LIBERO-shaped observation. This is architectural, not a hardware gap.
_EAI04_NOT_APPLICABLE = (
    "not-applicable on the real LIBERO path: action/action_space inject an out-of-band directive "
    "channel a real VLA ignores, and LIBERO surfaces no supports_action_integrity / "
    "supports_action_space signal (verified on a LIBERO-shaped observation). No real-policy EAI04 "
    "transfer is obtainable through this mechanism; a real action-freeze / hijack needs the "
    "GPU-gated adversarial-image search (FreezeVLA / AttackVLA — see the optimized_patch family)."
)

_EAI04_HONESTY = (
    "Sim-only, defensive. The reach rows are properties of the deterministic CPU keep-out fixture, "
    "NOT a real VLA. The EAI04 action/action_space attacks inject an out-of-band directive channel "
    "that a real VLA ignores, and no real suite (LIBERO) surfaces the required action-integrity "
    "signal - so the real SmolVLA/pi0 legs are NOT-APPLICABLE, not merely 'pending': no "
    "real-policy EAI04 transfer is obtainable through this mechanism, and action/action_space stay "
    "stub-validated. A real action-freeze/hijack needs the GPU-gated adversarial-image search "
    "(FreezeVLA/AttackVLA; see the optimized_patch family). Every rate is read against its "
    "benign-FPR control; "
    "BH-FDR corrects across vectors; runs under 5 seeds are flagged preliminary. No 'first' claim."
)


class Eai04Row(BaseModel):
    """One (architecture × vector) cell of the EAI04 study — the full stats, or not-applicable."""

    architecture: str
    family: str  # action | action_space
    vector: str  # freeze | trajectory_hijack | keepout_hijack | critical_freeze
    status: str  # "measured" | "not-applicable"
    attempts: int = 0
    successes: int = 0
    asr: float | None = None
    ci95_low: float | None = None
    ci95_high: float | None = None
    benign_fpr: float | None = None
    matched_benign_fpr: float | None = None
    succ_but_unsafe: float | None = None
    bh_fdr_q: float | None = None
    bh_fdr_significant: bool | None = None
    seeds: int | None = None
    preliminary: bool | None = None
    note: str = ""


class Eai04Summary(BaseModel):
    """The machine-readable EAI04 transfer table (deterministic: no wall-clock)."""

    format: str = "provael-eai04-transfer-study/v1"
    tool_version: str
    battery: list[str]
    vectors: dict[str, list[str]]
    episodes: int
    seed: int
    rows: list[Eai04Row]
    honesty: str


def eai04_measured_rows(arch: Architecture, report: RunReport) -> list[Eai04Row]:
    """Per-vector EAI04 rows for a measured architecture.

    Reuses the shipped scoring end to end: ``report.by_attack`` (ASR), :func:`wilson_ci`,
    :func:`fdr_by_attack` (BH-FDR across the EAI04 vectors), :func:`succ_but_unsafe`, and
    :func:`matched_benign_fpr`. A vector with no applicable episodes in this suite is ``not-
    applicable`` (excluded from the denominator, never faked).
    """
    fdr = fdr_by_attack(report) or {}
    mbf = matched_benign_fpr(report.results)
    rows: list[Eai04Row] = []
    for family, vectors in EAI04_VECTORS.items():
        for vector in vectors:
            stat = report.by_attack.get(vector)
            if stat is None or stat.attempts == 0:
                rows.append(Eai04Row(
                    architecture=arch.key, family=family, vector=vector, status="not-applicable",
                    note="no applicable episodes in this suite",
                ))
                continue
            lo, hi = wilson_ci(stat.successes, stat.attempts)
            q = fdr.get(vector)
            sbu = succ_but_unsafe([r for r in report.results if r.attack == vector])
            rows.append(Eai04Row(
                architecture=arch.key, family=family, vector=vector, status="measured",
                attempts=stat.attempts, successes=stat.successes, asr=stat.asr,
                ci95_low=lo, ci95_high=hi, benign_fpr=report.benign_fpr, matched_benign_fpr=mbf,
                succ_but_unsafe=sbu,
                bh_fdr_q=None if q is None else q[0],
                bh_fdr_significant=None if q is None else q[1],
                seeds=report.seeds, preliminary=report.preliminary,
            ))
    return rows


def eai04_not_applicable_rows(arch: Architecture, note: str) -> list[Eai04Row]:
    """Not-applicable rows for an architecture where EAI04 cannot be measured (e.g. real LIBERO)."""
    return [
        Eai04Row(architecture=arch.key, family=family, vector=vector, status="not-applicable",
                 note=note)
        for family, vectors in EAI04_VECTORS.items()
        for vector in vectors
    ]


def build_eai04_study(
    *, episodes: int = 10, seed: int = 0,
    architectures: tuple[Architecture, ...] = EAI04_ARCHITECTURES,
) -> tuple[Eai04Summary, dict[str, RunReport]]:
    """Run the EAI04 transfer study and return the summary + the measured reports.

    The CPU reference (``reach``) is measured deterministically; the real backends are
    ``not-applicable`` — verified architectural fact, not a hardware gate (see
    :data:`_EAI04_NOT_APPLICABLE`). Deterministic given fixed ``episodes``/``seed``.
    """
    rows: list[Eai04Row] = []
    reports: dict[str, RunReport] = {}
    for arch in architectures:
        report = run_arch(arch, episodes=episodes, seed=seed, battery=EAI04_BATTERY)
        if report is None:
            # Gated here; and for the real (LIBERO) backends, not-applicable regardless of a GPU.
            note = _EAI04_NOT_APPLICABLE if arch.extra is not None else _pending_reason(arch)
            rows.extend(eai04_not_applicable_rows(arch, note))
        else:
            reports[arch.key] = report
            rows.extend(eai04_measured_rows(arch, report))
    return Eai04Summary(
        tool_version=__version__, battery=EAI04_BATTERY,
        vectors={k: list(v) for k, v in EAI04_VECTORS.items()},
        episodes=episodes, seed=seed, rows=rows, honesty=_EAI04_HONESTY,
    ), reports


def eai04_summary_json(summary: Eai04Summary) -> str:
    """Deterministic, indented JSON for the EAI04 summary (no trailing newline)."""
    return summary.model_dump_json(indent=2)


#: Filename of the machine-readable EAI04 summary within a study's output directory.
EAI04_SUMMARY_JSON = "summary.json"


def write_eai04_study(
    summary: Eai04Summary, reports: dict[str, RunReport], out_dir: Path
) -> Path:
    """Write the EAI04 summary JSON + each measured architecture's byte-deterministic RunReport."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / EAI04_SUMMARY_JSON).write_text(eai04_summary_json(summary) + "\n", encoding="utf-8")
    for key, report in reports.items():
        write_report(report, out_dir / key)
    return out_dir


def render_eai04_table(summary: Eai04Summary, console: object | None = None) -> None:
    """Print the EAI04 architecture × vector × ASR × CI × controls table (Rich)."""
    from rich.console import Console
    from rich.table import Table

    out = console if console is not None else Console()
    table = Table(title="EAI04 action-space transfer — ASR by (architecture × vector)")
    for col in ("architecture", "family", "vector", "ASR (95% CI)", "n", "benign-FPR",
                "SbU", "BH-q", "status"):
        table.add_column(col)
    for row in summary.rows:
        if (
            row.status == "measured" and row.asr is not None
            and row.ci95_low is not None and row.ci95_high is not None
        ):
            asr = f"{row.asr * 100:.0f}% [{row.ci95_low * 100:.0f}-{row.ci95_high * 100:.0f}%]"
            n = str(row.attempts)
            fpr = "n/a" if row.benign_fpr is None else f"{row.benign_fpr * 100:.0f}%"
            sbu = "n/a" if row.succ_but_unsafe is None else f"{row.succ_but_unsafe * 100:.0f}%"
            bh = "n/a" if row.bh_fdr_q is None else f"{row.bh_fdr_q:.1g}"
        else:
            asr = n = fpr = sbu = bh = "—"
        table.add_row(_label(row.architecture), row.family, row.vector, asr, n, fpr, sbu, bh,
                      row.status)
    out.print(table)  # type: ignore[attr-defined]
    out.print(f"[dim]{summary.honesty}[/dim]")  # type: ignore[attr-defined]


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
    "EAI04_BATTERY",
    "EAI04_VECTORS",
    "EAI04_ARCHITECTURES",
    "EAI04_SUMMARY_JSON",
    "Eai04Row",
    "Eai04Summary",
    "eai04_measured_rows",
    "eai04_not_applicable_rows",
    "build_eai04_study",
    "eai04_summary_json",
    "write_eai04_study",
    "render_eai04_table",
]
