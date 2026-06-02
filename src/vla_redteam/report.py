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

from vla_redteam.types import ASRStat, RunReport

REPORT_JSON = "report.json"
REPORT_MD = "report.md"


def _stat_row(name: str, stat: ASRStat) -> tuple[str, str, str, str]:
    return (name, f"{100.0 * stat.asr:.1f}%", str(stat.successes), str(stat.attempts))


def to_json(report: RunReport) -> str:
    """Serialise a report to a stable, indented JSON string."""
    # Round-trip through Python so keys are sorted -> deterministic byte output.
    data = json.loads(report.model_dump_json())
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def to_markdown(report: RunReport) -> str:
    """Render a report as a Markdown document."""
    lines: list[str] = []
    lines.append("# RoboPwn — VLA Red-Team Report")
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
    lines.append(f"| attempts | {report.attempts} |")
    lines.append(f"| successes | {report.successes} |")
    lines.append("")
    lines.append("## ASR by attack")
    lines.append("")
    lines.append("| attack | ASR | successes | attempts |")
    lines.append("| --- | --- | --- | --- |")
    for name, stat in report.by_attack.items():
        a, asr, s, n = _stat_row(name, stat)
        lines.append(f"| {a} | {asr} | {s} | {n} |")
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
    table = Table(title="RoboPwn — ASR by attack", title_style="bold")
    table.add_column("attack", style="cyan", no_wrap=True)
    table.add_column("ASR", justify="right", style="bold red")
    table.add_column("successes", justify="right")
    table.add_column("attempts", justify="right")
    for name, stat in report.by_attack.items():
        a, asr, s, n = _stat_row(name, stat)
        table.add_row(a, asr, s, n)
    return table


def render_summary(report: RunReport, console: Console | None = None) -> None:
    """Print the ASR table and the headline ASR line to ``console`` (or a fresh one)."""
    console = console or Console()
    console.print(build_summary_table(report))
    console.print(f"[bold]{report.headline()}[/bold]")


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
