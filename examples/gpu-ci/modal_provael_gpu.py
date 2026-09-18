"""The scheduled real-model lane: one slice of a like-for-like campaign per run, on a Modal GPU.

Provael's core is CPU-tested in CI; the headline credibility move is a cheap, *real-model* job.
Modal (https://modal.com) spins up GPU containers on demand, runs the gated integration path, and
shuts down. `.github/workflows/gpu-scheduled.yml` runs this twice a week.

WHAT THIS LANE IS FOR, AND WHAT IT USED TO BE. Until 18 September 2026 each run was a canary: one
task, eight arms, two seeds, sixteen episodes. It kept `watch/freshness.json` fed and it could never
move `watch/publish-freshness.json`, for two reasons of arithmetic rather than budget:

* The published measurement is the largest body of real runs at one policy, suite and version
  (:func:`provael.watch.displacement`), and that body was 550 attempts over ten tasks at 0.32.0. A
  canary added fourteen attempts on one task per run, under a version bucket that reset every time
  a release re-pinned it. Twice a week for ever would have reached nothing.
* Even an accumulated canary body would have covered one task of ten. A single-task run of any
  length is a different measurement from a ten-task one, and the rule now says so.

So each run is now a SLICE of the campaign that would actually displace the published body: the
same checkpoint, the same suite, all ten `libero_object` tasks over time, every arm the published
body ran plus the harmless-variation controls, one seed per cell, one container per (task, seed)
cell. Slices accumulate at ONE pinned release until the body at that pin supersedes the published
one — covering every task it covered with at least as many attempts — and only then does the pin
advance. `tests/test_gpu_image_pin.py` enforces exactly that lifecycle.

THE COMMITTED TREE IS THE LEDGER. Which cells are done is read from `results/` on the driver
(every run is committed there by the workflow), so a run that loses a shard simply leaves that
cell for the next run, and a manual arm at the same pin (``modal_libero_suite.py``) is credited
rather than duplicated. No Volume, no resume file, no second copy of the plan.

WHAT IT COSTS, DERIVED BELOW RATHER THAN QUOTED. The measured anchors are the 0.32.0 suite (400
episodes in 15.4 L4-hours across ten 40-episode containers) and this lane's own canary (16 episodes
in ~37 min): both ~139 s/episode including container setup, which the `timing` stage put at ~174 s.
The constants below turn those into an expected and a ceiling cost per run and per month, and a
test asserts the ceiling fits the credit. Change ``TASKS_PER_RUN`` or ``ATTACKS`` and the bill
moves; the constants move with it, the docstring does not have to.

WHAT THIS CANNOT DO, STATED HERE SO NOBODY READS THE LANE AS A FIX FOR IT. A campaign of about
five seeds over ten tasks takes about thirteen runs, six and a half weeks, at this rate. Between
v0.32.0 (8 August 2026) and v0.41.2 (9 September 2026) this project shipped nine minor releases in
thirty-two days. At that cadence the body that displaces the published measurement lands roughly a
dozen minors behind the release current on the day it completes — past the two-release window it
is measured against. The lane makes the published measurement MOVE, repeatedly, and publishes how
far along it is; it cannot make it current. What would: a slower release cadence while a campaign
runs, or a larger credit. Neither is a code change, and neither is claimed here.

    pip install modal
    modal run examples/gpu-ci/modal_provael_gpu.py

WHY THE APP IS BUILT AT GLOBAL SCOPE. It used to be constructed inside `build_app()` so the module
would import without modal installed. That is exactly what broke it: `modal run` scans a module's
GLOBAL scope for an app and its entrypoint, so with everything local to a function it found none
and reported "has no functions or local entrypoints" — for 22 days, while the scheduled workflow
reported success. `modal_libero_suite.py` records the same trap at its own line 83. Importability
without modal bought nothing (no test asserted it) and cost the measurement the badge exists for.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
from collections.abc import Iterable

import modal

#: The LIBERO-finetuned checkpoint the published body was measured on. A slice against any other
#: checkpoint would be a different measurement and could not count toward displacing it.
CKPT = "HuggingFaceVLA/smolvla_libero"

#: The arms of every cell. The published body ran `none,instruction,visual,injection` on every task
#: and `benign_reword,nonsense_text` on every task in a separate control body; a slice runs all of
#: it in one cell, so the body this lane builds ships with its benign-FPR arm (`none`) and its
#: harmless-variation arm (`control`) in every shard rather than in a second campaign. `control`
#: expands to every registered harmless variation, and :data:`ARMS` below is asserted against the
#: registry by `tests/test_gpu_scheduled_plan.py`, so a control added later changes the cost here
#: rather than silently under-running the arm.
ATTACKS = "none,instruction,visual,injection,control"

#: Episodes per cell: `none` (1) + instruction (3) + visual (2) + injection (2) + control (4).
ARMS = 12

#: All ten libero_object tasks, in grid order. The published body covers exactly these, and
#: :func:`provael.watch.Campaign.covers` requires every one of them before size counts.
TASKS = tuple(f"libero_object/{i}" for i in range(10))

#: Cells per scheduled run, one container each. Four is the budget line, not a tuning knob: see
#: :data:`CEILING_USD_PER_MONTH` and the test that holds it under :data:`MONTHLY_CREDIT_USD`.
TASKS_PER_RUN = 4

#: Where the artifacts land on the runner, as ONE fact — each shard under `OUT_DIR/<task>/`. It
#: used to be the same string typed twice, once for `--out` and once for the mirror path, and the
#: workflow knew neither, so it went looking for `report.json` by modification time instead.
OUT_DIR = "runs/smolvla_libero"

#: The local entrypoint writes :data:`OUT_DIR` here, last, after the artifacts are on disk. The
#: workflow READS this file; it does not search.
#:
#: WHY THE SEARCH COULD NOT WORK. `gpu-scheduled.yml` ran
#: `find . -name report.json -newer gpu-scheduled-report.txt`, and that predicate is unsatisfiable
#: by construction: the entrypoint prints its closing line AFTER writing the artifacts, that line
#: goes through the same `tee` that produces the log, so the log's mtime is always newer than the
#: report it is announcing. On 4 September 2026 — the first scheduled run after #181's fix landed —
#: this lane reached a real policy, printed `Adversarial ASR: 33.3% (4/12)`, wrote three artifacts,
#: and the ledger step reported that it had produced none. Fourth time this lane has been unable to
#: report, after the nested app, the missing `pipefail`, and the discarded return value.
#:
#: The name is mirrored in `.github/workflows/gpu-scheduled.yml` and pinned by
#: `tests/test_modal_examples_are_runnable.py`, the same way every other cross-file contract in
#: this repo is held: copied deliberately, then guarded against drifting.
OUT_DIR_FILE = "gpu-scheduled-outdir.txt"

#: Shards that raised, one task per line, written beside :data:`OUT_DIR_FILE` so the workflow can
#: keep the shards that succeeded AND fail the job. Absent when every shard returned.
FAILED_SHARDS_FILE = "gpu-scheduled-failed-shards.txt"

#: The exact provael release every container installs.
#:
#: THIS IS A CAMPAIGN PIN, AND IT IS ALLOWED TO LAG. `tests/test_gpu_image_pin.py` used to require
#: it to equal `provael.__version__`, which is the right rule for a canary and the wrong rule for a
#: campaign: bumping it on every release reset the body this lane was building, so the lane could
#: accumulate toward nothing. The test now allows the pin to be the current version, OR the version
#: of the re-measurement in progress (the `challenger` in `watch/publish-freshness.json`), OR the
#: published measurement's version while it is still inside the release window. Every lane must
#: still pin the same version as every other — two lanes on different builds is the incident the
#: test was written for — and a pin that names none of the three fails, with the reason.
#:
#: So: do NOT bump this in a release PR while `publish-freshness.json` shows a challenger at this
#: version. Bump it when the body here has become the published measurement and a newer release
#: exists, and the test will say so in those words.
#:
#: THIS LANE WAS GENUINELY UNPINNED before 0.41.2, which is a different bug with a different
#: consequence. It installed `provael[lerobot]` with no constraint, so the canary measured whatever
#: PyPI served on the morning it ran — not reproducible in either direction, and it silently split
#: the two GPU lanes five releases apart while both looked healthy.
PROVAEL_PIN = "0.41.2"
PROVAEL = f"provael[lerobot]=={PROVAEL_PIN}"

# --------------------------------------------------------------------------- #
# cost, derived from measured anchors
# --------------------------------------------------------------------------- #

#: Modal's published L4 rate — the same figure `scripts/gpu_arm_plan.py` names.
L4_USD_PER_HOUR = 0.7992
#: Marginal seconds per episode once a container is up: (15.4 h x 3600 - 10 x 174 s) / 400.
EPISODE_SECONDS = 134
#: Container start to first step, measured by the suite's `timing` stage.
SETUP_SECONDS = 174
#: The per-container kill switch. It is the real cost ceiling: a hung container bills until it
#: fires regardless of what it was asked to do, so it is chosen from the budget, then checked to
#: hold the expected shard with headroom (see :data:`SHARD_SECONDS`).
SHARD_TIMEOUT_SECONDS = 3000
#: Tuesday and Friday: 104.3 runs a year, 8.69 a month.
RUNS_PER_MONTH = 104.3 / 12
#: The credit this lane shares with the manual arms in `gpu-arm.yml`.
MONTHLY_CREDIT_USD = 30.0

SHARD_SECONDS = SETUP_SECONDS + ARMS * EPISODE_SECONDS
EXPECTED_USD_PER_RUN = TASKS_PER_RUN * SHARD_SECONDS / 3600 * L4_USD_PER_HOUR
CEILING_USD_PER_RUN = TASKS_PER_RUN * SHARD_TIMEOUT_SECONDS / 3600 * L4_USD_PER_HOUR
EXPECTED_USD_PER_MONTH = EXPECTED_USD_PER_RUN * RUNS_PER_MONTH
CEILING_USD_PER_MONTH = CEILING_USD_PER_RUN * RUNS_PER_MONTH


def cost_table() -> str:
    """The lane's cost, derived, in the shape the workflow log prints before spending."""
    return "\n".join(
        [
            f"cells per run     {TASKS_PER_RUN} (one container each, {ARMS} episodes per cell)",
            f"expected per run  ${EXPECTED_USD_PER_RUN:.2f} "
            f"({TASKS_PER_RUN} x {SHARD_SECONDS} s x ${L4_USD_PER_HOUR}/L4-hour)",
            f"ceiling per run   ${CEILING_USD_PER_RUN:.2f} "
            f"({TASKS_PER_RUN} x {SHARD_TIMEOUT_SECONDS} s timeout)",
            f"expected / month  ${EXPECTED_USD_PER_MONTH:.2f} at {RUNS_PER_MONTH:.2f} runs",
            f"ceiling / month   ${CEILING_USD_PER_MONTH:.2f} of a ${MONTHLY_CREDIT_USD:.0f} credit",
        ]
    )


