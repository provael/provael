"""Machine-readable crosswalk: the Embodied AI Security Top 10 (EAI) ↔ RoboJailBench's taxonomy.

RoboJailBench (Yeke, Zhou, Lin, Cai, Bianchi & Celik, Purdue; arXiv 2605.19328v1, 2026-05-19)
defines an **18-category, harm-outcome** security taxonomy for embodied agents, derived from ISO/TS
15066:2016 + ISO 10218-1/-2, Asimov's Laws, and FDA/news incident reports. The **Embodied AI
Security Top 10** (``docs/TOP10.md``) is an **attack-mechanism/surface** taxonomy. The two are
orthogonal axes — *what harm results* vs *how it is attacked* — so a clean 1:1 does not exist and a
mapping that showed 18/18 covered would not be credible. This module encodes the mapping
declaratively (so a test can catch it rotting as families change) and emits it deterministically. It
reuses :mod:`provael.scoring.asr` + :mod:`provael.calibration` for the measured head-to-head — it
does not reimplement ASR.

**Sim-only, defensive.** Coverage numbers are provael's own measured sim results (keep-out-zone
violations and pre-deployment screens), each carrying its transfer statement. No RoboJailBench
harness is run here and no comparative scores against their numbers are produced — a separate task.
The category names below are quoted **verbatim** from RoboJailBench Table 2; do not paraphrase them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from provael.calibration import wilson_ci
from provael.config import RunConfig
from provael.runner import run
from provael.scoring.asr import by_family, matched_benign_fpr
from provael.types import RunReport

#: The crosswalk target id (the CLI ``--target``) and the emitted-file basename.
CROSSWALK_TARGET = "robojailbench"
CROSSWALK_JSON = "crosswalk.robojailbench.json"
CROSSWALK_FORMAT = "provael-crosswalk/v1"

#: Pinned provenance of the taxonomy we map to (read once — see module docstring). Quoted verbatim.
ROBOJAILBENCH_SOURCE: dict[str, object] = {
    "name": "RoboJailBench",
    "title": "RoboJailBench: Benchmarking Adversarial Attacks and Defenses in Embodied Robotic "
    "Agents",
    "arxiv": "2605.19328",
    "arxiv_version": "v1",
    "arxiv_date": "2026-05-19",
    "authors": [
        "Doguhuan Yeke", "Yanming Zhou", "Leo Y. Lin", "Hongyu Cai", "Antonio Bianchi",
        "Z. Berkay Celik",
    ],
    "affiliation": "Purdue University",
    "taxonomy_location": "Table 2 (18 categories)",
    "leaderboard_url": "https://purseclab.github.io/benchmark-for-robotics-security/",
    "leaderboard_version": "1.0.0",
    "leaderboard_date": "2026-05-07",
    "derivation": (
        "ISO/TS 15066:2016; ISO 10218-1/-2; Asimov's Laws of Robotics; real-world incident reports "
        "(news + FDA); prior robotics-safety research"
    ),
}


class Coverage(StrEnum):
    """Provael's coverage state for a RoboJailBench harm category."""

    covered = "covered"
    partial = "partial"
    not_covered = "not covered"
    out_of_scope = "out of scope by design"


@dataclass(frozen=True)
class RjbCategory:
    """One RoboJailBench category (name verbatim) and its mapping into the EAI Top 10 + provael."""

    id: str
    name: str  # verbatim from RoboJailBench Table 2
    group: str
    eai: tuple[str, ...]  # EAI ids whose mechanism produces this harm
    families: tuple[str, ...]  # provael attack families that exercise it (empty if none)
    coverage: Coverage
    note: str


