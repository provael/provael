"""Run the FULL libero_object suite on a rented Modal GPU. Two stages, on purpose.

WHY THIS EXISTS SEPARATELY FROM modal_provael_gpu.py. That script runs the suite's default task set,
which is `task_ids=(0,)` — a single task. Every committed real-policy result to date therefore
measures one task, and "one task at 10/10" is consistent with a suite-wide rate anywhere from 10% to
100%. That interval is the largest unconstrained quantity in the project and no amount of extra
seeds narrows it. Only more TASKS do.

WHY LIBERO CANNOT RUN ON A MAC, so this is not optional. lerobot declares
`hf-libero; sys_platform == "linux"`, so the LIBERO extra does not install on darwin at any price. A
rented Linux GPU is the cheapest path, not a luxury.

FOUR STAGES, IN COST ORDER, AND THE ORDER IS THE POINT.

    timing   1 task  x 1 arm  x 1 seed  =    1 episode   MEASURED: 174s total
    pilot    2 tasks x 2 arms x 2 seeds =    8 episodes
    probe   10 tasks x 4 arms x 3 seeds =  120 episodes
    full    10 tasks x 4 arms x 30 ep   = 1200 episodes

THE ESTIMATES IN THIS DOCSTRING USED TO BE GUESSES AND THE GUESSES WERE WRONG. It claimed the probe
was "~210 episodes, ~20 min, ~$0.30". The episode count was wrong (120, not 210) and the duration
was wrong by enough that the probe hit its own 3600s timeout having produced nothing. Do not restore
a projected cost here that was not measured by the stage below it.

What IS measured, from the `timing` run: setup plus one benign episode on task 0 = 174s, and that
episode ran 134 of 280 steps because it SUCCEEDED (LIBERO ends an episode on success). Two
consequences the later stages depend on: setup is bundled into that 174s and cannot be separated
from it by a single datum, and a failed episode runs the full horizon so it costs roughly twice a
successful one. Cost therefore depends on the ASR being measured, which is why `pilot` exists —
eight episodes give the slope that one episode cannot.

`full`'s shape is chosen, not arbitrary. 10 seeds x 3 repeats separates INITIAL-STATE variation from
POLICY stochasticity, which `--episodes-per-seed` made computable for the first time; n=30 per cell
puts an attack down to ~30% ASR above the detection floor once Holm correction is applied across the
screen. Whether it is affordable is a separate question from whether it is well-designed.

    modal run examples/gpu-ci/modal_libero_suite.py                       # timing, the default
    PROVAEL_STAGE=pilot modal run examples/gpu-ci/modal_libero_suite.py   # the slope
    PROVAEL_STAGE=probe modal run examples/gpu-ci/modal_libero_suite.py   # direction, 10 tasks
    PROVAEL_STAGE=full  modal run examples/gpu-ci/modal_libero_suite.py   # the real run

EVERYTHING HERE IS AT MODULE SCOPE, and that is a hard Modal requirement rather than a style choice.
`@app.function` rejects a function defined inside another function unless `serialized=True`. The
first version of this file wrapped the app in a `build_app()` factory — copying the pattern the
sibling `modal_provael_gpu.py` uses — and `modal run` refused it outright:

    InvalidError: The `@app.function` decorator must apply to functions in global scope

Do not reintroduce the factory. (The sibling script has the same defect and has therefore almost
certainly never been executed, which is worth knowing before trusting it.) The cost of module scope
is that `import modal` runs on import, so this file is only readable where modal is installed. That
is true of every Modal entrypoint.

The stage is an environment variable rather than a `--stage` flag for a related reason: `modal run`
resolves the app at import time, before any entrypoint argument is parsed, so the image, the GPU and
the timeout must all be fixed before Modal will accept the module.
"""

from __future__ import annotations

import json
import os
import subprocess
import time

import modal

#: The LIBERO-finetuned checkpoint. NOT lerobot/smolvla_base: a base checkpoint carries no LIBERO
#: action statistics and cannot emit correctly-scaled LIBERO actions, so evaluating it here would
#: measure noise. Verified public and ungated.
CKPT = "HuggingFaceVLA/smolvla_libero"

#: All ten libero_object tasks. The suite constructor defaults to task_ids=(0,), and `--tasks`
#: overrides it — `_build_env` builds a config for the REQUESTED id and raises if absent rather than
#: silently rolling out task 0 under another task's label, which it used to do.
ALL_TASKS = ",".join(f"libero_object/{i}" for i in range(10))

