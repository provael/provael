# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Print what one GPU arm will cost, BEFORE `.github/workflows/gpu-arm.yml` spends it.

WHY THIS IS A SCRIPT AND NOT A HEREDOC IN THE WORKFLOW. It started as one, and it was wrong twice
in the same twenty lines: ``STAGES`` is an *annotated* assignment so walking for ``ast.Assign``
found nothing and raised ``StopIteration``, and ``ast.Dict`` exposes ``.keys``/``.values`` rather
than ``.items``. Both would have surfaced only on a dispatch, in the one step whose entire job is
to speak before money is spent. This repo already draws that line — the Action's gate logic lives
in ``scripts/action/`` rather than inside ``action.yml`` "lifted out specifically so it can be
tested" — and a cost estimate is exactly the kind of logic that must not be first exercised in
production.

WHY IT EXECUTES THE EXAMPLE INSTEAD OF PARSING IT. ``STAGES`` holds ``"tasks": ALL_TASKS``, and
``ALL_TASKS`` is computed (``",".join(f"libero_object/{i}" for i in range(10))``), so no amount of
``ast.literal_eval`` recovers it — a parser would have to re-implement the module to read it. So
the module is executed with a **stub modal** injected instead: nothing here needs the real client,
the CPU lane does not have it, and a stub keeps this runnable (and therefore testable) wherever
``provael``'s own tests run. The stub is inert — attribute access and calls return more stub — so
``modal.App(...)``, the image chain and the ``@app.function`` decorators all evaluate to nothing.

