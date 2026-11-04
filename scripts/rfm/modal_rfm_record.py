# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
# mypy: disallow-untyped-decorators=False
"""Record the RFM episodes on one Modal L4, installed from THIS checkout, billed at most $3.35.

    uvx uv@0.13.6 run --frozen --with "modal>=1.2" modal run scripts/rfm/modal_rfm_record.py

NOT A MEASUREMENT LANE, AND THAT IS WHY IT DOES NOT LIVE IN examples/gpu-ci/. Every
``examples/gpu-ci/modal_*.py`` must install a pinned PyPI release (``tests/test_gpu_image_pin.py``),
which is right for a lane that measures. This script records a video: it installs the working
tree's own source (0.47.0's init-state pinning plus the recording hooks on this branch, neither on
PyPI), and its episodes are labelled as recordings in their execution manifests. It refuses to start
from a tree with uncommitted changes, because the commit it stamps on every artifact must describe
the code that ran.

WHAT RUNS. :func:`rfm_record.campaign`, exactly as on the workstation: the selection rule over seeds
0 to 4 (stopping at the first roleplay episode that leaves the envelope), the benign twin at that
seed, the identical-actions pair (two plain runs of the selected roleplay episode, actions only),
the check, and the three composed videos. Each episode is a fresh process. The Volume is committed
after every episode, and a completed episode is never re-run, so a preemption restart resumes.

WHAT IT COSTS, from https://modal.com/pricing as read on 4 November 2026 (L4 $0.000222/s, CPU
$0.0000131 per core per second, memory $0.00000222 per GiB per second; Modal bills CPU and memory
at max(request, use), and both are capped here above a smaller request): at most $0.000310 per
second ($1.12 an hour). Expected about 29 minutes ($0.53) when seed 0 leaves the envelope, about 58
minutes ($1.07) when all five seeds are needed (``rfm_plan.modal_plan_seconds``, at the slowest
measured 0.77 s per step). A GPU function on Modal cannot opt out of preemption, and a preempted
input is restarted, so the timeout alone bounds one attempt, not the bill: the function counts its
attempts per launch on the Volume and refuses a third, which caps a launch at 2 x 90 min =
$3.35, under the $5 budget. Image builds are not included in that figure. Set a workspace spend
limit in the Modal dashboard as well.

WHERE THE OUTPUT GOES. The Volume ``provael-rfm-2026-11`` under ``rfm_submission_2026-11/``; the
local entrypoint then copies everything except the camera tracks and the policy-view arrays (pass
``--with-tracks`` for those) into ``results/rfm_submission_2026-11/`` of this checkout. The same
files can be fetched by hand with ``modal volume get provael-rfm-2026-11 rfm_submission_2026-11
results``.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import uuid

import modal  # type: ignore[import-not-found, unused-ignore]

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "rfm"))

import rfm_plan as plan  # noqa: E402 - stdlib only, beside this file

APP_NAME = "provael-rfm-2026-11"
VOLUME_NAME = "provael-rfm-2026-11"
#: Shared with the measurement lanes: the SmolVLA checkpoint (HF_HOME) and LIBERO's assets.
CACHE_VOLUME = "provael-libero-cache"
REMOTE_OUT = "rfm_submission_2026-11"
UV_VERSION = "0.13.6"
#: What the container needs from the checkout; everything else stays local.
KEEP = ("src", "scripts/rfm", "pyproject.toml", "uv.lock", "LICENSE", "NOTICE")


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], capture_output=True, text=True, cwd=REPO, check=False,
                         timeout=10)
    return out.stdout.strip() if out.returncode == 0 else ""


def _ignore(path: pathlib.Path) -> bool:
    """True for every file of the checkout the container does not need."""
    rel = path.relative_to(REPO) if path.is_absolute() else path
    posix = rel.as_posix()
    if "__pycache__" in rel.parts or posix.endswith(".pyc"):
        return True
    inside = any(posix == k or posix.startswith(f"{k}/") for k in KEEP)
    parent_of_kept = any(k.startswith(f"{posix}/") for k in KEEP)
    return not (inside or parent_of_kept)


COMMIT = _git("rev-parse", "--short", "HEAD")
DIRTY = bool(_git("status", "--porcelain", "--untracked-files=no"))

volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
cache = modal.Volume.from_name(CACHE_VOLUME, create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.12")
    # The same system packages as examples/gpu-ci/modal_libero_suite.py, for the same reasons: EGL
    # (and OSMesa as a fallback) for MuJoCo's offscreen renderer, cmake and a compiler for the EGL
    # probes hf-libero builds, and the GUI libraries the full opencv-python it pulls in demands.
    .apt_install(
        "libegl1-mesa-dev", "libgl1-mesa-glx", "libosmesa6-dev", "git", "cmake", "build-essential",
        "libglib2.0-0", "libsm6", "libxrender1", "libfontconfig1",
    )
    # The checkout's own lock, frozen: the dependency set CI tests, with the [lerobot] extra.
    .uv_sync(uv_project_dir=str(REPO), extras=["lerobot"], frozen=True, uv_version=UV_VERSION,
             extra_options="--no-dev")
    .env({
        "MUJOCO_GL": "egl",
        "PYOPENGL_PLATFORM": "egl",
        "PROVAEL_INTEGRATION": "1",
        "HF_HOME": "/cache/hf",
        "CUBLAS_WORKSPACE_CONFIG": ":4096:8",
        # The checkout's source, not an installed wheel: uv_sync installs dependencies only.
        "PYTHONPATH": "/src/src",
        # Provenance the container cannot read from git (the source is mounted without .git).
        "PROVAEL_COMMIT": COMMIT,
        "PROVAEL_REPOSITORY": "provael/provael",
        "PROVAEL_SOURCE_DIRTY": "1" if DIRTY else "0",
    })
    .add_local_dir(str(REPO), "/src", ignore=_ignore)
)

app = modal.App(APP_NAME, image=image)


@app.function(
    gpu=plan.MODAL_GPU,
    cpu=(plan.MODAL_CPU_REQUEST_CORES, plan.MODAL_CPU_CORES),
    memory=(plan.MODAL_MEMORY_REQUEST_MIB, plan.MODAL_MEMORY_MIB),
    timeout=plan.MODAL_TIMEOUT_S,
    volumes={"/runs": volume, "/cache": cache},
)
def record(launch: str) -> str:
    """Run the campaign once for ``launch``, refusing a third attempt of the same launch."""
    out = pathlib.Path("/runs") / REMOTE_OUT
    out.mkdir(parents=True, exist_ok=True)
    attempts_file = out / "attempts.json"
    attempts = json.loads(attempts_file.read_text()) if attempts_file.is_file() else {}
    count = int(attempts.get(launch, 0)) + 1
    if count > plan.MODAL_MAX_ATTEMPTS:
        return (f"refusing attempt {count} of launch {launch}: the cap is "
                f"{plan.MODAL_MAX_ATTEMPTS}, which is what bounds the bill")
    attempts[launch] = count
    attempts_file.write_text(json.dumps(attempts, indent=2, sort_keys=True) + "\n")
    volume.commit()

    # LIBERO resolves its asset folder itself, so HF_HOME cannot move it: link it onto the cache
    # Volume as the measurement lane does, tolerating the link already being there.
    os.makedirs("/cache/libero", exist_ok=True)
    link = pathlib.Path("/root/.cache/libero")
    if not link.is_symlink():
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.exists():
            shutil.rmtree(link)
        link.symlink_to("/cache/libero")

    os.chdir("/src")  # so the execution manifests digest this checkout's uv.lock
    sys.path.insert(0, "/src/scripts/rfm")
    import rfm_record

    code = rfm_record.campaign(out, after_each=volume.commit)
    volume.commit()
    summary = out / "campaign.json"
    return f"attempt {count}, exit {code}\n" + (summary.read_text() if summary.is_file() else "")


def _write_back(with_tracks: bool) -> None:
    """Copy the launch's outputs from the Volume into results/rfm_submission_2026-11/ here."""
    dest = REPO / plan.OUTPUT_DIR
    copied = 0
    try:
        entries = volume.listdir(REMOTE_OUT, recursive=True)
        for entry in entries:
            if getattr(entry.type, "name", str(entry.type)).upper() != "FILE":
                continue
            rel = pathlib.PurePosixPath(entry.path).relative_to(REMOTE_OUT)
            if not with_tracks and ("tracks" in rel.parts or rel.suffix == ".npz"):
                continue
            target = dest / pathlib.Path(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as fh:
                for chunk in volume.read_file(entry.path):
                    fh.write(chunk)
            copied += 1
    except Exception as exc:  # noqa: BLE001 - the Volume still has everything; say how to get it
        print(f"[local] copying back failed ({exc}); fetch by hand with: modal volume get "
              f"{VOLUME_NAME} {REMOTE_OUT} {REPO / 'results'}")
        return
    print(f"[local] copied {copied} file(s) into {dest}")


@app.local_entrypoint()
def main(with_tracks: bool = False) -> None:
    if DIRTY and os.environ.get("RFM_ALLOW_DIRTY") != "1":
        raise SystemExit("this checkout has uncommitted changes; commit them first (the commit is "
                         "stamped on every artifact), or set RFM_ALLOW_DIRTY=1 to record anyway")
    if not COMMIT:
        raise SystemExit("no git commit could be read from this checkout")
    print(f"[local] commit {COMMIT}{' (dirty)' if DIRTY else ''}")
    print(plan.cost_summary())
    launch = uuid.uuid4().hex[:12]
    print(f"[local] launch {launch}")
    print(record.remote(launch))
    _write_back(with_tracks)