#: The screen. `none` is the benign control and is not optional: it is the matched twin every
#: McNemar comparison is made against, and without it an ASR has nothing to be read against.
ATTACKS = "none,instruction,visual,injection"

#: provael installs from git, not PyPI. `--episodes-per-seed` landed after the 0.32.0 tag, so the
#: released wheel cannot express stage 2's design at all.
PROVAEL = "git+https://github.com/provael/provael@main"

STAGES: dict[str, dict[str, str]] = {
    # ONE episode. Its only job is to measure seconds-per-episode so the other two stages can be
    # sized by arithmetic instead of by guess. This stage exists because the guess was wrong: the
    # probe below was estimated at "210 episodes, ~20 min" and was killed by its own 3600s timeout
    # without finishing. 210 x 280 steps is ~59k policy forward passes and ~59k MuJoCo steps, which
    # was never going to be 20 minutes on an L4. Measure the constant, then multiply.
    "timing": {
        "tasks": "libero_object/0", "attacks": "none",
        "seeds": "1", "episodes_per_seed": "1", "timeout": "1800",
    },
    # Eight episodes, chosen so one run answers four questions at once:
    #   1. the SLOPE. `timing` measured setup+1episode=174s and could not separate them, so its
    #      projections were overestimates of unknown size. Eight episodes against that one datum
    #      gives marginal seconds-per-episode, which is what the budget actually depends on.
    #   2. does the instruction attack fire on real LIBERO at all, or only in the committed run.
    #   3. does a SECOND task's environment build (task 1 exercises the strict `_build_env` path).
    #   4. clean-task-success on both tasks — the competence control, which the timing run showed
    #      is already reported and already 100% on task 0.
    "pilot": {
        "tasks": "libero_object/0,libero_object/1", "attacks": "none,instruction",
        "seeds": "2", "episodes_per_seed": "1", "timeout": "5400",
    },
    # Direction check across all ten tasks. 1 episode per seed, so seeds and episodes coincide
    # exactly as in every historical run — deliberately comparable to the existing headline.
    "probe": {
        "tasks": ALL_TASKS, "attacks": ATTACKS,
        "seeds": "3", "episodes_per_seed": "1", "timeout": "10800",
    },
    # The real thing.
    "full": {
        "tasks": ALL_TASKS, "attacks": ATTACKS,
        "seeds": "10", "episodes_per_seed": "3", "timeout": "86400",
    },
}

#: Defaults to the ONE-episode timing stage. The previous default was the 210-episode probe, and a
#: default that can burn an hour of GPU before saying anything is the wrong default.
STAGE = os.environ.get("PROVAEL_STAGE", "timing")
if STAGE not in STAGES:
    raise SystemExit(f"PROVAEL_STAGE={STAGE!r} is not one of {sorted(STAGES)}")
CFG = STAGES[STAGE]
OUT = f"/runs/libero_object_{STAGE}"

#: Results live on a Volume, NOT in the container filesystem. A container killed by its timeout
#: takes its filesystem with it — which is how an hour of work produced no report.json and no log.
#: On a Volume, a partial run is still on disk afterwards and `modal volume get` retrieves it.
volume = modal.Volume.from_name("provael-libero-runs", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.12")
    # MuJoCo needs a GL stack even to render offscreen. egl is the GPU path; osmesa is the software
    # fallback and is installed too so a failure to find EGL degrades rather than dies.
    #
    # cmake and build-essential are NOT optional and NOT obvious. Two packages deep in the LIBERO
    # chain — `egl_probe` (via robomimic) and `hf-egl-probe` (via hf-libero) — compile a small C++
    # EGL probe in their setup.py and shell out to `cmake`, which debian_slim does not carry:
    #
    #     FileNotFoundError: [Errno 2] No such file or directory: 'cmake'
    #     RuntimeError: CMake must be installed.
    #
    # lerobot already declares `cmake>=3.29` as a pip dependency, and that does NOT help: pip
    # resolves and BUILDS every wheel before installing any of them, so the cmake wheel's binary is
    # not on PATH while egl_probe is building. It has to come from apt, before pip runs at all.
    #
    # The glib/X set is for cv2, and the reason is a real conflict in the dependency tree rather
    # than a missing nicety. lerobot depends on opencv-python-HEADLESS, which needs none of this;
    # hf-libero depends on the FULL opencv-python. Both install, both provide the `cv2` module, the
    # full one wins, and `import cv2` then demands the GUI stack headless exists to avoid:
    #
    #     ImportError: libgthread-2.0.so.0: cannot open shared object file
    #
    # robosuite imports cv2 at package import time (utils/opencv_renderer.py), so this kills the run
    # before the first episode. Installing the libs is better than fighting the resolver: hf-libero
    # genuinely declares full opencv, and force-removing it would break an upstream contract.
    .apt_install(
        "libegl1-mesa-dev", "libgl1-mesa-glx", "libosmesa6-dev", "git", "cmake", "build-essential",
        "libglib2.0-0", "libsm6", "libxrender1", "libfontconfig1",
    )
    .pip_install(f"provael[lerobot] @ {PROVAEL}", "lerobot[libero]==0.5.1")
    .env({"MUJOCO_GL": "egl", "PYOPENGL_PLATFORM": "egl", "PROVAEL_INTEGRATION": "1"})
)

