"""A test report in the SHAPE of ISO/IEC 17025:2017 clause 7.8 — the document assessors read.

WHY THIS SHAPE. The 13 September 2026 regulatory re-read found that no certifier, notified body or
insurer has published acceptance of SARIF, OSCAL or an ML-BOM as evidence. What a notified body
assessing a machinery technical file is used to reading is a **test report laid out as ISO/IEC
17025 clause 7.8 requires** — the item under test identified unambiguously, the method, the
conditions, the results with their uncertainty, the deviations, the dates, who authorised it —
plus a way to reproduce it. This module renders a provael run in that layout so an assessor finds
each field where they expect it, and so a missing field is visible as a blank rather than absent.

WHAT THIS IS NOT, in the words the report itself carries. Provael is **not an accredited
laboratory**, this document is **not an ISO/IEC 17025 report** and it makes **no statement of
conformity** with any standard or regulation. It is a *behavioural-susceptibility measurement in
simulation*, shaped like a test report. Clause 7.8's list of contents is reproduced here as the
skeleton, not as a claim of compliance with the standard; the same honesty rule that governs every
other emitter applies (``docs/compliance/index.md``, "an input, never a determination").

DETERMINISM. Like the scorecard, this is a pure rendering of ``report.json`` and, when present,
``execution-manifest.json``. No wall-clock value is introduced: the date of issue is the day a
person signs the report, so it is a blank for that person — an emitter that stamped "today" would
make the document assert a signature that never happened.

THE ANNEX. Annex A is the clause map from :mod:`provael.compliance`, the single source of every
framework mapping in this project, rendered as "what this evidence speaks to and what it does not
establish". Nothing is mapped here that is not mapped there.
"""

from __future__ import annotations

import json
from pathlib import Path

from provael.calibration import wilson_ci
from provael.compliance import to_compliance
from provael.execution import ExecutionManifest
from provael.scoring.asr import benign_control, semantic_role
from provael.types import RunReport

#: Default filename written into a run's output directory.
TEST_REPORT_MD = "report.test-report.md"
#: The manifest file the CLI reads beside ``report.json`` when it exists.
EXECUTION_MANIFEST_JSON = "execution-manifest.json"
#: The blank a signatory fills. Deliberately conspicuous.
BLANK = "_____ (to be completed by the authorising person)"

_NOT_ACCREDITED = (
    "Provael is not an accredited laboratory and this is not an ISO/IEC 17025 report. The layout "
    "follows ISO/IEC 17025:2017 clause 7.8 so that each element is where an assessor expects it. "
    "No statement of conformity with any standard or regulation is made or implied."
)


def _pct(x: float) -> str:
    return f"{100.0 * x:.1f}%"


def _rate(successes: int, attempts: int) -> str:
    return "N/A (no applicable episode)" if attempts == 0 else _pct(successes / attempts)


def _ci(successes: int, attempts: int) -> str:
    if attempts == 0:
        return "—"
    lo, hi = wilson_ci(successes, attempts)
    return f"[{_pct(lo)}, {_pct(hi)}]"


#: The three populations `provael.scoring.asr.semantic_role` distinguishes, in report words.
_OUTCOME = {
    "benign-control": "benign baseline — the floor",
    "harmless-variation": "control — enters neither the ASR nor the floor",
    "adversarial-treatment": "adversarial treatment",
}


def _roles(report: RunReport) -> dict[str, str]:
    """Role per arm: the stored ``roles`` map, completed from the episodes for arms it omits.

    ``report.roles`` lists the adversarial and control arms; the benign baseline is identified by
    its family on the episodes themselves, exactly as :func:`provael.scoring.asr.semantic_role`
    does. A report whose episodes were trimmed keeps whatever ``roles`` recorded.
    """
    roles = {r.attack: semantic_role(r) for r in report.results}
    roles.update(report.roles)
    return roles


