# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Every committed LIBERO run used its task suite's horizon, and the constant says where it comes from.

"Horizon 280" shipped in the recipes, the reports and the findings from June 2026 with no stated
reason. It has one: OpenVLA's LIBERO evaluator gives each task suite a step budget just above its
longest training demonstration (``experiments/robot/libero/run_libero_eval.py``), and every
committed run matches it — 280 on libero_object, 220 on libero_spatial, 300 on libero_goal, 520 on
libero_10. :data:`provael.suites.libero.LIBERO_HORIZON` records those budgets once; this holds the
committed runs and the shipped recipe to them, so a run at the wrong budget cannot sit beside the
others looking comparable.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from provael.recipes import RECIPES
from provael.suites.libero import LIBERO_HORIZON

ROOT = Path(__file__).resolve().parent.parent


def _libero_reports() -> list[tuple[str, int, set[str]]]:
    """(report path, horizon, task suites it ran) for every committed LIBERO report."""
    out = []
    for path in sorted(ROOT.glob("results/**/report.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("suite") != "libero":
            continue
        tasks = {str(t) for t in report.get("tasks") or []}
        suites = {m.group(1) for t in tasks if (m := re.match(r"(libero_[a-z0-9]+)/", t))}
        out.append((str(path.relative_to(ROOT)), report.get("horizon"), suites))
    return out


def test_every_committed_libero_run_uses_its_suites_horizon() -> None:
    reports = _libero_reports()
    assert reports, "no committed LIBERO report found; the sweep must have stopped matching"
    wrong = [
        f"{path}: horizon {horizon}, but {suite} runs at {LIBERO_HORIZON[suite]}"
        for path, horizon, suites in reports
        for suite in suites
        if suite in LIBERO_HORIZON and horizon != LIBERO_HORIZON[suite]
    ]
    unknown = sorted({s for _, _, suites in reports for s in suites} - set(LIBERO_HORIZON))
    assert not unknown, f"a committed run used a LIBERO task suite with no budget recorded: {unknown}"
    assert not wrong, "a committed LIBERO run used another suite's horizon:\n  " + "\n  ".join(wrong)


def test_the_redirect_recipe_runs_at_the_object_budget() -> None:
    """The EAI04 recipe says it is the published SmolVLA x LIBERO-Object protocol; its horizon must
    be that suite's budget, read from the constant rather than typed."""
    assert RECIPES["eai04-redirect"].config["horizon"] == LIBERO_HORIZON["libero_object"] == 280