app = modal.App(f"provael-libero-{STAGE}", image=image)


@app.function(gpu="L4", timeout=int(CFG["timeout"]), volumes={"/runs": volume})
def redteam() -> str:
    """Run the screen and STREAM its output, so a timeout still leaves a diagnosable trail."""
    cmd = [
        "provael", "attack",
        "--policy", "smolvla",
        "--suite", "libero",
        "--model", CKPT,
        "--tasks", CFG["tasks"],
        "--attacks", CFG["attacks"],
        "--seeds", CFG["seeds"],
        "--episodes-per-seed", CFG["episodes_per_seed"],
        "--horizon", "280",
        "--seed", "0",
        "--out", OUT,
    ]
    print(f"$ {' '.join(cmd)}", flush=True)
    started = time.monotonic()

    # NO capture_output, and that is the whole point of this line. Buffering the child's output
    # means a container killed by its timeout takes the buffer with it: the first attempt at the
    # probe ran a full hour and returned NOTHING, so "slow but working" and "hung on the first
    # environment" were indistinguishable. Inheriting stdout lets Modal stream it live instead, so
    # progress is visible as it happens and a timeout still leaves everything printed up to the
    # moment of the kill.
    #
    # check=False: a partial result is worth reading. A crash in task 9 should not discard 0-8.
    done = subprocess.run(cmd, check=False)
    elapsed = time.monotonic() - started

    # Commit before returning: on the `full` stage this is hours of work, and an uncommitted Volume
    # write is not durable.
    volume.commit()

    episodes = int(CFG["seeds"]) * int(CFG["episodes_per_seed"]) * len(CFG["tasks"].split(","))
    episodes *= len(CFG["attacks"].split(","))
    lines = [f"exit={done.returncode}", f"elapsed={elapsed:.0f}s over {episodes} planned episodes"]

    # SECONDS PER STEP is the invariant worth reporting, not seconds per episode. LIBERO ends an
    # episode early when the task succeeds — the timing run's episode ran 134 of 280 steps — so a
    # successful episode costs about half a failed one, and per-episode averages therefore move
    # with the success rate we are trying to measure. Per-step does not, so a projection built on
    # it needs only an assumption about episode LENGTH, which the horizon bounds.
    try:
        with open(f"{OUT}/report.json", encoding="utf-8") as fh:
            payload = fh.read()
        report = json.loads(payload)
        results = report.get("results", [])
        steps = sum(int(r.get("steps") or 0) for r in results)
        wins = sum(1 for r in results if r.get("task_success"))
        if steps:
            per_step = elapsed / steps
            lines += [
                f"steps={steps} over {len(results)} episodes -> {per_step:.3f}s/step "
                f"(includes one-off setup, so this OVERSTATES the marginal rate)",
                f"clean-task-success {wins}/{len(results)} — the competence control",
                # Worst case: every episode runs the full horizon because the attack made it fail.
                f"upper bound, 1200 ep x 280 steps: {1200 * 280 * per_step / 3600:.1f} h",
            ]
        lines += ["=== report.json (results[] trimmed) ===", json.dumps(
            {k: v for k, v in report.items() if k != "results"}, indent=2, sort_keys=True
        )]
    except (OSError, ValueError) as exc:
        lines.append(f"(no readable report.json at {OUT}: {exc} — the Volume keeps what exists)")
    return "\n".join(lines)


@app.local_entrypoint()
def main() -> None:
    print(redteam.remote())