def load_manifest(in_dir: Path) -> ExecutionManifest | None:
    """The execution manifest beside a report, or ``None`` when the run wrote none."""
    base = in_dir if in_dir.is_dir() else in_dir.parent
    path = base / EXECUTION_MANIFEST_JSON
    if not path.exists():
        return None
    return ExecutionManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _item_under_test(report: RunReport, manifest: ExecutionManifest | None) -> list[str]:
    lines = [f"- **Policy adapter:** `{report.policy}`"]
    if report.model:
        lines.append(f"- **Checkpoint:** `{report.model}`")
    if manifest is not None:
        rev = manifest.checkpoint_revision or "not recorded"
        digest = manifest.checkpoint_digest or "not recorded"
        lines.append(f"- **Checkpoint revision:** `{rev}`  **digest:** `{digest}`")
        head = "deterministic"
        if report.stochastic:
            head = "model-stochastic sampling, seeded per episode"
        lines.append(f"- **Action head:** {head}")
    else:
        lines.append("- **Checkpoint revision / digest:** not recorded (no execution manifest)")
    lines.append(
        "- **Condition on receipt:** loaded as published by its provider; integrity verification "
        "is recorded in the execution manifest when `provael verify-checkpoint` ran, and absent "
        "otherwise."
    )
    return lines


def _method(report: RunReport, manifest: ExecutionManifest | None) -> list[str]:
    protocol = (
        f"`{manifest.protocol_id}` version `{manifest.protocol_version}`"
        if manifest is not None
        else "`provael-redteam` (version not recorded: no execution manifest)"
    )
    predicate = (
        "calibrated (see the calibration block)" if report.calibrated else "default, uncalibrated"
    )
    return [
        f"- **Tool:** provael `{report.tool_version}` — protocol {protocol}",
        f"- **Simulator suite:** `{report.suite}`; tasks: "
        + ", ".join(f"`{t}`" for t in report.tasks),
        f"- **Treatment arms:** {', '.join(f'`{a}`' for a in report.attacks)}",
        f"- **Unsafe predicate:** {predicate}",
        f"- **Episode design:** {report.episodes} episode(s) per (task, arm), horizon "
        f"{report.horizon} steps, base seed {report.seed} (episode *i* used seed "
        f"{report.seed} + *i*), {report.seeds} seed(s)",
        "- **Reference:** the method is documented at docs.provael.com (quickstart, attacks, "
        "sim-predicts-real); the run is reproducible from the committed `report.json`'s config.",
    ]


def _conditions(report: RunReport, manifest: ExecutionManifest | None) -> list[str]:
    if manifest is None:
        return [
            f"- **Accelerator requested:** `{report.accelerator or 'not recorded'}`",
            "- **Hardware, OS, Python, precision:** not recorded (no execution manifest)",
            "- **Physical robot:** none — simulation only",
        ]
    return [
        f"- **Hardware:** `{manifest.hardware or 'not recorded'}`  **accelerator:** "
        f"`{manifest.accelerator or 'not recorded'}`  **precision:** "
        f"`{manifest.precision or 'not recorded'}`",
        f"- **OS / Python:** `{manifest.os or 'not recorded'}` / "
        f"`{manifest.python_version or 'not recorded'}`",
        f"- **Dependency lock digest:** `{manifest.dep_lock_digest or 'not recorded'}`",
        f"- **Network policy:** `{manifest.network_policy}`",
        "- **Physical robot:** none — simulation only",
    ]


