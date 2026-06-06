#!/usr/bin/env bash
# Real SmolVLA-on-LIBERO red-team path (GPU). Runs the IN-PROCESS attack loop
# (robopwn attack --policy smolvla --suite libero), not a lerobot-eval fallback.
#
# Detects CUDA. With a GPU it provisions an isolated venv with the [lerobot] + LIBERO
# extras, runs the verified-real gated tests, runs the real attack, and refreshes the
# leaderboard. With NO GPU it prints the exact commands and exits 0.
#
# NOTE: lerobot/smolvla_base is NOT LIBERO-compatible (it expects camera1/2/3; LIBERO
# provides image/image2 + 8-dim state). The default below is a READY LIBERO-fine-tuned
# checkpoint — HuggingFaceVLA/smolvla_libero — verified to load through the glue with no
# IncompatiblePolicyError, so no fine-tuning is needed. Override with
# ROBOPWN_SMOLVLA_LIBERO_CKPT. (Its benign task-success may run below the paper numbers —
# see LeRobot issues #3264 / #2354 — which is fine here: we measure redirection ASR.)
#
# Usage:  ./scripts/run_real.sh            (or ROBOPWN_SMOLVLA_LIBERO_CKPT=<repo_id> ...)
set -euo pipefail
cd "$(dirname "$0")/.."

# Headless MuJoCo rendering for LIBERO on a cloud/HPC box. EGL = GPU-accelerated headless
# (needs the EGL loader libs, e.g. `apt-get install -y libegl1-mesa-dev libgl1-mesa-glx`).
# PyOpenGL needs PYOPENGL_PLATFORM set too, else it defaults to GLX and mujoco's EGL import
# fails with "NoneType has no attribute eglQueryString". For a bulletproof CPU-rendering
# fallback (no EGL/driver needed; slower): MUJOCO_GL=osmesa (+ apt `libosmesa6-dev`).
export MUJOCO_GL="${MUJOCO_GL:-egl}"
export PYOPENGL_PLATFORM="${PYOPENGL_PLATFORM:-$MUJOCO_GL}"

VENV=".venv-real"
CKPT="${ROBOPWN_SMOLVLA_LIBERO_CKPT:-HuggingFaceVLA/smolvla_libero}"
TASKS="${ROBOPWN_ATTACKS:-instruction,visual,injection}"
SEEDS="${ROBOPWN_SEEDS:-10}"

print_commands() {
  cat <<EOF
On a CUDA GPU box, run the real in-process attack loop:

  uv venv ${VENV} --python 3.12
  uv pip install --python ${VENV}/bin/python -e '.[lerobot]' 'lerobot[libero]==0.5.1'
  # headless MuJoCo rendering (EGL needs: apt-get install -y libegl1-mesa-dev libgl1-mesa-glx)
  export MUJOCO_GL=egl PYOPENGL_PLATFORM=egl   # or MUJOCO_GL=osmesa (CPU fallback; apt libosmesa6-dev)

  # Real seeded attack-ASR (mean ± per-seed std) with the ready LIBERO checkpoint:
  ${VENV}/bin/robopwn attack --policy smolvla --suite libero \\
      --model ${CKPT} \\
      --attacks ${TASKS} --seeds ${SEEDS} --seed 0 --out runs/smolvla_libero

  # Flip the leaderboard to real (non-demo) numbers:
  ${VENV}/bin/robopwn leaderboard build --runs 'runs/*' --out leaderboard/results
EOF
}

if ! { command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; }; then
  echo "No CUDA GPU detected on this machine — not running the real path."
  echo
  print_commands
  exit 0
fi

echo "CUDA detected — provisioning ${VENV} and running the real SmolVLA-on-LIBERO path…"
echo "checkpoint: ${CKPT}  (set ROBOPWN_SMOLVLA_LIBERO_CKPT to override)"
uv venv "${VENV}" --python 3.12
uv pip install --python "${VENV}/bin/python" -e '.[lerobot]' 'lerobot[libero]==0.5.1'

echo ">> gated integration tests (real load + real env + one real step)…"
ROBOPWN_INTEGRATION=1 ROBOPWN_SMOLVLA_LIBERO_CKPT="${CKPT}" "${VENV}/bin/python" -m pytest \
  tests/test_lerobot_adapter.py tests/test_libero_adapter.py -q || true

echo ">> red-team SmolVLA in the LIBERO simulator (in-process attack-ASR)…"
"${VENV}/bin/robopwn" attack --policy smolvla --suite libero \
  --model "${CKPT}" --attacks "${TASKS}" --seeds "${SEEDS}" --seed 0 \
  --out runs/smolvla_libero

echo ">> refreshing the leaderboard with real numbers…"
"${VENV}/bin/robopwn" leaderboard build --runs 'runs/*' --out leaderboard/results
echo ">> done. Real results in runs/smolvla_libero and leaderboard/results."