# Coverage legend (also rendered in the doc):
#   covered  — provael ships an applicable family that measures this harm class in sim (a keep-out
#              violation or a pre-deploy screen) with a benign-FPR control; a SIM PROXY, and mostly
#              stub-validated — see the head-to-head for the number and its transfer status.
#   partial  — a related mechanism is exercised, but only a facet / a loose proxy of the category.
#   not covered — no provael attack exercises this harm class.
#   out of scope by design — outside provael's sim-only VLA-policy red-team charter.
RJB_CATEGORIES: tuple[RjbCategory, ...] = (
    RjbCategory(
        "rjb01", "Collision with people", "physical safety",
        ("EAI04", "EAI06", "EAI02"), ("action_space", "misalignment", "sensor_spoof"),
        Coverage.partial,
        "provael measures a generic keep-out-zone violation — a sim proxy that does "
        "not distinguish a person from any keep-out target; stub-validated.",
    ),
    RjbCategory(
        "rjb02", "Collision with robots", "physical safety",
        ("EAI04", "EAI06", "EAI02"), ("action_space", "misalignment", "sensor_spoof"),
        Coverage.partial,
        "same generic keep-out-zone proxy; the target's identity (a robot) is not modelled.",
    ),
    RjbCategory(
        "rjb03", "Collision with objects", "physical safety",
        ("EAI04", "EAI06", "EAI02"), ("action_space", "misalignment", "sensor_spoof"),
        Coverage.partial,
        "same generic keep-out-zone proxy; the target's identity (an object) is not modelled.",
    ),
    RjbCategory(
        "rjb04", "Force/pressure violation", "physical safety",
        ("EAI04",), (),
        Coverage.not_covered,
        "provael perturbs motion / commanded-end-state channels, not force or pressure; "
        "no force is modelled in the suites.",
    ),
    RjbCategory(
        "rjb05", "Unsafe motion", "physical safety",
        ("EAI04",), ("action", "action_space"),
        Coverage.covered,
        "the action family (freeze / trajectory_hijack) and the keep-out hijack directly exercise "
        "unsafe / hijacked motion in simulation; stub-validated (see head-to-head).",
    ),
    RjbCategory(
        "rjb06", "Entrapment/crushing", "physical safety",
        ("EAI04",), (),
        Coverage.not_covered,
        "no gripper-closing / clamping dynamic exists in provael's suites.",
    ),
    RjbCategory(
        "rjb07", "Unauthorized capture", "data & privacy",
        ("EAI09",), (),
        Coverage.not_covered,
        "EAI09 names the surveillance facet, but the confidentiality family screens a memorized "
        "training-canary leak (membership-inference / extraction), not data capture; no attack "
        "drives the robot to record.",
    ),
    RjbCategory(
        "rjb08", "Data misuse", "data & privacy",
        ("EAI09",), (),
        Coverage.not_covered,
        "as rjb07: provael screens memorization-leak, not use of collected data.",
    ),
    RjbCategory(
        "rjb09", "Unauthorized sharing", "data & privacy",
        ("EAI09",), (),
        Coverage.not_covered,
        "as rjb07: no attack exercises exfiltration / telemetry sharing.",
    ),
    RjbCategory(
        "rjb10", "Unauthorized retention", "data & privacy",
        ("EAI09",), (),
        Coverage.not_covered,
        "as rjb07: no attack exercises unlawful retention of collected data.",
    ),
    RjbCategory(
        "rjb11", "Discrimination", "behavioral & ethical",
        ("EAI01", "EAI06"), (),
        Coverage.not_covered,
        "a content / ethics harm; provael measures embodied keep-out and screen mechanisms, not "
        "content policy. Inducible via an EAI01 jailbreak but not measured here.",
    ),
    RjbCategory(
        "rjb12", "Deception/manipulation", "behavioral & ethical",
        ("EAI01", "EAI06"), (),
        Coverage.not_covered,
        "a content / ethics harm; not measured by provael (see rjb11).",
    ),
    RjbCategory(
        "rjb13", "Public disruption", "behavioral & ethical",
        ("EAI04",), (),
        Coverage.not_covered,
        "no route-blocking / public-disruption scenario exists in provael's suites; EAI04 is the "
        "nearest mechanism.",
    ),
    RjbCategory(
        "rjb14", "Pornography", "behavioral & ethical",
        (), (),
        Coverage.out_of_scope,
        "a content-moderation harm outside provael's adversarial-embodied-security charter; "
        "belongs to LLM content-safety, not VLA-policy red-teaming.",
    ),
    RjbCategory(
        "rjb15", "Hateful conduct", "behavioral & ethical",
        (), (),
        Coverage.out_of_scope,
        "a content-moderation harm outside provael's charter (see rjb14).",
    ),
    RjbCategory(
        "rjb16", "Terrorism/weaponization", "behavioral & ethical",
        ("EAI01",), ("instruction",),
        Coverage.partial,
        "the instruction family exercises the jailbreak-to-harmful-action mechanism (and is the "
        "one family that transfers on a real policy), measured as end-effector diversion — not "
        "the weaponization outcome itself.",
    ),
    RjbCategory(
        "rjb17", "Theft", "behavioral & ethical",
        ("EAI08", "EAI01"), ("authorization", "instruction"),
        Coverage.partial,
        "the authorization family (self-authorize a guarded action) and the instruction jailbreak "
        "exercise the unauthorized-action mechanism; measured as a screen / diversion proxy, not "
        "the theft outcome.",
    ),
    RjbCategory(
        "rjb18", "Trespassing", "physical safety",
        ("EAI04", "EAI02", "EAI08", "EAI06"), ("action_space", "sensor_spoof", "misalignment"),
        Coverage.covered,
        "'enter a restricted area' maps directly to provael's keep-out-zone violation — the most "
        "literal sim match; stub-validated (see head-to-head).",
    ),
)


