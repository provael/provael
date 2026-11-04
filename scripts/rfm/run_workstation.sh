#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
#
# Record the RFM Safety Failures episodes on the 14 September workstation (Linux / WSL2, one CUDA
# GPU; it was an RTX 2000 Ada). A FILE rather than lines to paste, because that terminal's paste
# drops tildes, asterisks and underscores next to punctuation. Run it from tmux so a closed window
# does not stop it:
#
#   tmux new -d -s rfm "bash $HOME/rfm-src/scripts/rfm/run_workstation.sh"
#   tmux attach -t rfm        (leave with Ctrl-b then d; never Ctrl-c inside tmux)
#
# What it does: refuses a checkout with uncommitted changes (the commit is stamped on every
# artifact), builds .venv from uv.lock with the [lerobot] extra using the uv version CI uses,
# checks a CUDA device is visible, then runs the whole campaign (selection rule, benign twin,
# identical-actions pair, composed videos) into results/rfm_submission_2026-11 of this checkout.
# Re-running resumes: an episode with a finished recording.json is never re-run.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"
OUT="${1:-$REPO/results/rfm_submission_2026-11}"
mkdir -p "$OUT"
LOG="$OUT/campaign.log"
exec > >(tee -a "$LOG") 2>&1

echo "[rfm] $(date -u +%Y-%m-%dT%H:%M:%SZ) checkout $REPO at $(git rev-parse --short HEAD)"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "[rfm] uncommitted changes in $REPO; commit or stash them first" >&2
  exit 2
fi

export MUJOCO_GL=egl
export PYOPENGL_PLATFORM=egl
export PROVAEL_INTEGRATION=1
export CUBLAS_WORKSPACE_CONFIG=":4096:8"

# uv 0.13.6 is the version CI uses; the lock is revision 5 and older uv releases write it wrongly.
uvx uv@0.13.6 sync --frozen --extra lerobot --no-dev
PY="$REPO/.venv/bin/python"
"$PY" -c "import torch, sys; ok = torch.cuda.is_available(); print('[rfm] torch', torch.__version__, 'cuda', torch.version.cuda, 'device', torch.cuda.get_device_name(0) if ok else None); sys.exit(0 if ok else 3)"

"$PY" scripts/rfm/rfm_record.py campaign --out "$OUT"
echo "[rfm] $(date -u +%Y-%m-%dT%H:%M:%SZ) done; outputs in $OUT"
cat "$OUT/SHA256SUMS" 2>/dev/null || true
