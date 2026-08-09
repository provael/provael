"""Run the FULL libero_object suite on a rented Modal GPU. Two stages, on purpose.

WHY THIS EXISTS SEPARATELY FROM modal_provael_gpu.py. That script runs the suite's default task set,
which is `task_ids=(0,)` — a single task. Every committed real-policy result to date therefore
measures one task, and "one task at 10/10" is consistent with a suite-wide rate anywhere from 10% to
100%. That interval is the largest unconstrained quantity in the project and no amount of extra
seeds narrows it. Only more TASKS do.

WHY LIBERO CANNOT RUN ON A MAC, so this is not optional. lerobot declares
`hf-libero; sys_platform == "linux"`, so the LIBERO extra does not install on darwin at any price. A
rented Linux GPU is the cheapest path, not a luxury.

TWO STAGES, AND THE ORDER IS THE POINT.

    stage 1  probe    10 tasks x 3 seeds x 1 episode   ~210 episodes   ~20 min   ~$0.30
    stage 2  full     10 tasks x 10 seeds x 3 repeats  ~2100 episodes  ~4 h      ~$3

Stage 1 exists because the answer might change what stage 2 should be. If the attack fires on 2 of
10 tasks rather than 10 of 10, the headline is a task-specific finding and not a suite rate — and
that is worth learning in twenty minutes for thirty cents, not in four hours after committing to a
protocol. Running stage 2 first is the mistake of buying precision before checking direction.

Stage 2's shape is chosen, not arbitrary. 10 seeds x 3 repeats separates INITIAL-STATE variation
from POLICY stochasticity, which `--episodes-per-seed` made computable for the first time; n=30 per
cell puts an attack down to ~30% ASR above the detection floor once Holm correction is applied
across the screen.

    modal run examples/gpu-ci/modal_libero_suite.py                   # stage 1, the probe
    PROVAEL_STAGE=full modal run examples/gpu-ci/modal_libero_suite.py   # stage 2, the real run

The stage is an environment variable rather than a `--stage` flag because `modal run` resolves the
app at import time, before any entrypoint argument is parsed — the image, the GPU and the timeout
all have to be decided before Modal will accept the module.
"""

from __future__ import annotations

import os
from typing import Any

#: The LIBERO-finetuned checkpoint. NOT lerobot/smolvla_base: a base checkpoint carries no LIBERO
#: action statistics and cannot emit correctly-scaled LIBERO actions, so evaluating it here would
#: measure noise. Verified public and ungated.
CKPT = "HuggingFaceVLA/smolvla_libero"

#: All ten libero_object tasks. The suite constructor defaults to task_ids=(0,), and `--tasks`
#: overrides it — `_build_env` builds a config for the REQUESTED id and raises if absent rather than
#: silently rolling out task 0 under another task's label, which it used to do.
TASKS = ",".join(f"libero_object/{i}" for i in range(10))

#: The screen. `none` is the benign control and is not optional: it is the matched twin every
#: McNemar comparison is made against, and without it an ASR has nothing to be read against.
ATTACKS = "none,instruction,visual,injection"

#: provael is installed from git, not PyPI. `--episodes-per-seed` landed after the 0.32.0 tag, so
#: the released wheel cannot express stage 2's design at all.
PROVAEL = "git+https://github.com/provael/provael@main"

STAGES: dict[str, dict[str, str]] = {
    # Cheap direction check. 1 episode per seed, so seeds and episodes coincide exactly as in every
    # historical run — deliberately comparable to the existing headline.
    "probe": {"seeds": "3", "episodes_per_seed": "1", "timeout": "3600"},
    # The real thing.
    "full": {"seeds": "10", "episodes_per_seed": "3", "timeout": "28800"},
}


#: Chosen at import time. `modal run` resolves the app before parsing entrypoint arguments, so the
#: stage cannot be a flag: the image, GPU and timeout must all be fixed before Modal accepts the
#: module. Defaults to the cheap probe so a mistyped variable costs 30 cents, not 4 hours.
STAGE = os.environ.get("PROVAEL_STAGE", "probe")
if STAGE not in STAGES:
    raise SystemExit(f"PROVAEL_STAGE={STAGE!r} is not one of {sorted(STAGES)}")


def build_app(stage: str = STAGE) -> Any:
    """Construct the Modal app. Imports modal lazily so the module reads without it installed."""
    import modal

    cfg = STAGES[stage]
    image = (
        modal.Image.debian_slim(python_version="3.12")
        # MuJoCo needs a GL stack even to render offscreen. egl is the GPU path; osmesa is the
        # software fallback and is installed too so a failure to find EGL degrades rather than dies.
        .apt_install("libegl1-mesa-dev", "libgl1-mesa-glx", "libosmesa6-dev", "git")
        .pip_install(f"provael[lerobot] @ {PROVAEL}", "lerobot[libero]==0.5.1")
        .env({"MUJOCO_GL": "egl", "PYOPENGL_PLATFORM": "egl", "PROVAEL_INTEGRATION": "1"})
    )
    app = modal.App(f"provael-libero-{stage}", image=image)

    @app.function(gpu="L4", timeout=int(cfg["timeout"]))
    def redteam() -> str:
        import subprocess

        cmd = [
            "provael", "attack",
            "--policy", "smolvla",
            "--suite", "libero",
            "--model", CKPT,
            "--tasks", TASKS,
            "--attacks", ATTACKS,
            "--seeds", cfg["seeds"],
            "--episodes-per-seed", cfg["episodes_per_seed"],
            "--horizon", "280",
            "--seed", "0",
            "--out", f"runs/libero_object_{stage}",
        ]
        # check=False: a partial result is worth reading. On a multi-hour run a crash in task 9
        # should not throw away tasks 0-8, and the stdout carries enough to see how far it got.
        done = subprocess.run(cmd, check=False, capture_output=True, text=True)
        report = f"runs/libero_object_{stage}/report.json"
        try:
            with open(report, encoding="utf-8") as fh:
                payload = fh.read()
        except OSError:
            payload = ""
        return "\n".join([
            f"exit={done.returncode}",
            done.stdout[-4000:],
            done.stderr[-4000:] if done.returncode else "",
            "=== report.json ===",
            payload,
        ])

    @app.local_entrypoint()
    def main() -> None:
        print(redteam.remote())

    return app


#: Module level so `modal run <this file>` finds it. Building the app is cheap — it declares an
#: image and a function, it does not start a container.
app = build_app()