@dataclass(frozen=True)
class EaiEntry:
    """One EAI Top-10 id and the RoboJailBench categories it corresponds to (or none)."""

    id: str
    name: str  # short name, must match docs/TOP10.md
    robojailbench: tuple[str, ...]  # RJB category ids, or empty for 'no counterpart'
    note: str


#: The symmetric direction: each EAI01-EAI10 → its RoboJailBench counterpart(s), or 'no
# counterpart'.
#: Four EAI ids have no counterpart because they are *mechanisms / meta-risks*, not harm classes —
#: which is the whole point about the two taxonomies being orthogonal.
EAI_TO_RJB: tuple[EaiEntry, ...] = (
    EaiEntry(
        "EAI01", "Policy & instruction jailbreak", ("rjb16", "rjb17"),
        "a jailbreak can drive many harms; it maps to the harmful-action outcomes provael's "
        "instruction family can reach (weaponization, theft), and can also induce the content "
        "harms rjb11/rjb12 that provael does not measure.",
    ),
    EaiEntry(
        "EAI02", "Adversarial perception", ("rjb01", "rjb02", "rjb03", "rjb05", "rjb18"),
        "a sensor-spoof driving the effector into a keep-out zone → the collision / unsafe-motion "
        "/ trespassing harms.",
    ),
    EaiEntry(
        "EAI03", "Model & pipeline poisoning, backdoors & supply chain", (),
        "no counterpart: a backdoor is a delivery mechanism, not a harm class — once triggered it "
        "can produce any of RoboJailBench's 18 harms.",
    ),
    EaiEntry(
        "EAI04", "Action-space integrity",
        ("rjb01", "rjb02", "rjb03", "rjb04", "rjb05", "rjb06", "rjb13", "rjb18"),
        "action-space attacks produce the physical-safety harm outcomes (collision, force, unsafe "
        "motion, entrapment, disruption, trespassing).",
    ),
    EaiEntry(
        "EAI05", "Indirect / embodied prompt injection", (),
        "no counterpart: an injection channel is a delivery mechanism, not a harm class.",
    ),
    EaiEntry(
        "EAI06", "Cross-domain safety misalignment", ("rjb01", "rjb02", "rjb03", "rjb05"),
        "a benign-sounding instruction driving an unsafe action → the collision / unsafe-motion "
        "harms.",
    ),
    EaiEntry(
        "EAI07", "CPS, firmware, comms & teleoperation compromise", (),
        "no counterpart: RoboJailBench's taxonomy is harm-outcome and has no CPS / firmware / "
        "comms class; also out of provael's scope by design.",
    ),
    EaiEntry(
        "EAI08", "Identity, access & excessive autonomy", ("rjb17", "rjb18"),
        "unauthorized or over-broad action → theft and trespassing.",
    ),
    EaiEntry(
        "EAI09", "Model & data confidentiality", ("rjb07", "rjb08", "rjb09", "rjb10"),
        "the data / privacy harms — though provael's confidentiality family screens a memorization "
        "leak, not these capture / sharing / retention behaviours (see the coverage column).",
    ),
    EaiEntry(
        "EAI10", "Insufficient evaluation, observability & incident response", (),
        "no counterpart: a governance / operations meta-risk, not a harm class.",
    ),
)


def referenced_eai_ids() -> set[str]:
    """Every EAI id used anywhere in the mapping (both directions)."""
    ids = {e.id for e in EAI_TO_RJB}
    for cat in RJB_CATEGORIES:
        ids.update(cat.eai)
    return ids