def _results(report: RunReport) -> list[str]:
    _adv_rate, adv_s, adv_n = report.adversarial_headline()
    lines = [
        f"- **Adversarial attack-success rate (ASR):** {_rate(adv_s, adv_n)} {_ci(adv_s, adv_n)} "
        f"({adv_s}/{adv_n} applicable adversarial episodes)",
    ]
    benign = benign_control(report)
    if benign is not None:
        counts = f" ({benign.successes}/{benign.attempts})" if benign.attempts else ""
        interval = (
            _ci(benign.successes, benign.attempts)
            if benign.attempts
            else "(no interval recoverable)"
        )
        lines.append(
            f"- **Benign control (the floor the ASR is read against):** {_pct(benign.rate)} "
            f"{interval}{counts}"
        )
    if report.clean_task_success_rate is not None:
        lines.append(
            f"- **Clean task success (competence control):** {_pct(report.clean_task_success_rate)}"
        )
    lines += [
        "",
        "| arm | role | outcome | rate | 95% CI (Wilson) | unsafe / attempts |",
        "|---|---|---|---:|:---:|---:|",
    ]
    roles = _roles(report)
    for name, stat in report.by_attack.items():
        role = roles.get(name, "adversarial-treatment")
        outcome = _OUTCOME.get(role, "adversarial treatment")
        lines.append(
            f"| `{name}` | {role} | {outcome} | {_rate(stat.successes, stat.attempts)} "
            f"| {_ci(stat.successes, stat.attempts)} | {stat.successes} / {stat.attempts} |"
        )
    lines += [
        "",
        "Units: rates are episode fractions; an episode is *unsafe* when the suite's predicate "
        "fired at any step within the horizon. A control arm enters neither the ASR nor the benign "
        "floor. `N/A` is an arm that had no applicable episode on this suite — it was not "
        "measured, and must not be read as 0%.",
    ]
    return lines


def _uncertainty(report: RunReport) -> list[str]:
    lines = [
        "- Every rate above carries a 95% Wilson score interval over its own episodes.",
        f"- Per-seed spread of the ASR (standard deviation across seeds): {report.asr_std:.3f}.",
    ]
    if report.anytime_ci is not None:
        lo, hi = report.anytime_ci
        lines.append(f"- Anytime-valid interval on the headline: [{_pct(lo)}, {_pct(hi)}].")
    if report.stochastic:
        lines.append(
            "- The policy samples its actions; episodes are seeded and the applied seed is "
            "recorded per episode, but a re-execution is expected to match in distribution, not "
            "byte for byte."
        )
    else:
        lines.append(
            "- The run is byte-deterministic: the same configuration reproduces `report.json` "
            "exactly."
        )
    lines.append(
        "- A single-task result carries no task-clustered interval; a multi-task run's clustered "
        "interval is reported in its aggregate, never here."
    )
    return lines


def _deviations(report: RunReport, manifest: ExecutionManifest | None) -> list[str]:
    lines: list[str] = []
    not_applicable = [n for n, s in report.by_attack.items() if s.attempts == 0]
    if not_applicable:
        lines.append(
            f"- Arms with no applicable episode on this suite (excluded from every rate): "
            f"{', '.join(f'`{n}`' for n in not_applicable)}."
        )
    if report.preliminary:
        lines.append("- The report is marked **preliminary** by its producer.")
    if manifest is not None:
        lines += [f"- {d}" for d in manifest.deviations]
        if manifest.skipped_checks:
            skipped = ", ".join(f"`{c}`" for c in manifest.skipped_checks)
            lines.append(f"- Skipped checks: {skipped}.")
        if manifest.missing_fields:
            missing = ", ".join(f"`{f}`" for f in manifest.missing_fields)
            lines.append(f"- Manifest fields not recorded: {missing}.")
    else:
        lines.append(
            "- No execution manifest accompanies this report; provenance fields are blank above."
        )
    return lines or ["- None recorded."]


def _annex_clause_map(report: RunReport) -> list[str]:
    compliance = to_compliance(report)
    lines = [
        "| framework | control | what this evidence speaks to | status | not established |",
        "|---|---|---|---|---|",
    ]
    for entry in compliance.entries:
        gap = entry.gap_reason or "—"
        lines.append(
            f"| {entry.framework} | {entry.control_id} — {entry.control_title} | "
            f"{entry.provael_signal} | {entry.status} | {gap} |"
        )
    lines += ["", f"_{compliance.disclaimer}_"]
    for caveat in compliance.scope_caveats:
        lines.append(f"- **{caveat.id}:** {caveat.text}")
    return lines


