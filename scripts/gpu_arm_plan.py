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

AND ON STARTING SCENES (23 October 2026). Disjoint seeds were not enough. Under lerobot 0.5.1 a
LIBERO env picks each episode's starting scene from a reset counter the seed never reaches, and a
fresh env starts it at init state 0 (:data:`LEROBOT_RULE_VERSION` says where that was read). Every
task of the headline run, still uncalibrated, started in a fresh env, and so does every task's
fit, so the first fit rollout starts where the headline's first episode on that task did, whatever
``seed`` the stage passes. The step refuses that from the same records. Past each task's first
episode the records cannot say which scene an episode started from, and the refusal says what
they would need.

AND ON RECORDED INIT STATES (24 October 2026). From report schema 8 every episode records the init
state its reset loaded, read from the environment, and the stage can start each task's counter at
``init_state_offset``. Where the scored run's records carry ``init_state``, the fit's planned init
states are compared with the recorded ones, per task, and any overlap refuses; where they do not
(every committed run so far), the opening-scene rule above stands, and a fit that starts past the
opening scene is refused as unplaceable rather than waved through on the one scene that can be
placed.
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

#: How lerobot picks a LIBERO episode's starting scene, read from ``lerobot/envs/libero.py`` in the
#: 0.5.1 wheel, the version the ``[lerobot]`` extra pins (as it did at 0.41.2, the headline run's
#: release), rather than assumed:
#:
#: * ``self.init_state_id = self.episode_index`` (line 151), and ``_make_env_fns`` gives the one
#:   sub-env of an ``n_envs=1`` vector ``episode_index=0`` (lines 386-387). The LIBERO adapter
#:   builds exactly that, one env per task (``make_env(cfg, n_envs=1)``), reads the state each
#:   reset loaded back from the counter, and can move where a fresh env's counter starts
#:   (``init_state_offset``); it never picks a state per episode.
#: * ``reset`` loads ``self._init_states[self.init_state_id % len(self._init_states)]`` and then
#:   adds ``n_envs`` (lines 149 and 300-302): one state per reset, of the 50 each libero_object
#:   task's init file holds in the locked hf-libero 0.1.4.
#: * ``step`` calls ``self.reset()`` itself when an episode terminates (lines 331 and 341-348), so
#:   an episode that ends in task success uses up a second state before the next reset.
#: * The seed reaches ``self._env.seed(seed)`` (line 298) and nothing that picks the state.
#:
#: ``tests/test_gpu_arm_seed_overlap.py`` fails if the pin moves or the adapter starts choosing the
#: state per episode, because either would make this the wrong rule.
LEROBOT_RULE_VERSION = "0.5.1"

#: The init state a fresh LIBERO env's first reset loads, by the rule above.
FIRST_INIT_STATE = 0

#: How many fixed initial states each libero_object task has: every init file in the locked
#: hf-libero 0.1.4 (``libero/libero/init_files/libero_object/*.pruned_init``) holds a (50, 110)
#: array. The counter is taken modulo this, so a fit window past 49 wraps to the start.
INIT_STATES = 50

#: The newest provael RELEASE whose ``calibrate`` has no ``--init-state-offset`` (it is on main
#: since 24 October 2026). A fact about a past release, so it never needs updating: the GPU image
#: installs ``PROVAEL_PIN``, and while that is at or below this version a container handed the flag
#: would exit on an unknown option after billing had started, so the plan step refuses first.
LAST_RELEASE_WITHOUT_OFFSET = "0.46.0"


class _Inert:
    """Absorbs every attribute access, call and decoration, and returns more of itself."""

    def __getattr__(self, _name: str) -> _Inert:
        return self

    def __call__(self, *_args: Any, **_kwargs: Any) -> _Inert:
        return self


def _example() -> types.ModuleType:
    """The example module, executed with an inert ``modal`` so its computed values resolve."""
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
    return module


def stages() -> dict[str, dict[str, str]]:
    """The example's own ``STAGES`` dict, with computed values resolved."""
    result: dict[str, dict[str, str]] = _example().STAGES
    if not result:
        raise SystemExit(f"{EXAMPLE} defines no STAGES")
    return result


def image_pin() -> str:
    """The provael release the GPU image installs (the example's ``PROVAEL_PIN``)."""
    return str(_example().PROVAEL_PIN)


def _release(version: str) -> tuple[int, ...]:
    """``0.46.0`` as ``(0, 46, 0)``; the image pin is exact (``tests/test_gpu_image_pin.py``)."""
    return tuple(int(part) for part in version.split("."))


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