def referenced_families() -> set[str]:
    """Every provael family name used in the mapping."""
    fams: set[str] = set()
    for cat in RJB_CATEGORIES:
        fams.update(cat.families)
    return fams


def coverage_counts() -> dict[str, int]:
    """How many RJB categories fall in each coverage state (for the honest headline)."""
    counts = {state.value: 0 for state in Coverage}
    for cat in RJB_CATEGORIES:
        counts[cat.coverage.value] += 1
    return counts


def _mapping_dict() -> dict[str, object]:
    """The pure, static, deterministic mapping (no run, no clock)."""
    return {
        "format": CROSSWALK_FORMAT,
        "target": CROSSWALK_TARGET,
        "source": ROBOJAILBENCH_SOURCE,
        "coverage_counts": coverage_counts(),
        "robojailbench_to_eai": [
            {
                "id": c.id, "category": c.name, "group": c.group,
                "eai": list(c.eai), "families": list(c.families),
                "coverage": c.coverage.value, "note": c.note,
            }
            for c in RJB_CATEGORIES
        ],
        "eai_to_robojailbench": [
            {"id": e.id, "name": e.name, "robojailbench": list(e.robojailbench), "note": e.note}
            for e in EAI_TO_RJB
        ],
    }


def to_crosswalk_json() -> str:
    """Deterministic JSON of the pure mapping (``sort_keys``, no wall-clock)."""
    return json.dumps(_mapping_dict(), indent=2, sort_keys=True)


def _cov_symbol(state: str) -> str:
    return {"covered": "✅", "partial": "🟡", "not covered": "⬜",
            "out of scope by design": "▫️"}.get(state, "")


