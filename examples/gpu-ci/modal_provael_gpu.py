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


image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libegl1-mesa-dev", "libgl1-mesa-glx", "libosmesa6-dev")
    .pip_install("provael[lerobot]", "lerobot[libero]==0.5.1")
    .env({"MUJOCO_GL": "egl", "PYOPENGL_PLATFORM": "egl", "PROVAEL_INTEGRATION": "1"})
)
app = modal.App("provael-gpu-ci", image=image)


@app.function(gpu="L4", timeout=3600)
def redteam() -> str:
    """Run the gated real-model path and return the CLI's stdout."""
    import subprocess

    cmd = [
        "provael", "attack", "--policy", "smolvla", "--suite", "libero",
        "--model", CKPT, "--attacks", ATTACKS, "--seeds", SEEDS, "--horizon", "280",
        "--seed", "0", "--out", "runs/smolvla_libero",
    ]
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


@app.local_entrypoint()
def main() -> None:
    print(redteam.remote())