def _task_span(tasks: list[str]) -> str:
    """``libero_object/0-9`` for numbered tasks of one suite, otherwise the tasks listed."""
    parts = [task.rpartition("/") for task in tasks]
    suites = {suite for suite, _, _ in parts}
    if len(suites) == 1 and all(sep and number.isdigit() for _, sep, number in parts):
        return f"{suites.pop()}/{_span(sorted(int(number) for _, _, number in parts))}"
    return ", ".join(tasks)


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


def headline_first_scenes(root: Path = ROOT) -> tuple[str, dict[str, int]]:
    """Each task the headline run scored, and the init state its first episode started from.

    A run's records are in plan order, and a task's first planned episode is that task's first
    reset in whichever process measured it, a resumed one included, so by the rule above it started
    at :data:`FIRST_INIT_STATE`. Nothing after it can be placed from the records: they carry no
    starting scene, and a resumed shard restarts the counter without a trace in ``report.json``.
    """
    run = json.loads((root / BOARD_SOURCE).read_text(encoding="utf-8"))["run"]
    first: dict[str, int] = {}
    for report in sorted((root / run).glob("*/report.json")):
        for record in json.loads(report.read_text(encoding="utf-8"))["results"]:
            first.setdefault(str(record["task"]), FIRST_INIT_STATE)
    return run, first


def headline_recorded_states(root: Path = ROOT) -> dict[str, set[int]]:
    """The init states the headline run recorded, for each task whose every record carries one.

    ``init_state`` is on each record from report schema 8, read from the environment after the
    reset, so a resumed shard is placed as it actually ran rather than as the episode order would
    suggest. A task with any record that lacks it is left out: part of its scenes would be
    unknown, and an unknown scene is not a clear one.
    """
    run = json.loads((root / BOARD_SOURCE).read_text(encoding="utf-8"))["run"]
    states: dict[str, set[int]] = {}
    partial: set[str] = set()
    for report in sorted((root / run).glob("*/report.json")):
        for record in json.loads(report.read_text(encoding="utf-8"))["results"]:
            task, state = str(record["task"]), record.get("init_state")
            if isinstance(state, int) and not isinstance(state, bool):
                states.setdefault(task, set()).add(state)
            else:
                partial.add(task)
    return {task: found for task, found in states.items() if task not in partial}


def fit_init_states(cfg: dict[str, str]) -> list[int]:
    """Every init state a `calibrate` stage's fit rollouts can start from, on each task.

    Each task's counter starts at the stage's ``init_state_offset`` (0 when absent) in a fresh env.
    Fit rollout ``j`` follows ``j`` earlier resets plus one for each earlier rollout that ended in
    task success, so it starts between ``offset + j`` and ``offset + 2j``; which one depends on
    outcomes nobody has seen yet, so the plan covers the whole range. Only the fit split is
    planned: the tuning split and the attacked arm come after it and walk on from there.
    """
    offset = int(cfg.get("init_state_offset", "0"))
    steps = 2 * len(calibrate_splits(cfg)["fit"]) - 1
    return sorted({(offset + step) % INIT_STATES for step in range(steps)})


def _ranges(states: list[int]) -> str:
    """``0-7,45-49``: sorted init states, consecutive runs collapsed."""
    runs: list[list[int]] = []
    for state in states:
        if runs and state == runs[-1][-1] + 1:
            runs[-1].append(state)
        else:
            runs.append([state])
    return ",".join(f"{run[0]}-{run[-1]}" if len(run) > 1 else str(run[0]) for run in runs)


def _clearing_offset(cfg: dict[str, str], recorded: dict[str, set[int]]) -> int | None:
    """The smallest ``init_state_offset`` whose fit window misses every recorded state, if any."""
    for offset in range(INIT_STATES):
        window = set(fit_init_states({**cfg, "init_state_offset": str(offset)}))
        if not any(window & found for found in recorded.values()):
            return offset
    return None


