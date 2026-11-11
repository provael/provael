# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Persist and present a :class:`RunReport`.

Writes a machine-readable ``report.json`` and a human-readable ``report.md``, loads
a report back from disk (for the ``report`` CLI command), and renders a Rich table
plus the headline ASR line to a console.

``report.json`` is produced via pydantic's ``model_dump_json`` with sorted keys and
stable formatting so two runs of the same config yield byte-identical files. It is written as
bytes, with LF line endings on every OS, because an attestation binds those bytes
(:class:`ReportArtifact`).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table

from provael.calibration import describe_calibration, wilson_ci
from provael.eai import CATALOG
from provael.endpoints import PHYSICAL_HAZARD
from provael.evidence import evidence_state_of
from provael.scoring.asr import (
    arm_episodes,
    benign_control,
    endpoint_by_attack,
    fdr_by_attack,
    report_rates,
    semantic_role,
)
from provael.scoring.safety_cost import (
    FIXED_HORIZON,
    QUADRANT_KEYS,
    TASK_SUCCESS_UNMEASURED,
    UNSAFE_SUCCESS,
    cumulative_cost,
    exposure_unobservable,
    quadrant_counts,
    risk_exposure_time,
    unsafe_success_rate,
    unsafe_success_unobservable,
)
from provael.types import ASRStat, RateStat, ReportRates, RunReport
from provael.verdict import ReleaseDecision, acceptance_line, release_verdict

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


def _endpoint_cell(stat: ASRStat | None) -> str:
    """``events/measured (rate%) [Wilson]`` for an endpoint, or ``n/a`` where nothing measured."""
    if stat is None or stat.attempts == 0:
        return "n/a"
    lo, hi = wilson_ci(stat.successes, stat.attempts)
    return (
        f"{stat.successes}/{stat.attempts} ({100.0 * stat.asr:.1f}%) "
        f"[{100.0 * lo:.0f}–{100.0 * hi:.0f}%]"
    )


def _interval_of(stat: RateStat | None) -> tuple[float, float] | None:
    """A RateStat's interval as ``(low, high)``, or None for an N/A slice."""
    if stat is None or stat.interval is None:
        return None
    return (stat.interval.low, stat.interval.high)


def _unjudged_note(report: RunReport, stat: RateStat | None) -> str:
    """`` · unjudged N`` beside a rate on a schema-9 report; nothing on an earlier one.

    An earlier report recorded no verdict, so a 0 printed for it would be a claim nobody made.
    """
    if report.schema_version < 9 or stat is None:
        return ""
    return f" · unjudged {stat.n_unjudged}"


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


def report_json_bytes(report: RunReport) -> bytes:
    """The exact bytes :func:`write_report` writes as ``report.json`` for ``report``."""
    return to_json(report).encode("utf-8")


def report_json_path(path: Path) -> Path:
    """``<path>/report.json`` for a run directory, ``path`` itself for a file."""
    return path / REPORT_JSON if path.is_dir() else path


@dataclass(frozen=True)
class ReportArtifact:
    """A ``report.json`` as a verifier will hold it: its exact bytes, and the report they parse to.

    An attestation binds ``sha256(raw)``, so the bytes travel with the parsed report instead of
    being re-derived from it. Re-serialising a parsed report does not reproduce a file another
    release wrote: a field that release did not emit comes back as ``null``, and a report written
    with ``write_text`` on Windows has CRLF line endings. Anything that attests a file that already
    exists therefore starts from :meth:`read`, never from :func:`load_report`.
    """

    raw: bytes
    report: RunReport

    @classmethod
    def from_bytes(cls, raw: bytes) -> ReportArtifact:
        """Parse ``raw`` as a report (pydantic's ``ValidationError`` when it is not one)."""
        return cls(raw=raw, report=RunReport.model_validate_json(raw))

    @classmethod
    def read(cls, path: Path) -> ReportArtifact:
        """Read ``<path>/report.json``, or ``path`` itself when it is a file.

        Raises:
            FileNotFoundError: if there is no such file.
        """
        json_path = report_json_path(path)
        if not json_path.exists():
            raise FileNotFoundError(f"no report.json found at {json_path}")
        return cls.from_bytes(json_path.read_bytes())

    @classmethod
    def of(cls, report: RunReport | ReportArtifact) -> ReportArtifact:
        """``report`` as an artifact: an artifact as it is, a bare report as the bytes
        :func:`write_report` writes for it (which are a file's bytes only if this release wrote
        that file)."""
        if isinstance(report, ReportArtifact):
            return report
        return cls(raw=report_json_bytes(report), report=report)

    @property
    def sha256(self) -> str:
        """Hex SHA-256 of :attr:`raw`: what ``sha256sum report.json`` prints."""
        return hashlib.sha256(self.raw).hexdigest()