def to_test_report_markdown(report: RunReport, manifest: ExecutionManifest | None = None) -> str:
    """Render the clause-7.8-shaped test report as Markdown."""
    run_id = manifest.run_id if manifest is not None else "not recorded (no execution manifest)"
    digest = manifest.report_digest if manifest is not None else "not recorded"
    started = (manifest.started_at if manifest is not None else None) or "not recorded"
    ended = (manifest.ended_at if manifest is not None else None) or "not recorded"
    operator = manifest.operator if manifest is not None and manifest.operator else BLANK
    reviewer = manifest.reviewer if manifest is not None and manifest.reviewer else BLANK
    evidence = (
        manifest.evidence_state
        if manifest is not None
        else (report.evidence_state or "not recorded")
    )
    verdict = manifest.release_verdict if manifest is not None else "not recorded"
    lines: list[str] = [
        "# Test report — adversarial robustness of a vision-language-action policy in simulation",
        "",
        f"> {_NOT_ACCREDITED}",
        "",
        "## 1. Identification (7.8.2.1 a–e, j)",
        "",
        f"- **Report identifier:** run `{run_id}` · report digest `{digest}` · this document is "
        "complete in one part",
        f"- **Issued by (laboratory in the clause's sense):** {operator} — *not an accredited "
        "laboratory*",
        f"- **Reviewed by:** {reviewer}",
        f"- **Customer:** {BLANK}",
        f"- **Date of issue:** {BLANK}",
        "",
        "## 2. Item under test (7.8.2.1 g, h)",
        "",
        *_item_under_test(report, manifest),
        "",
        "## 3. Method (7.8.2.1 f, k)",
        "",
        *_method(report, manifest),
        "",
        "## 4. Dates and location of the activity (7.8.2.1 c, i)",
        "",
        f"- **Started:** `{started}`  **ended:** `{ended}` (UTC, from the execution manifest)",
        "- **Location:** the machine described in section 5; no activity took place outside it",
        "",
        "## 5. Conditions (7.8.3.1 a)",
        "",
        *_conditions(report, manifest),
        "",
        "## 6. Results (7.8.2.1 m)",
        "",
        *_results(report),
        "",
        "## 7. Measurement uncertainty (7.8.3.1 c)",
        "",
        *_uncertainty(report),
        "",
        "## 8. Deviations, additions and exclusions (7.8.2.1 n)",
        "",
        *_deviations(report, manifest),
        "",
        "## 9. Statement of conformity (7.8.3.1 b)",
        "",
        "None. This report establishes no conformity with any standard, regulation or "
        "specification, and no opinion or interpretation (7.8.3.1 d) is offered. Annex A lists the "
        "requirements this measurement can serve as an input to, and what each does not establish.",
        "",
        "## 10. Scope of the results (7.8.2.1 l)",
        "",
        "The results relate only to the checkpoint identified in section 2, driven through the "
        "simulator suite and tasks identified in section 3, under the conditions of section 5. "
        "They are not results for the model family, for other checkpoints of the same name, for "
        "other simulators, or for any physical robot.",
        "",
        "## 11. External providers (7.8.2.1 p)",
        "",
        f"- Checkpoint: the provider named in section 2 (`{report.model or report.policy}`)",
        f"- Simulator: `{report.suite}` and the physics engine it wraps",
        "- Every rate in section 6 was produced by provael; nothing in this report was measured "
        "by a third party.",
        "",
        "## 12. Evidence state and verdict (7.8.3.1 e)",
        "",
        f"- **Evidence state:** `{evidence}` (see docs.provael.com, evidence ladder)",
        f"- **Release verdict:** `{verdict}`",
        "- **Reproduction:** `provael reproduce` on the committed `report.json`; `provael attest` "
        "binds this report to a signature when a key is supplied.",
        "",
        "## 13. Authorisation (7.8.2.1 o)",
        "",
        f"- **Authorised by (name, role):** {BLANK}",
        f"- **Signature and date:** {BLANK}",
        "",
        "## Annex A — clause map (from `provael report --format compliance`)",
        "",
        *_annex_clause_map(report),
        "",
    ]
    return "\n".join(lines)


def write_test_report(
    report: RunReport, path: Path, manifest: ExecutionManifest | None = None
) -> Path:
    """Write the Markdown test report to ``path`` and return it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_test_report_markdown(report, manifest), encoding="utf-8")
    return path


__all__ = [
    "BLANK",
    "EXECUTION_MANIFEST_JSON",
    "TEST_REPORT_MD",
    "load_manifest",
    "to_test_report_markdown",
    "write_test_report",
]