def scene_check(cfg: dict[str, str], root: Path = ROOT) -> tuple[bool, str]:
    """Whether a `calibrate` stage's fit can start on a scene the headline run scored, as Markdown.

    Per task. Where the run's records carry ``init_state``, the fit's planned init states
    (:func:`fit_init_states`) are compared with the recorded ones and any overlap refuses. Where
    they do not, only each task's first episode can be placed, at :data:`FIRST_INIT_STATE`
    (:func:`headline_first_scenes`): a fit that starts there too is refused as #339 refused it, and
    a fit that starts elsewhere is refused as unplaceable, since nothing shows its states are clear.
    A non-zero offset also needs a GPU image whose provael takes ``--init-state-offset``.
    """
    run, first = headline_first_scenes(root)
    recorded = headline_recorded_states(root)
    offset = int(cfg.get("init_state_offset", "0"))
    planned = fit_init_states(cfg)
    tasks = cfg["tasks"].split(",")
    known = [task for task in tasks if task in recorded]
    unplaced = [task for task in tasks if task in first and task not in recorded]
    if offset == 0:
        start = (
            "Each task's fit starts in a fresh env and rolls its fit split first, so its first "
            f"rollout starts at init state {FIRST_INIT_STATE} whatever `seed` is."
        )
    else:
        start = (
            f"This stage starts each task's counter at init state {offset} (`init_state_offset`) "
            "and rolls its fit split first, so its first rollout starts there whatever `seed` is."
        )
    opening = (
        f"Under lerobot {LEROBOT_RULE_VERSION} a LIBERO env picks each episode's starting scene "
        "from a reset counter the seed never reaches: a fresh env loads init state "
        f"{FIRST_INIT_STATE} first and moves one state on per reset, two after an episode that "
        f"ends in task success. {start}"
    )
    # The tasks the run scored without recording init states: #339's rule and wording cover them.
    scored = sorted(task for task in first if task not in recorded)
    if scored:
        opening += (
            f" `{run}` scored {_task_span(scored)}, and its first episode on each started at "
            f"init state {FIRST_INIT_STATE} for the same reason."
        )
    lines = ["#### Starting scenes", "", opening]
    refusals: list[str] = []
    if unplaced and offset == 0:
        refusals.append(
            "**Refused:** the fit would start at the init state the headline's first episode "
            f"started from on {_task_span(unplaced)}. No `seed` moves it (#136). Nothing has been "
            "billed."
        )
    elif unplaced:
        refusals.append(
            f"**Refused:** the fit starts at init state {offset}, past the opening scene, and the "
            f"headline's records cannot place its later scenes on {_task_span(unplaced)}, so "
            f"nothing shows that init states {_ranges(planned)} are clear of them (#136). Nothing "
            "has been billed."
        )
    if known:
        lines += [
            "",
            f"`{run}` recorded the init state each episode started from on {_task_span(known)}. "
            f"The fit's rollouts can start from init states {_ranges(planned)} on each task: "
            f"{offset} first, then one or two states on per rollout. The tuning split and the "
            "attacked arm follow the fit and are not planned here.",
        ]
        clash = {task: sorted(set(planned) & recorded[task]) for task in known}
        where = "; ".join(f"{_ranges(found)} on {task}" for task, found in clash.items() if found)
        if where:
            clear = _clearing_offset(cfg, {task: recorded[task] for task in known})
            hint = (
                f"An `init_state_offset` of {clear} would miss every recorded state on these "
                "tasks."
                if clear is not None
                else f"No offset misses them all: no window of {len(planned)} consecutive states "
                "falls between the recorded ones."
            )
            refusals.append(
                "**Refused:** the fit's planned init states overlap the ones the run recorded: "
                f"{where} (#136). {hint} Nothing has been billed."
            )
    if offset and _release(image_pin()) <= _release(LAST_RELEASE_WITHOUT_OFFSET):
        refusals.append(
            f"**Refused:** the GPU image installs provael {image_pin()}, and no release up to "
            f"{LAST_RELEASE_WITHOUT_OFFSET} takes `--init-state-offset`, so every container would "
            "exit on an unknown option after billing had started. Move `PROVAEL_PIN` to a release "
            "that has it first. Nothing has been billed."
        )
    if refusals:
        for refusal in refusals:
            lines += ["", refusal]
    elif known:
        lines += ["", "No shared scene: none of the fit's planned init states is one the run "
                  "recorded on these tasks."]
    else:
        lines += ["", "No shared scene: this calibration fits no task the headline run scored."]
    if scored:
        lines += [
            "",
            "Past each task's first episode the headline's scenes cannot be read from its records: "
            "they carry no starting scene, and a resumed shard restarts the counter without a "
            "trace in `report.json`. Each record would need the init state its reset loaded.",
        ]
    return not refusals, "\n".join(lines)


def seed_check(stage: str, cfg: dict[str, str], root: Path = ROOT) -> tuple[bool, str]:
    """Whether a dispatch may run as far as its seeds go, and the Markdown that says why.

    Only `calibrate` fits anything, so every other stage passes with nothing to say. Any seed the
    stage rolls out that the headline run scored refuses the dispatch, whichever split it lands in.

    It compares SEEDS, then STARTING SCENES through :func:`scene_check`. Under lerobot 0.5.1 LIBERO
    picks each episode's starting scene from a reset counter, not from the seed, so disjoint seeds
    are necessary and not sufficient.
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
    scenes_ok, scenes = scene_check(cfg, root)
    lines += ["", scenes]
    return not where and scenes_ok, "\n".join(lines)


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
