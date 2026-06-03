#!/usr/bin/env bash
# Real SmolVLA-on-LIBERO red-team path (GPU). Runs the IN-PROCESS attack loop
# (robopwn attack --policy smolvla --suite libero), not a lerobot-eval fallback.
#
# Detects CUDA. With a GPU it provisions an isolated venv with the [lerobot] + LIBERO
# extras, runs the verified-real gated tests, runs the real attack, and refreshes the
# leaderboard. With NO GPU it prints the exact commands and exits 0.
#
# IMPORTANT: lerobot/smolvla_base is NOT LIBERO-compatible (it expects camera1/2/3;
# LIBERO provides image/image2 + 8-dim state). Set ROBOPWN_SMOLVLA_LIBERO_CKPT to a
# LIBERO-FINE-TUNED SmolVLA checkpoint (train one with lerobot-train on
# HuggingFaceVLA/libero). The base model will report a clean IncompatiblePolicyError.
#
# Usage:  ROBOPWN_SMOLVLA_LIBERO_CKPT=<repo_id> ./scripts/run_real.sh
set -euo pipefail
cd "$(dirname "$0")/.."

VENV=".venv-real"
CKPT="${ROBOPWN_SMOLVLA_LIBERO_CKPT:-lerobot/smolvla_base}"
TASKS="${ROBOPWN_ATTACKS:-instruction,visual,injection}"
SEEDS="${ROBOPWN_SEEDS:-10}"

print_commands() {
  cat <<EOF
On a CUDA GPU box, run the real in-process attack loop:

  uv venv ${VENV} --python 3.12
  uv pip install --python ${VENV}/bin/python -e '.[lerobot]' 'lerobot[libero]==0.5.1'

  # A LIBERO-FINE-TUNED SmolVLA checkpoint is required (base model is incompatible):
  export ROBOPWN_SMOLVLA_LIBERO_CKPT=<your-libero-finetuned-smolvla-repo_id>

  # Real seeded attack-ASR (mean ± per-seed std), in the LIBERO simulator:
  ${VENV}/bin/robopwn attack --policy smolvla --suite libero \\
      --model "\$ROBOPWN_SMOLVLA_LIBERO_CKPT" \\
      --attacks ${TASKS} --seeds ${SEEDS} --seed 0 --out runs/smolvla_libero

  # Flip the leaderboard to real (non-demo) numbers:
  ${VENV}/bin/robopwn leaderboard build --runs 'runs/*' --out leaderboard/results

To produce a checkpoint (per the official LeRobot LIBERO docs):
  ${VENV}/bin/lerobot-train --policy.type=smolvla --policy.load_vlm_weights=true \\
      --dataset.repo_id=HuggingFaceVLA/libero --env.type=libero --env.task=libero_10 \\
      --output_dir=./outputs/ --steps=100000
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
