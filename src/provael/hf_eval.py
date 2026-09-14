"""Hugging Face Community Evals: ``.eval_results/*.yaml`` entries and a benchmark ``eval.yaml``.

WHAT THE HUB EXPECTS (read from huggingface.co/docs/hub/eval-results on 14 September 2026, a
work-in-progress feature by its own banner). A model repo stores evaluation scores as YAML files
under ``.eval_results/``; each file is a LIST of entries::

    - dataset:
        id: <hub dataset id>        # required; the dataset must be registered as a Benchmark
        task_id: <task id>          # required; as defined in the dataset's eval.yaml
        revision: <hash>            # optional
      value: 0.412                  # required; the metric value
      verifyToken: <token>          # optional; only HF Jobs + inspect-ai runs can carry one
      date: "2025-01-15"            # optional; ISO-8601, defaults to the git commit time
      source: {url, name, user}     # optional; url required when present
      notes: "..."                  # optional; free text about the setup

A benchmark dataset carries an ``eval.yaml`` at its root: ``name``, ``description``,
``evaluation_framework`` (an enum the Hugging Face team maintains in ``huggingface.js`` —
``provael`` has to be added there by a pull request before a benchmark can name it), and
``tasks[]`` with an ``id`` each (``config`` and ``split`` optional). Results submitted by pull
request show as *community-provided* while the PR is open; *verified* is reserved for HF Jobs
runs with inspect-ai, which provael is not, so nothing here ever emits a ``verifyToken``.

WHAT PROVAEL PUBLISHES THERE, AND HOW IT STAYS HONEST. One entry per arm of the run — the
adversarial treatments, the benign baseline and the harmless-variation controls alike — with
``value`` the arm's episode-level unsafe fraction in ``[0, 1]`` and ``notes`` carrying the role,
the counts, the 95 % Wilson interval, the predicate state, the tool version and the checkpoint,
so a reader of the Hub page sees the floor beside the rate and never a bare number. ``date`` is
the execution manifest's end time when one is present and is otherwise omitted (the Hub falls
back to the commit time; this module never reads the clock). ``source.url`` is meant to be the
committed results directory on GitHub, so the entry points at an artifact, not at a claim. Arms
with no applicable episode are omitted rather than published as 0 — an N/A is not a score.

The task ids are stable and mechanical, ``<suite>--<attack>``, so a result for the same arm on a
different checkpoint lands on the same leaderboard; :func:`benchmark_eval_yaml` enumerates them
from the registry so the benchmark declares every arm provael can measure, not only the ones a
particular run happened to include.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from provael.calibration import wilson_ci
from provael.execution import ExecutionManifest
from provael.scoring.asr import semantic_role
from provael.types import RunReport

#: The ``evaluation_framework`` value a provael benchmark's ``eval.yaml`` names. It must exist in
#: huggingface.js ``packages/tasks/src/eval.ts`` before the Hub accepts the file; see the module
#: note and ``docs/`` for the pull request that adds it.
EVALUATION_FRAMEWORK = "provael"
#: Default filename under ``.eval_results/`` in a model repo.
EVAL_RESULTS_FILENAME = "provael.yaml"
#: The benchmark descriptor's filename at a dataset repo's root.
EVAL_YAML = "eval.yaml"


def task_id(suite: str, attack: str) -> str:
    """The stable leaderboard id for one arm on one suite: ``libero--roleplay``."""
    return f"{suite}--{attack}"


def _roles(report: RunReport) -> dict[str, str]:
    roles = {r.attack: semantic_role(r) for r in report.results}
    roles.update(report.roles)
    return roles


def _date_of(manifest: ExecutionManifest | None) -> str | None:
    """The manifest's end date (``YYYY-MM-DD``), or ``None`` — never the wall clock."""
    if manifest is None or not manifest.ended_at:
        return None
    return manifest.ended_at[:10]


def to_eval_results(
    report: RunReport,
    dataset_id: str,
    *,
    manifest: ExecutionManifest | None = None,
    source_url: str | None = None,
    source_name: str | None = None,
    user: str | None = None,
) -> list[dict[str, Any]]:
    """One ``.eval_results`` entry per measured arm of ``report`` against ``dataset_id``."""
    roles = _roles(report)
    predicate = "calibrated predicate" if report.calibrated else "default (uncalibrated) predicate"
    checkpoint = report.model or report.policy
    date = _date_of(manifest)
    entries: list[dict[str, Any]] = []
    for attack, stat in report.by_attack.items():
        if stat.attempts == 0:
            continue  # not applicable on this suite: unmeasured, never a 0
        lo, hi = wilson_ci(stat.successes, stat.attempts)
        role = roles.get(attack, "adversarial-treatment")
        entry: dict[str, Any] = {
            "dataset": {"id": dataset_id, "task_id": task_id(report.suite, attack)},
            "value": round(stat.successes / stat.attempts, 6),
            "notes": (
                f"{role}; unsafe {stat.successes}/{stat.attempts}; 95% Wilson CI "
                f"[{lo:.3f}, {hi:.3f}]; {predicate}; horizon {report.horizon}; "
                f"provael {report.tool_version}; checkpoint {checkpoint}; "
                "value is the episode-level unsafe fraction, read against the benign-control arm"
            ),
        }
        if date is not None:
            entry["date"] = date
        if source_url is not None:
            source: dict[str, str] = {"url": source_url}
            if source_name is not None:
                source["name"] = source_name
            if user is not None:
                source["user"] = user
            entry["source"] = source
        entries.append(entry)
    return entries


def to_eval_results_yaml(report: RunReport, dataset_id: str, **kwargs: Any) -> str:
    """The ``.eval_results`` file text for :func:`to_eval_results`."""
    return yaml.safe_dump(
        to_eval_results(report, dataset_id, **kwargs), sort_keys=False, allow_unicode=True
    )


def write_eval_results(report: RunReport, dataset_id: str, path: Path, **kwargs: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_eval_results_yaml(report, dataset_id, **kwargs), encoding="utf-8")
    return path


def benchmark_eval_yaml(suite: str, attacks: list[str], *, name: str, description: str) -> str:
    """A benchmark dataset's ``eval.yaml`` declaring one task per arm on ``suite``.

    ``attacks`` is the full list of arms the benchmark accepts results for — normally every
    registered attack plus the benign baseline — so the benchmark declares what provael can
    measure rather than what one run measured.
    """
    document = {
        "name": name,
        "description": description,
        "evaluation_framework": EVALUATION_FRAMEWORK,
        "tasks": [{"id": task_id(suite, attack)} for attack in attacks],
    }
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True)


__all__ = [
    "EVALUATION_FRAMEWORK",
    "EVAL_RESULTS_FILENAME",
    "EVAL_YAML",
    "benchmark_eval_yaml",
    "task_id",
    "to_eval_results",
    "to_eval_results_yaml",
    "write_eval_results",
]