def _rate_cell(stat: RateStat | None, missing: str) -> str:
    """``k/n (p%) [lo–hi%]`` for a RateStat, or ``missing`` where there is none or no trial."""
    if stat is None or stat.rate is None:
        return missing
    return (
        f"{stat.successes}/{stat.trials} ({100.0 * stat.rate:.1f}%) "
        f"[{_fmt_ci(_interval_of(stat))}]"
    )


def ended_cell(terminations: dict[str, int] | None, schema_version: int) -> str:
    """How an arm's episodes ended, as ``"horizon 3, task_success 2"``, or why it cannot say."""
    if terminations is None:
        return f"not recorded (report schema {schema_version}; recorded from schema 9)"
    return ", ".join(f"{name} {count}" for name, count in terminations.items())


def _per_arm_outcomes(report: RunReport, rates: ReportRates) -> list[str]:
    """Per arm: task success, mean steps and how its episodes ended (P2.1).

    An unsafe rate says how often an arm left the envelope and nothing about what the policy did
    otherwise: an arm can sit at the floor because the policy stopped doing the task and ran out
    the horizon. These three columns say which.
    """
    outcomes = arm_episodes(report.results)
    roles = {r.attack: semantic_role(r) for r in report.results} | report.roles
    lines = [
        "## Task success and how episodes ended, per arm",
        "",
        "| attack | role | task success | mean steps | how episodes ended |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name in report.by_attack:
        arm = outcomes.get(name)
        role = roles.get(name, "adversarial-treatment")
        if arm is None:
            lines.append(f"| {name} | {role} | N/A | N/A | not applicable on this suite |")
            continue
        success = _rate_cell(
            rates.task_success_by_attack.get(name), "N/A (no task-success signal)"
        )
        steps = f"{arm.mean_steps:.1f}" if arm.mean_steps is not None else "N/A"
        ended = ended_cell(arm.terminations, report.schema_version)
        lines.append(f"| {name} | {role} | {success} | {steps} | {ended} |")
    lines += [
        "",
        "> Task success counts the episodes that carry the suite's task-success signal; mean "
        "steps and how episodes ended count every applicable episode of the arm.",
        "",
    ]
    return lines


def _pp(value: float) -> str:
    """A difference in percentage points with its sign, ``+82.0`` / ``-3.3`` / ``0.0``."""
    points = round(100.0 * value, 1)
    return "0.0" if points == 0 else f"{points:+.1f}"


def _paired_difference_section(rates: ReportRates) -> list[str]:
    """Each paired arm's rate minus the benign arm's, with Newcombe's paired interval (P2.4).

    Two Wilson intervals side by side are not an interval for their difference, and the pairs are
    paired: the McNemar test reads the same table, and this bounds what it tests.
    """
    if not rates.paired_difference:
        return []
    lines = [
        "## Paired difference against the benign arm",
        "",
        "| attack | pairs (n) | discordant (b–c) | difference | 95% interval |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, diff in rates.paired_difference.items():
        lines.append(
            f"| {name} | {diff.pairs} | {diff.attack_only}–{diff.benign_only} | "
            f"{_pp(diff.estimate)} pp | [{_pp(diff.interval.low)}, {_pp(diff.interval.high)}] pp |"
        )
    method = next(iter(rates.paired_difference.values())).interval.method
    lines += [
        "",
        f"> Each arm's unsafe rate minus its benign twins' over the (task, seed) cells both ran, "
        f"interval by `{method}` (Newcombe 1998, Statistics in Medicine 17:2635). The pairs share "
        "a task and a seed, not necessarily a starting scene (E-2026-19); the intervals are not "
        "adjusted for multiplicity.",
        "",
    ]
    return lines


def _competence_section(report: RunReport) -> list[str]:
    """The competence pre-run, when the run asked for one (``--competence-check``, P2.2)."""
    check = report.competence
    if check is None:
        return []
    lines = [
        "## Competence check",
        "",
        f"> {check.episodes_per_task} benign episode(s) per task ran before the arms, at seeds "
        "after the run's own, with the run's defense in place and under its termination mode. "
        f"A task whose task success fell below {100.0 * check.floor:.0f}% had its adversarial "
        "arms refused; the benign arm and "
        "the harmless-variation controls still ran on it. These episodes enter no rate.",
        "",
        "| task | task success (pre-run) | decision | arms refused |",
        "| --- | --- | --- | --- |",
    ]
    for task, row in check.by_task.items():
        decision = "admitted" if row.admitted else "**refused**"
        refused = ", ".join(row.refused) or "—"
        lines.append(
            f"| {task} | {_rate_cell(row.task_success, 'N/A')} | {decision} | {refused} |"
        )
    lines.append("")
    return lines


def to_markdown(
    report: RunReport, decision: ReleaseDecision | None = None, *, termination: str | None = None
) -> str:
    """Render a report as a Markdown document.

    ``decision`` is the release decision the caller made (under a named protocol, or not assessed);
    it is derived here only when the caller has none, so this page, the scorecard, the SARIF and
    the manifest of one run can never disagree about its verdict. ``termination`` defaults to the
    report's own ``termination_mode``, which decides whether Succ-But-Unsafe, CC and RET print as
    N/A (E-2026-21): they do on a first-event run, exactly as before, and not on a fixed-horizon
    one.
    """
    decision = decision if decision is not None else release_verdict(report)
    termination = termination if termination is not None else report.termination_mode
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
    if report.termination_mode == FIXED_HORIZON:
        # Printed only for the new mode, so a first-event report renders exactly as it did.
        lines.append(
            "| episode termination | fixed horizon: every episode ran to the horizon, past its "
            "first envelope exit and past task success |"
        )
    lines.append(f"| base seed | {report.seed} |")
    if report.accelerator is not None or report.precision is not None:
        acc = report.accelerator or "unspecified"
        prec = report.precision or "unspecified"
        lines.append(f"| accelerator / precision | `{acc}` / `{prec}` |")
    adv_rate, adv_s, adv_n = report.adversarial_headline()
    adv_pct = "N/A" if adv_n == 0 else f"{100.0 * adv_rate:.1f}%"
    # Every interval comes from the one resolver (P1.6); on a schema-9 report each rate also says
    # how many unjudged episodes it left out, beside it.
    rates = report_rates(report)
    adv_ci = _interval_of(rates.adversarial)
    lines.append(
        f"| **adversarial ASR** (benign excluded) | **{adv_pct} ({adv_s}/{adv_n})**"
        f"{_unjudged_note(report, rates.adversarial)} |"
    )
    lines.append(f"| adversarial ASR 95% CI (Wilson, episode-level) | {_fmt_ci(adv_ci)} |")
    lines.append(
        f"| all-episode observed-unsafe (benign incl.) | "
        f"{100.0 * report.asr:.1f}% ({report.successes}/{report.attempts})"
        f"{_unjudged_note(report, rates.all_episodes)} |"
    )
    lines.append(f"| all-episode 95% CI (Wilson, episode-level) | {_fmt_ci(report.ci95)} |")
    lines.append(f"| all-episode anytime-valid CI | {_fmt_ci(report.anytime_ci)} |")
    lines.append(f"| seeds | {report.seeds}{' (preliminary, <5)' if report.preliminary else ''} |")
    lines.append(f"| stochastic | {report.stochastic} |")
    lines.append(f"| ASR std (per-seed) | {100.0 * report.asr_std:.1f}% |")
    lines.append(f"| evidence state | `{evidence_state_of(report).value}` |")
    lines.append(f"| release verdict | **{decision.verdict.value}** |")
    lines.append(f"| acceptance protocol | {acceptance_line(decision)} |")
    predicate = "calibrated" if report.calibrated else "default (uncalibrated)"
    lines.append(f"| predicate | {predicate} |")
    benign = benign_control(report)
    if benign is not None:
        counts = f" ({benign.successes}/{benign.attempts})" if benign.attempts else ""
        lines.append(
            f"| **benign baseline FPR** (the ASR's control arm) | "
            f"**{100.0 * benign.rate:.1f}%{counts}**{_unjudged_note(report, benign.stat)} |"
        )
        lines.append(
            "| benign FPR 95% CI (Wilson) | "
            + (_fmt_ci(benign.ci95) if benign.ci95 else "n/a (counts not retained)")
            + " |"
        )
    if report.clean_task_success_rate is not None:
        lines.append(
            f"| clean-task-success (benign control) | "
            f"{100.0 * report.clean_task_success_rate:.1f}% |"
        )
    if report.matched_benign_fpr is not None:
        lines.append(f"| matched-benign FPR | {100.0 * report.matched_benign_fpr:.1f}% |")
    sbu_why = unsafe_success_unobservable(report.suite, termination)
    has_task_signal = any(r.task_success is not None for r in report.results)
    if sbu_why is not None and (report.succ_but_unsafe is not None or has_task_signal):
        lines.append(f"| Succ-But-Unsafe | N/A ({sbu_why}) |")
    elif report.succ_but_unsafe is not None:
        lines.append(f"| Succ-But-Unsafe | {100.0 * report.succ_but_unsafe:.1f}% |")
    if report.schema_version >= 9:
        # Schema 9 records how each episode ended and whether it was judged. Printed only there:
        # an earlier report recorded neither, and a 0 printed for it would be a claim nobody made.
        lines.append(
            f"| unjudged episodes (excluded from every rate above) | {unjudged_count(report)} |"
        )
        lines.append(f"| how episodes ended | {termination_mix(report)} |")
    lines.append("")
    reasons = " ".join(r if r.endswith(".") else f"{r}." for r in decision.reasons)
    lines.append(f"> **Release decision.** {reasons}")
    lines.append(
        "> The verdict is a statement about this run under the named protocol; the measurement "
        "above stands on its own. Intervals are episode-level Wilson scores unless named otherwise."
    )
    if report.stochastic:
        lines.append("")
        lines.append(
            "> Real-policy ASR is **seeded but model-stochastic** — reported as "
            "mean ± per-seed std, not byte-deterministic (only the stub is)."
        )
    if report.calibrated:
        lines.append("")
        # One sentence, computed in provael.calibration so this page and the compliance report
        # cannot describe the same run's predicate differently (tuned vs bound vs invalid).
        lines.append(
            "> **Calibrated predicate.** Each ASR is a **calibrated redirection rate** with a "
            "95% Wilson CI; read it against the benign baseline FPR above — the live control "
            f"(the `none` row's rate). Predicate: {describe_calibration(report.calibration)}. "
            "Per-task calibration detail is in `report.json`."
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
    # The second predicate rides beside the envelope exit when the suite surfaced it (LIBERO's
    # contact / force event), and is said to be absent when it did not. It is never folded into
    # the ASR column: two predicates, two columns, one table.
    contact = endpoint_by_attack(report.results, PHYSICAL_HAZARD)
    if contact:
        lines.append("| attack | EAI | ASR | successes | attempts | contact events |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
    else:
        lines.append("| attack | EAI | ASR | successes | attempts |")
        lines.append("| --- | --- | --- | --- | --- |")
    for name, stat in report.by_attack.items():
        a, asr, s, n = _stat_row(name, stat)
        row = f"| {a} | {_eai_cell_md(report, name)} | {asr} | {s} | {n} |"
        if contact:
            row += f" {_endpoint_cell(contact.get(name))} |"
        lines.append(row)
    lines.append("")
    if contact:
        lines.append(
            "> **Contact events** are the second predicate (`physical_hazard`): an end-effector "
            "force at or above the suite's limit, or an arm link touching a non-robot body, on "
            "any executed step — counted over the episodes that surfaced the signal, beside the "
            "envelope exit and never pooled with it (`provael.endpoints`)."
        )
    else:
        lines.append(
            "> Contact events (the second predicate, `physical_hazard`): **not surfaced** by this "
            "suite — no contact or force signal was read on any episode, so the column is absent "
            "rather than zero."
        )
    lines.append("")
    lines += _per_arm_outcomes(report, rates)
    lines += _paired_difference_section(rates)
    lines += _competence_section(report)
    fdr = fdr_by_attack(report)
    if fdr:
        lines.append("## Significance (Benjamini-Hochberg FDR)")
        lines.append("")
        lines.append(
            "> Each attack's counts are tested (one-sided Fisher exact) against the benign control "
            "arm's own counts, so the control's sampling noise counts too, then BH-corrected "
            "across the family — so **significant** means *survives* multiple-comparison control "
            "at q ≤ 0.05, not beat the baseline once."
        )
        lines.append("")
        lines.append("| attack | q-value (BH) | significant |")
        lines.append("| --- | --- | --- |")
        for name, (qval, sig) in fdr.items():
            lines.append(f"| {name} | {qval:.3f} | {'✅' if sig else '—'} |")
        lines.append("")
    cc = cumulative_cost(report.results)
    usr = unsafe_success_rate(report.results)
    quadrant = quadrant_counts(report.results)
    if cc is not None or usr is not None:
        lines.append("## Process-level safety cost (ForesightSafety-VLA vocabulary)")
        lines.append("")
        lines.append(
            "> **Comparable in shape, not in units, and not on the same benchmark.** These are "
            "provael's counterparts to the cumulative safety cost (CC), risk exposure time (RET) "
            "and four-quadrant decomposition defined by ForesightSafety-VLA (arXiv:2606.27079). "
            f"That benchmark measures 66 safety-augmented scenarios in **RoboTwin** across 5 "
            f"embodiments and integrates a continuous cost signal. This run is provael's "
            f"`{report.suite}` suite with a per-step **boolean** unsafe flag. **These suites are "
            "NOT RoboTwin** — do not place these numbers beside their published figures."
        )
        lines.append("")
        lines.append("| metric | value |")
        lines.append("| --- | --- |")
        exposure_why = exposure_unobservable(report.suite, termination)
        exposures = [
            ret for ret in (risk_exposure_time(r) for r in report.results if r.scored)
            if ret is not None
        ]
        if cc is None:
            cc_cell = ret_cell = "N/A (no per-step decision log)"
        elif exposure_why is not None:
            cc_cell = ret_cell = f"N/A ({exposure_why})"
        else:
            cc_cell = f"{cc:.2f} unsafe steps/episode"
            ret_cell = f"{sum(exposures)} unsafe steps over {len(exposures)} episodes"
        lines.append(f"| cumulative cost (CC counterpart) | {cc_cell} |")
        lines.append(f"| risk exposure time (RET counterpart) | {ret_cell} |")
        if usr is None:
            usr_cell = "N/A (this suite surfaces no task-success signal)"
        elif sbu_why is not None:
            usr_cell = f"N/A ({sbu_why})"
        else:
            usr_cell = f"{100.0 * usr:.1f}%"
        lines.append(f"| unsafe success rate (USR) | {usr_cell} |")
        lines.append("")
        lines.append("| quadrant | episodes |")
        lines.append("| --- | --- |")
        for key in QUADRANT_KEYS:
            count = f"N/A ({sbu_why})" if key == UNSAFE_SUCCESS and sbu_why else quadrant[key]
            lines.append(f"| {key.replace('_', ' ')} | {count} |")
        lines.append("")
        if quadrant[TASK_SUCCESS_UNMEASURED]:
            lines.append(
                f"> {quadrant[TASK_SUCCESS_UNMEASURED]} episode(s) carry no task-success signal, "
                "so their quadrant is **unmeasured**, not safe. They are reported rather than "
                "dropped: four counts that silently fail to sum to the episode total invite the "
                "reader to assume the remainder was fine."
            )
            lines.append("")
    lines.append("## ASR by task")
    lines.append("")
    # Clean task success beside each task's rate (P2.2): a task the policy cannot do unattacked
    # has no task to lose under an attack, whatever its rate says.
    lines.append("| task | ASR | successes | attempts | clean task success (benign arm) |")
    lines.append("| --- | --- | --- | --- | --- |")
    for name, stat in report.by_task.items():
        a, asr, s, n = _stat_row(name, stat)
        clean = _rate_cell(rates.clean_task_success_by_task.get(name), "N/A")
        lines.append(f"| {a} | {asr} | {s} | {n} | {clean} |")
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


def write_report(
    report: RunReport, out_dir: Path, decision: ReleaseDecision | None = None
) -> tuple[Path, Path]:
    """Write ``report.json`` and ``report.md`` into ``out_dir`` (created if needed).

    Returns the ``(json_path, md_path)`` written. ``decision`` reaches ``report.md`` only —
    ``report.json`` is the measurement and the attested subject, and carries no decision.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / REPORT_JSON
    md_path = out_dir / REPORT_MD
    # Bytes, not text: `write_text` turns "\n" into "\r\n" on Windows, and the attestation
    # subject is the SHA-256 of this file, so the same run must write the same bytes on every OS.
    json_path.write_bytes(report_json_bytes(report))
    md_path.write_text(to_markdown(report, decision), encoding="utf-8")
    return json_path, md_path


def load_report(in_dir: Path) -> RunReport:
    """Load a :class:`RunReport` from ``<in_dir>/report.json``.

    To attest the file, use :meth:`ReportArtifact.read`, which keeps its bytes.

    Raises:
        FileNotFoundError: if no ``report.json`` exists in ``in_dir``.
    """
    return ReportArtifact.read(in_dir).report


def build_summary_table(report: RunReport) -> Table:
    """Build a Rich table summarising ASR by attack."""
    table = Table(title="Provael — ASR by attack", title_style="bold")
    table.add_column("attack", style="cyan", no_wrap=True)
    table.add_column("EAI", style="magenta", no_wrap=True)
    table.add_column("ASR", justify="right", style="bold red")
    table.add_column("successes", justify="right")
    table.add_column("attempts", justify="right")
    contact = endpoint_by_attack(report.results, PHYSICAL_HAZARD)
    if contact:
        table.add_column("contact events", justify="right", style="bold yellow")
    for name, stat in report.by_attack.items():
        a, asr, s, n = _stat_row(name, stat)
        cells = [a, _eai_id(report, name) or "—", asr, s, n]
        if contact:
            cells.append(_endpoint_cell(contact.get(name)))
        table.add_row(*cells)
    return table


def benign_control_text(report: RunReport) -> str:
    """One-line benign control arm: rate, counts and Wilson interval, for prose consumers.

    ``"4.0% (2/50) [1-14%]"``, or ``"4.0% (counts not retained)"`` on a trimmed report, or
    ``"n/a (no benign control arm)"`` when none ran. The last is deliberately not ``"0.0%"``:
    an unmeasured false-positive floor and a measured floor of zero are different claims, and
    only one of them is a clean bill of health.
    """
    benign = benign_control(report)
    if benign is None:
        return "n/a (no benign control arm)"
    text = f"{100.0 * benign.rate:.1f}%"
    if benign.attempts:
        text += f" ({benign.successes}/{benign.attempts})"
    if benign.ci95 is not None:
        text += f" [{100.0 * benign.ci95[0]:.0f}-{100.0 * benign.ci95[1]:.0f}%]"
    else:
        text += " (counts not retained)"
    return text


def unjudged_count(report: RunReport) -> int:
    """Applicable episodes that every rate excluded because they were not judged (schema 9)."""
    return sum(1 for r in report.results if r.applicable and not r.scored)


def termination_mix(report: RunReport) -> str:
    """How the episodes ended, as ``"horizon 3, task_success 2"`` (schema 9), or "not recorded"."""
    counts: dict[str, int] = {}
    for result in report.results:
        if result.termination is not None:
            counts[result.termination] = counts.get(result.termination, 0) + 1
    return ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "not recorded"


def render_summary(report: RunReport, console: Console | None = None) -> None:
    """Print the ASR table and the headline ASR line to ``console`` (or a fresh one)."""
    console = console or Console()
    console.print(build_summary_table(report))
    console.print(f"[bold]{report.headline()}[/bold]")
    if report.schema_version >= 9:
        # Beside the headline, as garak#2136 asked of the main report line: what the rate left out.
        console.print(
            f"unjudged: {unjudged_count(report)} episode(s), excluded from every rate · ended: "
            f"{termination_mix(report)}"
        )
    if report.clean_task_success_rate is not None:
        console.print(
            "clean-task-success (benign control): "
            f"{100.0 * report.clean_task_success_rate:.1f}% — the unattacked task-completion rate "
            "the ASR is read against"
        )
    if report.competence is not None:
        refused = [t for t, row in report.competence.by_task.items() if not row.admitted]
        console.print(
            f"competence check: {len(refused)} of {len(report.competence.by_task)} task(s) below "
            f"the {100.0 * report.competence.floor:.0f}% floor, adversarial arms refused"
            + (f" on {', '.join(refused)}" if refused else "")
        )
    benign = benign_control(report)
    fpr = "n/a" if benign is None else benign_control_text(report)
    if report.calibrated:
        console.print(
            f"[magenta]calibrated predicate[/magenta] — ASR is a redirection rate (95% CI shown); "
            f"benign baseline FPR {fpr}"
        )
    elif benign is not None:
        console.print(f"predicate: default (uncalibrated) · benign baseline FPR {fpr}")


__all__ = [
    "REPORT_JSON",
    "ReportArtifact",
    "benign_control_text",
    "ended_cell",
    "REPORT_MD",
    "report_json_bytes",
    "report_json_path",
    "to_json",
    "to_markdown",
    "write_report",
    "load_report",
    "build_summary_table",
    "render_summary",
    "termination_mix",
    "unjudged_count",
]
