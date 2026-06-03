#!/usr/bin/env bash
# Real SmolVLA-on-LIBERO red-team path (GPU only).
#
# Detects CUDA. If a GPU is present, it provisions an isolated venv with the
# [lerobot] + LIBERO simulator extras, runs the verified-real gated tests, runs the
# attack in the real simulator, and refreshes the leaderboard. If there is NO GPU it
# prints the exact commands and exits 0 (it never fails the no-GPU case).
#
# Usage:  ./scripts/run_real.sh
set -euo pipefail
cd "$(dirname "$0")/.."

VENV=".venv-real"

print_commands() {
  cat <<EOF
On a CUDA GPU box, run the real path:

  uv venv ${VENV} --python 3.12
  uv pip install --python ${VENV}/bin/python -e '.[lerobot]' 'lerobot[libero]==0.5.1'

  # 1) Verified-real stack check (loads SmolVLA + builds a real LIBERO env):
  ROBOPWN_INTEGRATION=1 ${VENV}/bin/python -m pytest \\
      tests/test_lerobot_adapter.py tests/test_libero_adapter.py -q

  # 2) Attack-ASR via our harness, in the LIBERO simulator:
  ROBOPWN_INTEGRATION=1 ${VENV}/bin/robopwn attack --policy smolvla --suite libero \\
      --attacks instruction,visual,injection --episodes 10 --seed 0 --out runs/smolvla_libero

  # 3) Refresh the leaderboard with the real numbers:
  ${VENV}/bin/robopwn leaderboard build --runs 'runs/*' --out leaderboard/results

  # Reference numbers via LeRobot's own evaluator (benign task success):
  ${VENV}/bin/lerobot-eval --policy.path=lerobot/smolvla_base \\
      --env.type=libero --env.task=libero_object

NOTE: end-to-end smolvla x libero attack-ASR depends on the LIBERO observation ->
policy-features wiring; if step 2 reports it needs that glue, use lerobot-eval for
reference numbers and see CHANGELOG '[Unreleased]'.
EOF
}

if ! { command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; }; then
  echo "No CUDA GPU detected on this machine — not running the real path."
  echo
  print_commands
  exit 0
fi

echo "CUDA detected — provisioning ${VENV} and running the real SmolVLA-on-LIBERO path…"
uv venv "${VENV}" --python 3.12
uv pip install --python "${VENV}/bin/python" -e '.[lerobot]' 'lerobot[libero]==0.5.1'

echo ">> gated integration tests (real load + real env)…"
ROBOPWN_INTEGRATION=1 "${VENV}/bin/python" -m pytest \
  tests/test_lerobot_adapter.py tests/test_libero_adapter.py -q

echo ">> red-team SmolVLA in the LIBERO simulator…"
if ROBOPWN_INTEGRATION=1 "${VENV}/bin/robopwn" attack --policy smolvla --suite libero \
    --attacks instruction,visual,injection --episodes 10 --seed 0 --out runs/smolvla_libero; then
  "${VENV}/bin/robopwn" leaderboard build --runs 'runs/*' --out leaderboard/results
  echo ">> real results written to runs/smolvla_libero and leaderboard/results."
else
  echo ">> in-process smolvla x libero attack-ASR needs the LIBERO obs->features glue."
  echo ">> reference numbers via lerobot-eval:"
  "${VENV}/bin/lerobot-eval" --policy.path=lerobot/smolvla_base \
    --env.type=libero --env.task=libero_object || true
fi
echo ">> done."