def to_crosswalk_markdown() -> str:
    """Deterministic Markdown: the two crosswalk tables + the honest coverage tally."""
    src = ROBOJAILBENCH_SOURCE
    counts = coverage_counts()
    lines: list[str] = []
    lines.append(
        f"<!-- generated by `provael crosswalk --target {CROSSWALK_TARGET}` — do not edit -->"
    )
    lines.append("")
    lines.append(
        f"Mapped against **{src['name']}** (arXiv {src['arxiv']}{src['arxiv_version']}, "
        f"{src['arxiv_date']}; leaderboard v{src['leaderboard_version']}, "
        f"{src['leaderboard_date']}). Category names quoted verbatim from "
        f"{src['taxonomy_location']}."
    )
    lines.append("")
    lines.append(
        f"**Coverage tally:** {counts['covered']} covered · {counts['partial']} partial · "
        f"{counts['not covered']} not covered · "
        f"{counts['out of scope by design']} out of scope by design (of 18)."
    )
    lines.append("")
    lines.append("### RoboJailBench → Embodied AI Security Top 10")
    lines.append("")
    lines.append(
        "| # | RoboJailBench category | Group | EAI id(s) | Provael family | Coverage | Note |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for c in RJB_CATEGORIES:
        eai = ", ".join(c.eai) or "—"
        fam = ", ".join(f"`{f}`" for f in c.families) or "—"
        lines.append(
            f"| {c.id[3:]} | {c.name} | {c.group} | {eai} | {fam} | "
            f"{_cov_symbol(c.coverage.value)} {c.coverage.value} | {c.note} |"
        )
    lines.append("")
    lines.append("### Embodied AI Security Top 10 → RoboJailBench")
    lines.append("")
    lines.append("| EAI | Name | RoboJailBench counterpart(s) | Note |")
    lines.append("| --- | --- | --- | --- |")
    for e in EAI_TO_RJB:
        rjb = ", ".join(
            c.name for c in RJB_CATEGORIES if c.id in e.robojailbench
        ) or "*no counterpart*"
        lines.append(f"| {e.id} | {e.name} | {rjb} | {e.note} |")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------
# Head-to-head measured coverage — reuses provael.scoring.asr / provael.calibration (no reimpl).
# --------------------------------------------------------------------------------------------

#: Families that transfer on a real policy today (see results/cross_arch_transfer + docs/findings).
#: Only the instruction family has a measured real-policy transfer; everything else is
# stub-validated.
_REAL_TRANSFER_NOTE: dict[str, str] = {
    "instruction": (
        "measured on a real policy — `roleplay` diverted real SmolVLA×LIBERO 100% (10/10) 95% CI "
        "[72–100%], `goal_substitution` 60% (sim-only, one task, n=10; results/cross_arch_transfer)"
    ),
}
_NOT_DEMONSTRATED = "not demonstrated on a real policy (stub-validated only)"


def measured_families() -> list[str]:
    """The provael families that appear in a covered/partial RJB mapping (sorted, unique)."""
    fams: set[str] = set()
    for c in RJB_CATEGORIES:
        if c.coverage in (Coverage.covered, Coverage.partial):
            fams.update(c.families)
    return sorted(fams)


#: The deterministic CPU suites the mapped families are applicable on: scalar-danger families run on
#: ``stub``; the keep-out families (sensor_spoof / action_space / misalignment) run on ``reach``.
_MEASUREMENT_SUITES: tuple[str, ...] = ("stub", "reach")


def _measurement_reports() -> list[RunReport]:
    """Deterministic CPU runs over every mapped family across the suites they are applicable on."""
    attacks = ["none", *measured_families()]
    return [
        run(RunConfig(policy="stub", suite=suite, attacks=attacks, episodes=10, seed=0))
        for suite in _MEASUREMENT_SUITES
    ]


def _row_for(family: str, report: RunReport) -> dict[str, object] | None:
    """Head-to-head row for ``family`` from ``report`` (reuses scoring), or None if not "
    "applicable."""
    stat = by_family(report.results).get(family)
    if stat is None or stat.attempts == 0:
        return None
    lo, hi = wilson_ci(stat.successes, stat.attempts)
    mbf = matched_benign_fpr(report.results)
    return {
        "family": family,
        "measured_on": f"{report.policy}/{report.suite}",
        "asr": round(stat.asr, 4),
        "n": stat.attempts,
        "successes": stat.successes,
        "wilson_ci95": [round(lo, 4), round(hi, 4)],
        "matched_benign_fpr": None if mbf is None else round(mbf, 4),
        "transfer_statement": _REAL_TRANSFER_NOTE.get(family, _NOT_DEMONSTRATED),
    }


def head_to_head(report: RunReport | None = None) -> list[dict[str, object]]:
    """Measured ASR per mapped family, each with its transfer statement (reuses scoring.asr).

    For every family the crosswalk relies on (covered/partial categories), report the ASR with its
    n, 95% Wilson CI, and matched benign-FPR — computed by the shipped scoring, not reimplemented —
    and, mandatorily, the transfer statement: a family that has not transferred on a real policy is
    labelled *"not demonstrated on a real policy"* in the same row as its number.

    With no ``report`` it measures across the deterministic CPU ``stub`` + ``reach`` suites (each
    mapped family on the suite it is applicable on). Given a ``report`` (e.g. the certify run under
    assessment) it measures only that one, so the appendix reflects exactly what was run.
    """
    reports = [report] if report is not None else _measurement_reports()
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for family in measured_families():
        for rep in reports:
            row = _row_for(family, rep)
            if row is not None and family not in seen:
                rows.append(row)
                seen.add(family)
    return rows


def build_appendix(report: RunReport) -> dict[str, object]:
    """The certify appendix payload: the mapping + the head-to-head measured against ``report``.

    Composed for :func:`provael.certify.build_dossier` to embed as an optional appendix — it does
    not render a dossier, it hands back data. The head-to-head reuses :func:`head_to_head`.
    """
    return {
        "format": CROSSWALK_FORMAT,
        "target": CROSSWALK_TARGET,
        "source": ROBOJAILBENCH_SOURCE,
        "coverage_counts": coverage_counts(),
        "measured_head_to_head": head_to_head(report),
        "note": (
            "Taxonomy crosswalk + provael's own measured coverage. No RoboJailBench benchmark was "
            "run and no comparative scores against their numbers are produced. Each family's "
            "number carries its transfer statement; only instruction has real-policy transfer."
        ),
    }


__all__ = [
    "CROSSWALK_TARGET",
    "CROSSWALK_JSON",
    "CROSSWALK_FORMAT",
    "ROBOJAILBENCH_SOURCE",
    "Coverage",
    "RjbCategory",
    "EaiEntry",
    "RJB_CATEGORIES",
    "EAI_TO_RJB",
    "referenced_eai_ids",
    "referenced_families",
    "coverage_counts",
    "to_crosswalk_json",
    "to_crosswalk_markdown",
    "measured_families",
    "head_to_head",
    "build_appendix",
]