WHY IT ALSO REFUSES. A `calibrate` dispatch that rolls out seeds the published headline run scored
would fit the envelope on the episodes a calibrated re-run then scores its benign floor on. On 19
October 2026 the stage's fit split was seeds 0-6 and the published headline, still uncalibrated,
had scored 0-4 (#136). This step already runs before anything bills, so it checks the seeds here
and exits non-zero, which stops the workflow before the arm starts. The headline's seeds are read
from its own records; the split comes from :mod:`provael.calibration`, so this step needs provael
installed, which the workflow does first.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import types
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "gpu-ci" / "modal_libero_suite.py"

#: Modal's own published L4 rate. The ceiling below is only as honest as this number, so it lives
#: in one place and is named — `modal_libero_suite.py` quotes the same figure in its cost table.
L4_USD_PER_HOUR = 0.7992

#: The signed board's pointer to the committed run the published headline rests on. Read, not
#: retyped, so the day a calibrated re-run becomes the board's source the seed check follows it.
BOARD_SOURCE = Path("leaderboard") / "results" / "source.json"


class _Inert:
    """Absorbs every attribute access, call and decoration, and returns more of itself."""

    def __getattr__(self, _name: str) -> _Inert:
        return self

    def __call__(self, *_args: Any, **_kwargs: Any) -> _Inert:
        return self


def stages() -> dict[str, dict[str, str]]:
    """The example's own ``STAGES`` dict, with computed values resolved."""
    stub = types.ModuleType("modal")
    for name in ("App", "Image", "Volume", "NetworkFileSystem", "Secret", "Mount"):
        setattr(stub, name, _Inert())
    saved = sys.modules.get("modal")
    sys.modules["modal"] = stub
    # The example raises SystemExit at import if PROVAEL_STAGE names an unknown stage. `timing` is
    # its own default and always valid, so set it rather than inheriting whatever the caller has.
    saved_stage = os.environ.get("PROVAEL_STAGE")
    os.environ["PROVAEL_STAGE"] = "timing"
    try:
        # The same importlib idiom `tests/test_check_changelog_entry.py` uses to reach a script
        # that is not on the import path.
        spec = importlib.util.spec_from_file_location("modal_libero_suite", EXAMPLE)
        if spec is None or spec.loader is None:  # pragma: no cover - only on a deleted example
            raise SystemExit(f"cannot load {EXAMPLE}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if saved is None:
            sys.modules.pop("modal", None)
        else:
            sys.modules["modal"] = saved
        if saved_stage is None:
            os.environ.pop("PROVAEL_STAGE", None)
        else:
            os.environ["PROVAEL_STAGE"] = saved_stage
    result: dict[str, dict[str, str]] = module.STAGES
    if not result:
        raise SystemExit(f"{EXAMPLE} defines no STAGES")
    return result


def plan(stage: str) -> str:
    """A Markdown summary of one stage: its config, its shard count and its hard cost ceiling."""
    every = stages()
    if stage not in every:
        raise SystemExit(f"unknown stage {stage!r}; the example defines {sorted(every)}")
    cfg = every[stage]
    shards = len(cfg["tasks"].split(","))
    hours = int(cfg["timeout"]) / 3600
    lines = [f"### Arm: `{stage}`", "", "| field | value |", "| --- | --- |"]
    lines += [f"| `{key}` | `{value}` |" for key, value in cfg.items()]
    lines += [
        f"| shards | {shards} (one container per task) |",
        f"| **hard ceiling** | **~${shards * hours * L4_USD_PER_HOUR:,.2f}** "
        f"({shards} x {hours:.2f} h x ${L4_USD_PER_HOUR}/L4-hour) |",
        "",
        "The ceiling is what hung containers bill regardless of what they were asked to do — it is "
        "the number that matters, not the expected spend. The stage's own comment in "
        "`examples/gpu-ci/modal_libero_suite.py` derives the expected figure.",
    ]
    return "\n".join(lines)


def _span(seeds: list[int]) -> str:
    """``0-6`` for a run of consecutive seeds, otherwise the seeds comma-separated."""
    if len(seeds) > 1 and seeds == list(range(seeds[0], seeds[-1] + 1)):
        return f"{seeds[0]}-{seeds[-1]}"
    return ",".join(str(seed) for seed in seeds)


def headline_seeds(root: Path = ROOT) -> tuple[str, list[int], int]:
    """The headline run's directory, every seed its episode records used, and how many records.

    The seeds come from the shards' own ``report.json`` records, which are what was measured, not
    from the run's README or a constant. A run with no records refuses rather than passes: a check
    that cannot see the headline's seeds has not shown that they are clear.
    """
    run = json.loads((root / BOARD_SOURCE).read_text(encoding="utf-8"))["run"]
    records = [
        record
        for report in sorted((root / run).glob("*/report.json"))
        for record in json.loads(report.read_text(encoding="utf-8"))["results"]
    ]
    if not records:
        raise SystemExit(f"{run} has no episode records under */report.json to read seeds from")
    return run, sorted({int(record["seed"]) for record in records}), len(records)


def calibrate_splits(cfg: dict[str, str]) -> dict[str, list[int]]:
    """The seeds a `calibrate` stage rolls out, split the way `provael calibrate` splits them.

    The stage passes no ``--split``, so the command's three-way default applies. The split is
    imported rather than restated here, because a second copy of it is the kind of drift this
    check exists to catch.
    """
    from provael.calibration import split_seeds_three

    base, count = int(cfg["seed"]), int(cfg["seeds"])
    fit, tuning, held_out = split_seeds_three(list(range(base, base + count)))
    return {"fit": fit, "tuning": tuning, "eval": held_out}


def seed_check(stage: str, cfg: dict[str, str], root: Path = ROOT) -> tuple[bool, str]:
    """Whether a dispatch may run as far as its seeds go, and the Markdown that says why.

    Only `calibrate` fits anything, so every other stage passes with nothing to say. Any seed the
    stage rolls out that the headline run scored refuses the dispatch, whichever split it lands in.

    It compares SEEDS. Under lerobot 0.5.1 LIBERO picks each episode's starting scene from a reset
    counter, not from the seed, so disjoint seeds are necessary here and not yet sufficient.
    """
    if stage != "calibrate":
        return True, ""
    run, scored, n_records = headline_seeds(root)
    splits = calibrate_splits(cfg)
    rolled = sorted(seed for seeds in splits.values() for seed in seeds)
    lines = [
        "#### Seeds",
        "",
        f"The stage rolls out seeds {_span(rolled)}, split as `provael calibrate` splits them: "
        + ", ".join(f"{name} {_span(seeds)}" for name, seeds in splits.items())
        + f". `{run}`, the run `{BOARD_SOURCE.as_posix()}` names, scored seeds {_span(scored)} "
        f"in its {n_records} episode records.",
        "",
    ]
    clash = {name: sorted(set(seeds) & set(scored)) for name, seeds in splits.items()}
    where = "; ".join(
        f"{_span(seeds)} in the {name} split" for name, seeds in clash.items() if seeds
    )
    if where:
        lines.append(
            f"**Refused:** the headline's seeds fall inside this calibration ({where}). A "
            "calibrated re-run on them would score its benign floor on episodes the envelope was "
            "fitted on. Move the fit (`seed` in this stage) or the re-run off those seeds first "
            "(#136). Nothing has been billed."
        )
    else:
        lines.append("No overlap: this calibration rolls out no seed the headline run scored.")
    lines += [
        "",
        "This compares seeds. Under lerobot 0.5.1 LIBERO picks each episode's starting scene from "
        "a reset counter rather than the seed, so disjoint seeds do not yet mean disjoint scenes.",
    ]
    return not where, "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print a GPU arm's plan and cost ceiling.")
    parser.add_argument("stage", help="stage name, as defined in the example's STAGES")
    stage = parser.parse_args(argv).stage
    print(plan(stage))
    ok, seeds = seed_check(stage, stages()[stage])
    if seeds:
        print(f"\n{seeds}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