# --------------------------------------------------------------------------- #
# the plan: which cells this run measures, read from the committed tree
# --------------------------------------------------------------------------- #

#: Committed run artifacts, resolved from this file so the driver does not depend on its cwd.
RESULTS_DIR = pathlib.Path(__file__).resolve().parents[2] / "results"


def committed_reports(results_dir: pathlib.Path = RESULTS_DIR) -> list[dict[str, object]]:
    """Every readable `report.json` under ``results_dir``; an unreadable one is skipped."""
    reports: list[dict[str, object]] = []
    for path in sorted(results_dir.rglob("report.json")) if results_dir.is_dir() else []:
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(loaded, dict):
            reports.append(loaded)
    return reports


def cells_measured(reports: Iterable[dict[str, object]]) -> set[tuple[str, int]]:
    """(task, seed) cells already measured at :data:`PROVAEL_PIN` on this checkpoint and suite.

    A cell counts once any committed report at the pin ran it, whatever lane produced it: the body
    rule in :func:`provael.watch.displacement` sums every run at a version, so re-running a cell
    another arm already measured would count the same episodes twice. `report.json` carries the
    base ``seed`` and the ``seeds`` count, and episode ``i`` used ``seed + i``.
    """
    used: set[tuple[str, int]] = set()
    for r in reports:
        if (
            r.get("tool_version") != PROVAEL_PIN
            or r.get("model") != CKPT
            or r.get("policy") != "smolvla"
            or r.get("suite") != "libero"
        ):
            continue
        tasks = r.get("tasks")
        seed, seeds = r.get("seed"), r.get("seeds")
        if not isinstance(tasks, list) or not isinstance(seed, int) or not isinstance(seeds, int):
            continue
        for task in tasks:
            for s in range(seed, seed + seeds):
                used.add((str(task), s))
    return used


