"""Aggregate run reports into a ranked ASR leaderboard.

Reads any number of ``report.json`` files, buckets every episode by
``(policy, suite, family)``, and produces a ranked table plus a representative
example payload per attack. Output is deterministic (sorted rows/keys, no wall-clock,
no source paths) so the committed leaderboard JSON is byte-stable.

A leaderboard is flagged ``is_demo`` when every aggregated run used the ``stub``
policy — i.e. there is no real-model number yet. The Gradio Space renders a clear
"demo data" banner in that case.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

from pydantic import BaseModel, Field

from provael.attacks.registry import make_attack
from provael.policies.stub import ATTACKABLE_OBS_FIELDS
from provael.report import REPORT_JSON, load_report
from provael.suites.stub import BASE_INSTRUCTION, StubSuite
from provael.types import RunReport

LEADERBOARD_JSON = "leaderboard.json"


class LeaderboardRow(BaseModel):
    """One ranked row: ASR for a ``(policy, suite, family)`` slice."""

    policy: str
    suite: str
    family: str
    attempts: int
    successes: int
    asr: float


class AttackExample(BaseModel):
    """A representative adversarial artifact produced by one attack."""

    attack: str
    family: str
    example: str


class Leaderboard(BaseModel):
    """A ranked, deterministic ASR leaderboard built from run reports."""

    schema_version: int = 1
    is_demo: bool = Field(..., description="True when every aggregated run used the stub policy.")
    rows: list[LeaderboardRow] = Field(default_factory=list)
    examples: list[AttackExample] = Field(default_factory=list)


def find_reports(paths: list[str]) -> list[Path]:
    """Resolve a list of paths/globs into a sorted, de-duplicated list of report.json files.

    Each entry may be a directory (searched recursively for ``report.json``), a glob
    pattern, or a direct path to a ``report.json``.
    """
    found: set[Path] = set()
    for entry in paths:
        if any(char in entry for char in "*?["):
            matches = [Path(m) for m in sorted(glob.glob(entry))]
        else:
            matches = [Path(entry)]
        for match in matches:
            if match.is_dir():
                found.update(match.rglob(REPORT_JSON))
            elif match.name == REPORT_JSON and match.exists():
                found.add(match)
    return sorted(found)


def attack_examples(attack_names: list[str]) -> list[AttackExample]:
    """Build a representative example artifact for each attack (deterministic).

    Re-runs each attack's ``perturb`` on a canonical stub observation and reports the
    changed instruction (instruction family) or the injected observation channel
    (visual / injection families). Policy-agnostic — it describes what the attack does.
    """
    base_obs = StubSuite().reset("reach", 0)
    examples: list[AttackExample] = []
    for name in attack_names:
        attack = make_attack(name)
        adv_instruction, adv_obs = attack.perturb(BASE_INSTRUCTION, base_obs)
        if adv_instruction != BASE_INSTRUCTION:
            artifact = adv_instruction
        else:
            changed = [
                f"{key}={adv_obs.get(key)!r}"
                for key in ATTACKABLE_OBS_FIELDS
                if adv_obs.get(key) != base_obs.get(key)
            ]
            artifact = "; ".join(changed)
        examples.append(AttackExample(attack=name, family=attack.family, example=artifact))
    return sorted(examples, key=lambda e: (e.family, e.attack))


def aggregate(reports: list[RunReport]) -> Leaderboard:
    """Aggregate run reports into a ranked :class:`Leaderboard`."""
    buckets: dict[tuple[str, str, str], list[int]] = {}
    attack_names: set[str] = set()
    for report in reports:
        for result in report.results:
            attack_names.add(result.attack)
            if not result.applicable:  # excluded from the ASR denominator
                continue
            key = (report.policy, report.suite, result.family)
            tally = buckets.setdefault(key, [0, 0])
            tally[0] += 1
            tally[1] += int(result.success)

    rows = [
        LeaderboardRow(
            policy=policy,
            suite=suite,
            family=family,
            attempts=attempts,
            successes=successes,
            asr=(successes / attempts if attempts else 0.0),
        )
        for (policy, suite, family), (attempts, successes) in buckets.items()
    ]
    # Rank by ASR (desc), then by keys for a stable, deterministic order.
    rows.sort(key=lambda r: (-r.asr, r.policy, r.suite, r.family))

    is_demo = all(report.policy == "stub" for report in reports) if reports else True
    return Leaderboard(
        is_demo=is_demo,
        rows=rows,
        examples=attack_examples(sorted(attack_names)),
    )


def validate_report(report: RunReport) -> list[str]:
    """Return a list of problems with a submitted run report (empty list == valid).

    Used by ``scripts/validate_submission.py`` (and CI) to gate leaderboard submissions:
    checks required fields, that the aggregate ASR/success counts are internally consistent
    with the per-episode results, and that the not-applicable accounting matches.
    """
    errors: list[str] = []
    if not report.policy:
        errors.append("missing 'policy'")
    if not report.suite:
        errors.append("missing 'suite'")
    if not report.results:
        errors.append("'results' is empty — nothing to score")
        return errors  # nothing else is meaningful without results
    if not 0.0 <= report.asr <= 1.0:
        errors.append(f"asr {report.asr} is outside [0, 1]")
    if not 0 <= report.successes <= report.attempts:
        errors.append(f"successes {report.successes} not in [0, attempts={report.attempts}]")
    applicable = sum(1 for r in report.results if r.applicable)
    if report.attempts != applicable:
        errors.append(f"attempts ({report.attempts}) != applicable results ({applicable})")
    applicable_successes = sum(1 for r in report.results if r.applicable and r.success)
    if report.successes != applicable_successes:
        errors.append(
            f"successes ({report.successes}) != applicable successes in results "
            f"({applicable_successes})"
        )
    for i, r in enumerate(report.results):
        if not r.attack:
            errors.append(f"results[{i}] missing 'attack'")
        if not r.family:
            errors.append(f"results[{i}] missing 'family'")
    return errors


def to_json(leaderboard: Leaderboard) -> str:
    """Serialise a leaderboard to a stable, indented JSON string (sorted keys)."""
    data = json.loads(leaderboard.model_dump_json())
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def load_leaderboard(path: Path) -> Leaderboard:
    """Load a :class:`Leaderboard` from a JSON file."""
    return Leaderboard.model_validate_json(path.read_text(encoding="utf-8"))


def build_leaderboard(run_paths: list[str], out_dir: Path) -> tuple[Path, Leaderboard]:
    """Find reports under ``run_paths``, aggregate, and write ``<out_dir>/leaderboard.json``.

    Raises:
        FileNotFoundError: if no ``report.json`` files are found.
    """
    report_paths = find_reports(run_paths)
    if not report_paths:
        raise FileNotFoundError(f"no {REPORT_JSON} files found under: {', '.join(run_paths)}")
    reports = [load_report(p) for p in report_paths]
    leaderboard = aggregate(reports)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / LEADERBOARD_JSON
    out_path.write_text(to_json(leaderboard), encoding="utf-8")
    return out_path, leaderboard


__all__ = [
    "LEADERBOARD_JSON",
    "LeaderboardRow",
    "AttackExample",
    "Leaderboard",
    "find_reports",
    "attack_examples",
    "aggregate",
    "to_json",
    "load_leaderboard",
    "build_leaderboard",
    "validate_report",
]
