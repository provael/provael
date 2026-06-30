"""Run the real SmolVLA x LIBERO red-team path on a Modal GPU — fork-safe, ~$0.02/run.

Provael's core is CPU-tested in CI; the headline credibility move is a cheap, *real-model* job.
Modal (https://modal.com) spins up a GPU container on demand, runs the gated integration path,
and shuts down — pennies per run. Pair with examples/gpu-ci/modal-gpu-tests.yml, which only
triggers on a `gpu-tests` PR label so fork PRs can't spend.

    pip install modal
    modal run examples/gpu-ci/modal_provael_gpu.py

This file is importable without modal (the decorators are applied lazily in `build_app`).
"""

from __future__ import annotations

from typing import Any

CKPT = "HuggingFaceVLA/smolvla_libero"
ATTACKS = "none,instruction,visual,injection"


def build_app() -> Any:
    """Construct the Modal app lazily so this module imports without modal installed."""
    import modal

    image = (
        modal.Image.debian_slim(python_version="3.12")
        .apt_install("libegl1-mesa-dev", "libgl1-mesa-glx", "libosmesa6-dev")
        .pip_install("provael[lerobot]", "lerobot[libero]==0.5.1")
        .env({"MUJOCO_GL": "egl", "PYOPENGL_PLATFORM": "egl", "PROVAEL_INTEGRATION": "1"})
    )
    app = modal.App("provael-gpu-ci", image=image)

    @app.function(gpu="L4", timeout=3600)
    def redteam() -> str:
        import subprocess

        cmd = [
            "provael", "attack", "--policy", "smolvla", "--suite", "libero",
            "--model", CKPT, "--attacks", ATTACKS, "--seeds", "10", "--horizon", "280",
            "--seed", "0", "--out", "runs/smolvla_libero",
        ]
        return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout

    @app.local_entrypoint()
    def main() -> None:
        print(redteam.remote())

    return app


if __name__ == "__main__":
    build_app()
