"""Persist and present a :class:`RunReport`.

Writes a machine-readable ``report.json`` and a human-readable ``report.md``, loads
a report back from disk (for the ``report`` CLI command), and renders a Rich table
plus the headline ASR line to a console.

``report.json`` is produced via pydantic's ``model_dump_json`` with sorted keys and
stable formatting so two runs of the same config yield byte-identical files.
"""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

from provael.calibration import wilson_ci
from provael.eai import CATALOG
from provael.types import ASRStat, RunReport

REPORT_JSON = "report.json"
REPORT_MD = "report.md"


def _asr_with_ci(stat: ASRStat) -> str:
    """ASR as a percentage with its 95% Wilson CI, e.g. ``80.0% [44–97%]`` (``N/A`` if empty)."""
    if stat.attempts == 0:
        return "N/A"
    lo, hi = wilson_ci(stat.successes, stat.attempts)
    return f"{100.0 * stat.asr:.1f}% [{100.0 * lo:.0f}–{100.0 * hi:.0f}%]"


def _stat_row(name: str, stat: ASRStat) -> tuple[str, str, str, str]:
    return (name, _asr_with_ci(stat), str(stat.successes), str(stat.attempts))


def _fmt_ci(ci: tuple[float, float] | None) -> str:
    """Format a proportion interval as ``44–97%`` (``N/A`` when absent)."""
    if ci is None:
        return "N/A"
    lo, hi = ci
    return f"{100.0 * lo:.0f}–{100.0 * hi:.0f}%"


def _eai_id(report: RunReport, attack: str) -> str | None:
    """The EAI risk id this attack maps to, or ``None`` (e.g. the baseline control)."""
    tag = report.eai.get(attack)
    return tag.id if tag is not None else None


def _eai_cell_md(report: RunReport, attack: str) -> str:
    """Markdown EAI cell: a deep link into the Top-10 doc, or an em-dash."""
    eid = _eai_id(report, attack)
    if eid is None:
        return "—"
    risk = CATALOG.get(eid)
    return f"[{eid}]({risk.help_uri})" if risk is not None else eid


def to_json(report: RunReport) -> str:
    """Serialise a report to a stable, indented JSON string."""
    # Round-trip through Python so keys are sorted -> deterministic byte output.
    data = json.loads(report.model_dump_json())
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def to_markdown(report: RunReport) -> str:
    """Render a report as a Markdown document."""
    lines: list[str] = []
    lines.append("# Provael — VLA Red-Team Report")
    lines.append("")
    lines.append(f"**{report.headline()}**")
    lines.append("")
    lines.append("## Run")
    lines.append("")
    lines.append("| field | value |")
    lines.append("| --- | --- |")
    lines.append(f"| tool version | `{report.tool_version}` |")
    lines.append(f"| policy | `{report.policy}` |")
    lines.append(f"| suite | `{report.suite}` |")
    lines.append(f"| attacks | {', '.join(f'`{a}`' for a in report.attacks)} |")
    lines.append(f"| tasks | {', '.join(f'`{t}`' for t in report.tasks)} |")
    lines.append(f"| episodes / pair | {report.episodes} |")
    lines.append(f"| horizon | {report.horizon} |")
    lines.append(f"| base seed | {report.seed} |")
    if report.accelerator is not None or report.precision is not None:
        acc = report.accelerator or "unspecified"
        prec = report.precision or "unspecified"
        lines.append(f"| accelerator / precision | `{acc}` / `{prec}` |")
    lines.append(f"| attempts | {report.attempts} |")
    lines.append(f"| successes | {report.successes} |")
    lines.append(f"| ASR 95% CI (Wilson) | {_fmt_ci(report.ci95)} |")
    lines.append(f"| ASR anytime-valid CI | {_fmt_ci(report.anytime_ci)} |")
    lines.append(f"| seeds | {report.seeds}{' (preliminary, <5)' if report.preliminary else ''} |")
    lines.append(f"| stochastic | {report.stochastic} |")
    lines.append(f"| ASR std (per-seed) | {100.0 * report.asr_std:.1f}% |")
    predicate = "calibrated" if report.calibrated else "default (uncalibrated)"
    lines.append(f"| predicate | {predicate} |")
    if report.benign_fpr is not None:
        lines.append(f"| benign baseline FPR | {100.0 * report.benign_fpr:.1f}% |")
    if report.matched_benign_fpr is not None:
        lines.append(f"| matched-benign FPR | {100.0 * report.matched_benign_fpr:.1f}% |")
    if report.stochastic:
        lines.append("")
        lines.append(
            "> Real-policy ASR is **seeded but model-stochastic** — reported as "
            "mean ± per-seed std, not byte-deterministic (only the stub is)."
        )
    if report.calibrated:
        lines.append("")
        lines.append(
            "> **Calibrated predicate.** Each ASR is a **calibrated redirection rate** with a "
            "95% Wilson CI; read it against the benign baseline FPR above — the live control "
            "(the `none` row's rate). Per-task calibration detail is in `report.json`."
        )
    if report.preliminary:
        lines.append("")
        lines.append(
            f"> **Preliminary — {report.seeds} seed(s) (<5).** Treat the headline as indicative, "
            "not a banked number: LIBERO shows a ~13.7 pp cross-seed spread. The **anytime-valid "
            "CI** stays honest under this seed-by-seed peeking (Wilson assumes one fixed n); a "
            "banked headline needs >=5 seeds."
        )
    lines.append("")
    lines.append("## ASR by attack")
    lines.append("")
    lines.append("| attack | EAI | ASR | successes | attempts |")
    lines.append("| --- | --- | --- | --- | --- |")
    for name, stat in report.by_attack.items():
        a, asr, s, n = _stat_row(name, stat)
        lines.append(f"| {a} | {_eai_cell_md(report, name)} | {asr} | {s} | {n} |")
    lines.append("")
    lines.append("## ASR by task")
    lines.append("")
    lines.append("| task | ASR | successes | attempts |")
    lines.append("| --- | --- | --- | --- |")
    for name, stat in report.by_task.items():
        a, asr, s, n = _stat_row(name, stat)
        lines.append(f"| {a} | {asr} | {s} | {n} |")
    lines.append("")
    lines.append("## Sample adversarial instructions")
    lines.append("")
    seen: set[str] = set()
    for r in report.results:
        if r.attack not in seen:
            seen.add(r.attack)
            lines.append(f"- **{r.attack}**: {r.adversarial_instruction!r}")
    lines.append("")
    return "\n".join(lines)


