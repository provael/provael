"""Run the real SmolVLA x LIBERO red-team path on a Modal GPU — fork-safe, ~$0.49/run.

Provael's core is CPU-tested in CI; the headline credibility move is a cheap, *real-model* job.
Modal (https://modal.com) spins up a GPU container on demand, runs the gated integration path,
and shuts down. Pair with examples/gpu-ci/modal-gpu-tests.yml, which only triggers on a
`gpu-tests` PR label so fork PRs can't spend.

WHAT THAT NUMBER COSTS, AND WHY IT USED TO BE WRONG. This file claimed ~$0.02/run and was never
recomputed after the run grew. `ATTACKS` expands to EIGHT arms (one baseline, three instruction,
two visual, two injection) and `task_ids` defaults to a single task, so the old `--seeds 10` was
80 episodes. The repo's measured anchor is 400 episodes in 15.4 L4-hours, ~139 s/episode, so 80
episodes is ~3 hours against the 1h `timeout` below: it could never finish, and every scheduled
run burned the full hour for nothing. Two seeds is 16 episodes, ~37 min, ~$0.49 at Modal's
$0.7992/L4-hour. Change SEEDS and you change the bill — recompute it here rather than trusting
this line.

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

import modal

CKPT = "HuggingFaceVLA/smolvla_libero"
ATTACKS = "none,instruction,visual,injection"

#: Seeds per arm. 8 arms x SEEDS x 1 task episodes, at ~139 s/episode measured, against the 1h
#: container timeout below. Two fits in ~37 min with real headroom; three is ~56 min and would
#: race the cap. The freshness badge this feeds carries a timestamp and no rate, so this is a
#: canary that the real-model path still runs — not a measurement, and not a published number.
SEEDS = "2"

#: Where the artifacts land, as ONE fact. It used to be the same string typed twice — once for the
#: CLI's `--out` inside the container, once for the mirror path in the local entrypoint — and the
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
    .pip_install("provael[lerobot]", "lerobot[libero]==0.5.1")
    .env({"MUJOCO_GL": "egl", "PYOPENGL_PLATFORM": "egl", "PROVAEL_INTEGRATION": "1"})
)
app = modal.App("provael-gpu-ci", image=image)


@app.function(gpu="L4", timeout=3600)
def redteam() -> tuple[str, dict[str, str]]:
    """Run the gated real-model path and return the CLI's stdout AND its artifacts.

    RETURNING THE ARTIFACTS IS THE WHOLE POINT, not a convenience. This used to return stdout
    alone, so `report.json` was written inside the container and died with it. The workflow's
    ledger step looks for that file ON THE RUNNER, found nothing, emitted a warning and exited 0 —
    so every scheduled run since the Modal credentials landed on 30 Aug 2026 reached a real policy,
    printed a real ASR, and recorded nothing. `watch/freshness.json` sat at 2026-08-09 while the job
    reported success twice a week, and provael.com served STALE MEASUREMENT off the back of it.

    A lane that measures and discards is indistinguishable from a lane that never ran. See #181.

    No Volume or NetworkFileSystem: the artifacts are small JSON and Markdown, they cross back in
    the return value, and adding a storage resource would be one more thing to provision before the
    measurement works.
    """
    import pathlib
    import subprocess

    out = pathlib.Path(OUT_DIR)
    cmd = [
        "provael", "attack", "--policy", "smolvla", "--suite", "libero",
        "--model", CKPT, "--attacks", ATTACKS, "--seeds", SEEDS, "--horizon", "280",
        "--seed", "0", "--out", str(out),
    ]
    stdout = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout

    files = {
        str(path.relative_to(out)): path.read_text(encoding="utf-8")
        for path in sorted(out.rglob("*"))
        if path.is_file() and path.suffix in {".json", ".md"}
    }
    if not any(name.endswith("report.json") for name in files):
        raise RuntimeError(
            f"the run produced no report.json under {out} — refusing to return a success that "
            f"records nothing. Files seen: {sorted(files) or 'none'}"
        )
    return stdout, files


@app.local_entrypoint()
def main() -> None:
    """Print the run, WRITE ITS ARTIFACTS to the runner, then declare where they went.

    WRITING THE ARTIFACTS IS NOT ENOUGH, which is the lesson of the 4 September 2026 run. It wrote
    all three of them and the ledger step still recorded nothing, because the workflow was
    searching for `report.json` by modification time rather than being told the path. Announcing
    the location is therefore part of producing the measurement, not a courtesy: see
    :data:`OUT_DIR_FILE`.
    """
    import pathlib

    stdout, files = redteam.remote()
    print(stdout)

    out = pathlib.Path(OUT_DIR)
    for rel, text in files.items():
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")

    # LAST, and only once the artifacts are on disk: the file existing is the claim that they are
    # there, and its contents are where. A failed run leaves no file, so the ledger step fails
    # loudly instead of recording a measurement that was never produced.
    pathlib.Path(OUT_DIR_FILE).write_text(f"{OUT_DIR}\n", encoding="utf-8")
    print(f"wrote {len(files)} artifact(s) to {out}/ — path declared in {OUT_DIR_FILE}")