def next_cells(
    used: set[tuple[str, int]], count: int = TASKS_PER_RUN
) -> list[tuple[str, int]]:
    """The next ``count`` unmeasured cells of the grid, seed-major.

    Seed-major so that a partial campaign is always "the first k seeds of the protocol over all
    ten tasks" — the shape :func:`provael.combine.combine_reports` can pool and an evidence
    manifest can be built over — rather than a ragged edge of some tasks at many seeds. A slice may
    finish one seed and start the next; each shard carries its own ``--seed`` so that costs
    nothing.
    """
    cells: list[tuple[str, int]] = []
    seed = 0
    while len(cells) < count:
        cells.extend((task, seed) for task in TASKS if (task, seed) not in used)
        seed += 1
    return cells[:count]


def plan(results_dir: pathlib.Path = RESULTS_DIR) -> list[tuple[str, int]]:
    """This run's cells, from the committed tree. Pure: one tree always yields one plan."""
    return next_cells(cells_measured(committed_reports(results_dir)))


def _pin_commit() -> str | None:
    """Commit of the tag the container installs from PyPI, resolved on the driver machine.

    The container has no git checkout (it pip-installs the pinned release), so without this the
    execution manifest records `commit: null`. Resolved from `v{PROVAEL_PIN}` — the code that
    actually runs — never from the driver's HEAD, which may be a different commit. None when the
    driver's checkout has no tags; the manifest then records the gap rather than a guess.
    """
    try:
        out = subprocess.run(  # noqa: S603,S607 - fixed argv, no user input
            ["git", "rev-parse", "--verify", "--short", f"v{PROVAEL_PIN}^{{commit}}"],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = out.stdout.strip()
    return sha if out.returncode == 0 and sha else None


PIN_COMMIT = _pin_commit()


image = (
    modal.Image.debian_slim(python_version="3.12")
    # cmake/build-essential/git are load-bearing: lerobot[libero] pulls `egl_probe` and
    # `hf-egl-probe`, which build native wheels and fail with "CMake must be installed."
    # modal_libero_suite.py already carries this list; this file did not, and the failure was
    # invisible while the step could not fail.
    .apt_install(
        "libegl1-mesa-dev", "libgl1-mesa-glx", "libosmesa6-dev", "git", "cmake",
        "build-essential", "libglib2.0-0", "libsm6", "libxrender1", "libfontconfig1",
    )
    .pip_install(PROVAEL, "lerobot[libero]==0.5.1")
    .env({
        "MUJOCO_GL": "egl",
        "PYOPENGL_PLATFORM": "egl",
        "PROVAEL_INTEGRATION": "1",
        # Provenance for execution-manifest.json: the pinned release's commit (see _pin_commit).
        **({"PROVAEL_COMMIT": PIN_COMMIT} if PIN_COMMIT else {}),
    })
)
app = modal.App("provael-gpu-ci", image=image)


@app.function(gpu="L4", timeout=SHARD_TIMEOUT_SECONDS)
def redteam(task: str, seed: int) -> tuple[str, dict[str, str]]:
    """Measure ONE cell — every arm on one task at one seed — and return stdout AND the artifacts.

    RETURNING THE ARTIFACTS IS THE WHOLE POINT, not a convenience. This used to return stdout
    alone, so `report.json` was written inside the container and died with it. The workflow's
    ledger step looks for that file ON THE RUNNER, found nothing, emitted a warning and exited 0 —
    so every run from 30 Aug to 3 Sep 2026 reached a real policy, printed a real ASR, and recorded
    nothing while `watch/freshness.json` sat at 2026-08-09 and provael.com served STALE MEASUREMENT
    off the back of it. A lane that measures and discards is indistinguishable from a lane that
    never ran. See #181.

    One cell per container because the container's timeout is the cost ceiling and a cell is the
    unit a lost container costs: the next run re-plans it from the committed tree.
    """
    out = pathlib.Path(OUT_DIR) / task.replace("/", "_")
    cmd = [
        "provael", "attack", "--policy", "smolvla", "--suite", "libero",
        "--model", CKPT, "--tasks", task, "--attacks", ATTACKS, "--seeds", "1", "--horizon", "280",
        "--seed", str(seed), "--out", str(out),
    ]
    done = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if done.returncode != 0:
        # The reason travels back in the exception, not only the exit code: the driver lists
        # failed shards by this message, and "exit 1" would send someone to Modal's logs for it.
        tail = "\n".join(done.stderr.strip().splitlines()[-12:])
        raise RuntimeError(
            f"provael attack exited {done.returncode} on ({task}, seed {seed}):\n{tail}"
        )

    files = {
        str(path.relative_to(out)): path.read_text(encoding="utf-8")
        for path in sorted(out.rglob("*"))
        if path.is_file() and path.suffix in {".json", ".md"}
    }
    if not any(name.endswith("report.json") for name in files):
        raise RuntimeError(
            f"the cell ({task}, seed {seed}) produced no report.json under {out} — refusing to "
            f"return a success that records nothing. Files seen: {sorted(files) or 'none'}"
        )
    return done.stdout, files


@app.local_entrypoint()
def main() -> None:
    """Plan the slice from the committed tree, run it, WRITE the artifacts, then declare where.

    WRITING THE ARTIFACTS IS NOT ENOUGH, which is the lesson of the 4 September 2026 run. It wrote
    all three of them and the ledger step still recorded nothing, because the workflow was
    searching for `report.json` by modification time rather than being told the path. Announcing
    the location is therefore part of producing the measurement, not a courtesy: see
    :data:`OUT_DIR_FILE`.

    A shard that raises does not take the others with it. The shards that returned are written and
    declared, the ones that did not are listed in :data:`FAILED_SHARDS_FILE`, and the workflow
    keeps the former and fails on the latter — losing four good cells to one bad one would be the
    sixth version of the "measured and discarded" bug, and a green job with a missing cell would be
    the first version of a new one.
    """
    used = cells_measured(committed_reports())
    cells = next_cells(used)
    print(f"[plan] provael {PROVAEL_PIN} on {CKPT}: {len(used)} cell(s) committed at this pin")
    print(f"[plan] this run: {', '.join(f'{t} @ seed {s}' for t, s in cells)}")
    print(cost_table())

    out = pathlib.Path(OUT_DIR)
    written = 0
    failed: list[str] = []
    for (task, seed), result in zip(
        cells, redteam.starmap(cells, return_exceptions=True), strict=True
    ):
        if isinstance(result, BaseException):
            failed.append(f"{task} @ seed {seed}: {type(result).__name__}: {result}")
            continue
        stdout, files = result
        print(stdout)
        shard = out / task.replace("/", "_")
        for rel, text in files.items():
            dest = shard / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text, encoding="utf-8")
        written += 1

    if failed:
        pathlib.Path(FAILED_SHARDS_FILE).write_text("\n".join(failed) + "\n", encoding="utf-8")
        print(f"[slice] {len(failed)} shard(s) FAILED — listed in {FAILED_SHARDS_FILE}:")
        for line in failed:
            print(f"  {line}")
    if written == 0:
        raise SystemExit("every shard failed; nothing to declare, nothing to record")

    # LAST, and only once the artifacts are on disk: the file existing is the claim that they are
    # there, and its contents are where. A failed run leaves no file, so the ledger step fails
    # loudly instead of recording a measurement that was never produced.
    pathlib.Path(OUT_DIR_FILE).write_text(f"{OUT_DIR}\n", encoding="utf-8")
    print(
        f"wrote {written} shard(s) to {out}/ — path declared in {OUT_DIR_FILE}; "
        f"{len(used) + written} cell(s) at {PROVAEL_PIN} once this run is committed"
    )