def write_report(report: RunReport, out_dir: Path) -> tuple[Path, Path]:
    """Write ``report.json`` and ``report.md`` into ``out_dir`` (created if needed).

    Returns the ``(json_path, md_path)`` written.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / REPORT_JSON
    md_path = out_dir / REPORT_MD
    json_path.write_text(to_json(report), encoding="utf-8")
    md_path.write_text(to_markdown(report), encoding="utf-8")
    return json_path, md_path


def load_report(in_dir: Path) -> RunReport:
    """Load a :class:`RunReport` from ``<in_dir>/report.json``.

    Raises:
        FileNotFoundError: if no ``report.json`` exists in ``in_dir``.
    """
    json_path = in_dir / REPORT_JSON if in_dir.is_dir() else in_dir
    if not json_path.exists():
        raise FileNotFoundError(f"no report.json found at {json_path}")
    return RunReport.model_validate_json(json_path.read_text(encoding="utf-8"))


def build_summary_table(report: RunReport) -> Table:
    """Build a Rich table summarising ASR by attack."""
    table = Table(title="Provael — ASR by attack", title_style="bold")
    table.add_column("attack", style="cyan", no_wrap=True)
    table.add_column("EAI", style="magenta", no_wrap=True)
    table.add_column("ASR", justify="right", style="bold red")
    table.add_column("successes", justify="right")
    table.add_column("attempts", justify="right")
    for name, stat in report.by_attack.items():
        a, asr, s, n = _stat_row(name, stat)
        table.add_row(a, _eai_id(report, name) or "—", asr, s, n)
    return table


def render_summary(report: RunReport, console: Console | None = None) -> None:
    """Print the ASR table and the headline ASR line to ``console`` (or a fresh one)."""
    console = console or Console()
    console.print(build_summary_table(report))
    console.print(f"[bold]{report.headline()}[/bold]")
    fpr = "n/a" if report.benign_fpr is None else f"{100.0 * report.benign_fpr:.1f}%"
    if report.calibrated:
        console.print(
            f"[magenta]calibrated predicate[/magenta] — ASR is a redirection rate (95% CI shown); "
            f"benign baseline FPR {fpr}"
        )
    elif report.benign_fpr is not None:
        console.print(f"predicate: default (uncalibrated) · benign baseline FPR {fpr}")


__all__ = [
    "REPORT_JSON",
    "REPORT_MD",
    "to_json",
    "to_markdown",
    "write_report",
    "load_report",
    "build_summary_table",
    "render_summary",
]
