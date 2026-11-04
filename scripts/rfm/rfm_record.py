# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Record one SmolVLA LIBERO-Object episode as a high-resolution video, with its measured report.

For the PAISI x MIT FutureTech "RFM Safety Failures" call. Same setup as the published headline:
``HuggingFaceVLA/smolvla_libero`` on ``libero_object/0``, base seed 0, horizon 280, the roleplay
instruction against the task's own instruction, both arms pinned to one starting scene
(``--pin-init-states``, provael 0.47.0). See ``results/rfm_submission_2026-11/README.md`` for the
selection rule (written before any result existed) and the commands.

WHAT IS MEASURED AND WHAT IS NOT. Each episode is run by :func:`provael.runner.run` and written by
the same functions ``provael attack`` uses (``report.json``, ``report.md``,
``execution-manifest.json``). The recorder is a runner argument: the report holds the scored
episode, which ends at the verdict; the steps after it are played for the video alone
(:mod:`provael.recording`). Nothing this script adds is a measurement: frames, renders and checks
sit in sidecars beside the report.

SUBCOMMANDS
    episode        one arm at one seed, with frames (``--mode video``) or actions only
    check-actions  compare action logs exactly; say where they first differ
    compose        the three submitted MP4s from recorded episodes (CPU only)
    campaign       the whole plan: selection rule, benign twin, identical-actions pair, compose
    synthetic      the campaign on a synthetic CPU scene, to test the path and estimate sizes
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import time
import warnings
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Before anything can initialise CUDA: cuBLAS reads this once, when its first handle is created.
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import numpy as np  # noqa: E402
import numpy.typing as npt  # noqa: E402

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import rfm_video as video  # noqa: E402
from rfm_plan import (  # noqa: E402 - the single source of the setup and the selection rule
    ARMS,
    CHECKPOINT,
    EXPECTED_INSTRUCTIONS,
    HORIZON,
    PIN_START,
    POLICY,
    SELECTION_SEEDS,
    SUITE,
    TASK,
    VIDEO_NAMES,
    select_seed,
)

TRACK_SIZE = 1024
MAIN_CAMERA = "agentview"
#: The wider camera, first one the live scene defines. LIBERO's floor scene (libero_object) sets
#: ``frontview`` and ``galleryview`` in ``libero_floor_manipulation.py``; detection is at runtime.
WIDE_CAMERAS: tuple[str, ...] = ("frontview", "galleryview")
#: Camera tracks are an intermediate: near-lossless so the final CRF-18 encode loses nothing.
TRACK_CRF = 10
#: Replay fidelity: a render of a snapshot at the policy's resolution against the frame the policy
#: received at that instant. Pass when the mean absolute difference is at most this many levels and
#: at least this share of pixel channels are within 8 levels.
FIDELITY_MAX_MEAN = 2.0
FIDELITY_MIN_CLOSE = 0.99

# --------------------------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------------------------- #


def apply_determinism(*, strict: bool) -> dict[str, Any]:
    """Set torch's determinism switches and return what is actually in force, read back.

    ``cudnn.deterministic`` on, ``cudnn.benchmark`` off, ``use_deterministic_algorithms(True)``
    (``warn_only`` unless ``strict``: an op with no deterministic kernel then warns instead of
    stopping the run, and the warnings are recorded), and ``CUBLAS_WORKSPACE_CONFIG=:4096:8``. The
    published runs set none of these; the execution manifest says so as a deviation. Without torch
    (the CPU build) nothing is set and the record says that.
    """
    record: dict[str, Any] = {
        "CUBLAS_WORKSPACE_CONFIG": os.environ.get("CUBLAS_WORKSPACE_CONFIG"),
        "requested": {
            "cudnn.deterministic": True,
            "cudnn.benchmark": False,
            "use_deterministic_algorithms": True,
            "warn_only": not strict,
        },
    }
    try:
        torch = importlib.import_module("torch")
    except ImportError:
        record["torch"] = None
        record["note"] = "torch is not installed here; no switch was set"
        return record
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True, warn_only=not strict)
    record.update(
        torch=str(torch.__version__),
        cuda=getattr(torch.version, "cuda", None),
        cudnn=(torch.backends.cudnn.version() if torch.backends.cudnn.is_available() else None),
        in_force={
            "cudnn.deterministic": bool(torch.backends.cudnn.deterministic),
            "cudnn.benchmark": bool(torch.backends.cudnn.benchmark),
            "use_deterministic_algorithms": bool(torch.are_deterministic_algorithms_enabled()),
            "warn_only": bool(torch.is_deterministic_algorithms_warn_only_enabled()),
            "allow_tf32_matmul": bool(torch.backends.cuda.matmul.allow_tf32),
            "allow_tf32_cudnn": bool(torch.backends.cudnn.allow_tf32),
        },
    )
    return record


def determinism_deviation(record: dict[str, Any]) -> str:
    in_force = record.get("in_force")
    if in_force is None:
        return "torch determinism: torch not installed in this process, nothing was set"
    return (
        "torch determinism set by the recorder (the published runs set none of it): "
        f"cudnn.deterministic={in_force['cudnn.deterministic']}, "
        f"cudnn.benchmark={in_force['cudnn.benchmark']}, "
        f"use_deterministic_algorithms={in_force['use_deterministic_algorithms']} "
        f"(warn_only={in_force['warn_only']}), "
        f"CUBLAS_WORKSPACE_CONFIG={record.get('CUBLAS_WORKSPACE_CONFIG')}"
    )


RECORDING_DEVIATION = (
    "recorded for video: the recorder kept stepping past the verdict for frames only; report.json "
    "holds the scored episode, which ends at the verdict"
)


# --------------------------------------------------------------------------------------------- #
# Orientation helpers
# --------------------------------------------------------------------------------------------- #

RELATIONS: dict[str, Callable[[npt.NDArray[Any]], npt.NDArray[Any]]] = {
    "identity": lambda a: a,
    "mirror_lr": lambda a: a[:, ::-1],
    "flip_ud": lambda a: a[::-1],
    "rotate_180": lambda a: a[::-1, ::-1],
}


def relation_between(source: npt.NDArray[Any], target: npt.NDArray[Any]) -> str | None:
    """The :data:`RELATIONS` entry that maps ``source`` onto ``target`` exactly, if one does."""
    for name, fn in RELATIONS.items():
        candidate = fn(source)
        if candidate.shape == target.shape and np.array_equal(candidate, target):
            return name
    return None


def frame_difference(a: npt.NDArray[Any], b: npt.NDArray[Any]) -> dict[str, float]:
    diff = np.abs(a.astype(np.int16) - b.astype(np.int16))
    return {
        "mean_abs": float(diff.mean()),
        "max_abs": float(diff.max()),
        "share_identical": float((diff == 0).mean()),
        "share_within_8": float((diff <= 8).mean()),
    }


# --------------------------------------------------------------------------------------------- #
# The recorder
# --------------------------------------------------------------------------------------------- #


class EpisodeVideoRecorder:
    """An :class:`~provael.recording.EpisodeRecorder` that keeps what a video of the episode needs.

    During the episode: the executed actions, a copy of each frame the policy received, and a
    simulator snapshot per step. Nothing is rendered until :meth:`finish`, after the policy has
    stopped acting. With ``record_video`` off it keeps the actions only — the control run of the
    identical-actions check.
    """

    continue_past_verdict = True

    def __init__(
        self,
        out: Path,
        *,
        record_video: bool,
        track_size: int = TRACK_SIZE,
        main_camera: str = MAIN_CAMERA,
        wide_cameras: Sequence[str] = WIDE_CAMERAS,
        ffmpeg: str | None = None,
    ) -> None:
        from provael.recording import ActionLog

        self.out = out
        self.record_video = record_video
        self.track_size = track_size
        self.main_camera = main_camera
        self.wide_cameras = tuple(wide_cameras)
        self.ffmpeg = ffmpeg
        self.log = ActionLog(continue_past_verdict=True)
        self.snapshots: list[npt.NDArray[np.float64]] = []
        self.policy_raw: list[npt.NDArray[np.uint8]] = []
        self.first_display: npt.NDArray[np.uint8] | None = None
        self.meta: dict[str, Any] = {}
        self._suite: Any = None
        self._source: Any = None

    # -- EpisodeRecorder ------------------------------------------------------------------------

    def begin(self, suite: Any, *, task: str, seed: int, attack: str) -> None:
        self._suite = suite
        self.meta.update(task=task, seed=seed, attack=attack)
        self.log.begin(suite, task=task, seed=seed, attack=attack)
        if not self.record_video:
            return
        source = suite.video_source()
        if source is None:
            raise RuntimeError(f"suite {suite.name!r} offers no video source; refusing to "
                               "record a video without its frames")
        present = list(source.cameras())
        if self.main_camera not in present:
            raise RuntimeError(f"the scene defines no {self.main_camera!r} camera; it has "
                               f"{present}")
        wide = next((c for c in self.wide_cameras if c in present), None)
        self._source = source
        self.meta.update(
            cameras_present=present,
            cameras_rendered=[self.main_camera, *([wide] if wide else [])],
            wide_camera=wide,
            wide_camera_preference=list(self.wide_cameras),
        )

    def observed(self, step: int, observation: Any) -> None:
        if self._source is None:
            return
        from provael.video import image_from

        self.snapshots.append(self._source.snapshot())
        raw = image_from(observation)
        if raw is None:
            raise RuntimeError(f"step {step}: the observation carries no camera frame to record")
        self.policy_raw.append(np.array(raw, dtype=np.uint8, copy=True))
        if self.first_display is None:
            shown = self._suite.display_frame(observation)
            self.first_display = None if shown is None else np.array(shown, dtype=np.uint8)

    def stepped(self, step: int, action: Any, *, unsafe: bool, scored: bool) -> None:
        self.log.stepped(step, action, unsafe=unsafe, scored=scored)

    def finish(self, suite: Any, result: Any, *, ended_by: str) -> None:
        self.log.finish(suite, result, ended_by=ended_by)
        self.meta.update(ended_by=ended_by, verdict_step=result.steps_to_success,
                         scored_steps=result.steps, recorded_steps=len(self.log.steps))
        if self._source is not None:
            self._write_video_material(suite, result)

    # -- after the episode ------------------------------------------------------------------------

    def _write_video_material(self, suite: Any, result: Any) -> None:
        from provael.recording import check_projection

        source = self._source
        upright = [np.ascontiguousarray(source.upright(f)) for f in self.policy_raw]
        if len(upright) != len(self.log.steps):
            raise RuntimeError(f"{len(upright)} frames for {len(self.log.steps)} steps")
        np.savez_compressed(self.out / "policy_view.npz", frames=np.stack(upright),
                            steps=np.asarray(self.log.steps, dtype=np.int32))

        # How the policy's own input relates to the upright frame (LIBERO: mirrored left-right).
        relation = (
            relation_between(upright[0], self.first_display)
            if self.first_display is not None else None
        )
        self.meta["policy_input_from_upright"] = relation

        # Replay fidelity, BEFORE any larger render can resize the renderer's buffer: a snapshot
        # rendered at the policy's resolution against the frame the policy received at that step.
        height, width = upright[0].shape[:2]
        verdict = result.steps_to_success
        indices = sorted({0, len(upright) - 1, *([verdict - 1] if verdict else [])})
        checks = []
        for i, frames in zip(
            indices,
            source.render([self.snapshots[i] for i in indices], [self.main_camera], width, height),
            strict=True,
        ):
            rendered = frames[self.main_camera]
            stats: dict[str, Any] = dict(frame_difference(rendered, upright[i]))
            stats.update(step=int(self.log.steps[i]),
                         best_relation=relation_between(rendered, upright[i]))
            checks.append(stats)
        passed = all(c["mean_abs"] <= FIDELITY_MAX_MEAN and c["share_within_8"]
                     >= FIDELITY_MIN_CLOSE for c in checks)
        self.meta["replay_fidelity"] = {
            "camera": self.main_camera, "size": [width, height], "passed": passed,
            "max_mean_abs": FIDELITY_MAX_MEAN, "min_share_within_8": FIDELITY_MIN_CLOSE,
            "checks": checks,
        }

        # The camera tracks, rendered from the snapshots now that nothing is acting.
        cams = list(self.meta["cameras_rendered"])
        tracks = self.out / "tracks"
        writers = {
            cam: video.FfmpegWriter(tracks / f"{cam}.mp4", self.track_size, self.track_size,
                                    crf=TRACK_CRF, preset="medium", pix_fmt="yuv444p",
                                    ffmpeg=self.ffmpeg)
            for cam in cams
        }
        with contextlib.ExitStack() as stack:
            for writer in writers.values():
                stack.enter_context(writer)
            for frames in source.render(self.snapshots, cams, self.track_size, self.track_size):
                for cam in cams:
                    writers[cam].write(frames[cam])
        self.meta["tracks"] = {
            cam: {"file": f"tracks/{cam}.mp4", "frames": writers[cam].frames,
                  "size": self.track_size, "crf": TRACK_CRF, "pix_fmt": "yuv444p"}
            for cam in cams
        }

        # The projection of each rendered camera, and the proof it is right (or why it is not).
        projections: dict[str, Any] = {}
        for cam in cams:
            proj = source.projection(cam, self.track_size, self.track_size)
            seg = source.segmentation(self.snapshots[0], cam, self.track_size, self.track_size)
            if proj is None or seg is None:
                projections[cam] = {
                    "projection": None if proj is None else proj.to_json_dict(),
                    "check": {"passed": False, "reason": "no projection" if proj is None
                              else "no segmentation render"},
                }
                continue
            projections[cam] = {"projection": proj.to_json_dict(),
                                "check": check_projection(proj, seg).to_json_dict()}
        self.meta["projections"] = projections
        self.meta["keep_out_zones"] = [
            z.model_dump() for z in suite.keep_out_zones(self.meta.get("task"))
        ]


# --------------------------------------------------------------------------------------------- #
# episode
# --------------------------------------------------------------------------------------------- #


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, timeout=10,
                             check=False, cwd=HERE)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def source_dirty() -> bool | None:
    """Whether the checkout the code runs from has uncommitted changes (``None``: cannot tell)."""
    explicit = os.environ.get("PROVAEL_SOURCE_DIRTY")
    if explicit in ("0", "1"):
        return explicit == "1"
    status = _git("status", "--porcelain", "--untracked-files=no")
    return None if status is None else bool(status)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


#: What an episode directory may hold. Anything else in it means ``--out`` points somewhere else,
#: and the directory is left alone rather than cleared.
EPISODE_FILES = frozenset({
    "report.json", "report.md", "execution-manifest.json", "actions.json", "recording.json",
    "policy_view.npz", "tracks",
})


def _clear_episode_dir(out: Path) -> None:
    """Remove a previous attempt at this episode, refusing if ``out`` holds anything else."""
    if not out.exists():
        return
    foreign = sorted(p.name for p in out.iterdir() if p.name not in EPISODE_FILES)
    if foreign:
        raise SystemExit(f"{out} holds files an episode does not write ({foreign[:5]}); "
                         "refusing to clear it. Pass an empty or episode-only directory.")
    shutil.rmtree(out)


def record_episode(
    out: Path,
    *,
    arm: str,
    seed: int,
    mode: str,
    synthetic: bool = False,
    strict_determinism: bool = False,
    horizon: int = HORIZON,
    pin_start: int | None = PIN_START,
    track_size: int = TRACK_SIZE,
) -> dict[str, Any]:
    """Run one episode through :func:`provael.runner.run` and write it the way ``attack`` does.

    ``recording.json`` is written last and is the completion marker the campaign resumes on.
    """
    from provael.cli._shared import _decide, _emit_execution_manifest
    from provael.config import RunConfig
    from provael.report import write_report
    from provael.runner import run

    if arm not in ARMS:
        raise ValueError(f"arm must be one of {sorted(ARMS)}, got {arm!r}")
    if mode not in ("video", "actions"):
        raise ValueError(f"mode must be 'video' or 'actions', got {mode!r}")
    _clear_episode_dir(out)
    out.mkdir(parents=True)
    determinism = apply_determinism(strict=strict_determinism)
    recorder = EpisodeVideoRecorder(out, record_video=mode == "video", track_size=track_size)

    if synthetic:
        import rfm_synthetic

        config = RunConfig(
            policy="stub", suite=rfm_synthetic.SUITE_NAME, tasks=[rfm_synthetic.TASK],
            attacks=[ARMS[arm]], episodes=1, seed=seed, horizon=horizon, out=out,
        )
        context: contextlib.AbstractContextManager[Any] = rfm_synthetic.installed()
    else:
        config = RunConfig(
            policy=POLICY, suite=SUITE, model=CHECKPOINT, tasks=[TASK], attacks=[ARMS[arm]],
            episodes=1, seed=seed, horizon=horizon, pin_init_states=pin_start, out=out,
        )
        context = contextlib.nullcontext()

    started = time.perf_counter()
    with warnings.catch_warnings(record=True) as caught, context:
        warnings.simplefilter("always")
        report = run(config, recorder_factory=lambda _t, _s, _a: recorder)
    elapsed = time.perf_counter() - started
    nondeterministic = sorted({str(w.message) for w in caught
                               if "determinis" in str(w.message).lower()})

    decision = _decide(report, None)
    write_report(report, out, decision)
    _emit_execution_manifest(report, out, elapsed=elapsed, decision=decision,
                             deviations=[RECORDING_DEVIATION, determinism_deviation(determinism)])
    write_json(out / "actions.json", recorder.log.to_json_dict())

    result = report.results[0]
    expected = EXPECTED_INSTRUCTIONS[arm]
    meta: dict[str, Any] = {
        "kind": "rfm-episode-recording",
        "not_a_report": "report.json beside this file is the measured episode; this is a sidecar",
        "synthetic": synthetic,
        "arm": arm,
        "attack": ARMS[arm],
        "mode": mode,
        "seed": seed,
        "pin_init_states": None if synthetic else pin_start,
        "init_state": result.init_state,
        "horizon": horizon,
        "instruction": result.adversarial_instruction,
        "instruction_expected": expected,
        "instruction_matches": synthetic or result.adversarial_instruction == expected,
        "left_envelope": bool(result.success),
        "task_success": result.task_success,
        "determinism": determinism,
        "nondeterministic_op_warnings": nondeterministic,
        "source_dirty": source_dirty(),
        "elapsed_s": round(elapsed, 1),
        **recorder.meta,
        "frames": [
            {"index": i, "step": s, "scored": sc, "unsafe": u}
            for i, (s, sc, u) in enumerate(
                zip(recorder.log.steps, recorder.log.scored, recorder.log.unsafe, strict=True)
            )
        ] if mode == "video" else [],
    }
    write_json(out / "recording.json", meta)
    return meta


# --------------------------------------------------------------------------------------------- #
# check-actions
# --------------------------------------------------------------------------------------------- #


def check_actions(recorded: Path, plain_a: Path, plain_b: Path) -> dict[str, Any]:
    """The identical-actions check over three runs of one episode.

    ``plain_a`` against ``plain_b`` first: two runs with no frames recorded. If they differ, the
    hardware path is not deterministic and no difference elsewhere can be blamed on recording, which
    the verdict says in those words. Then ``plain_a`` against ``recorded``.
    """
    from provael.recording import compare_actions

    def load(p: Path) -> dict[str, Any]:
        data: dict[str, Any] = json.loads((p / "actions.json").read_text(encoding="utf-8"))
        return data

    a, b, r = load(plain_a), load(plain_b), load(recorded)
    baseline = compare_actions(a, b)
    recording = compare_actions(a, r)
    if not baseline.identical:
        verdict = (
            "NOT DETERMINISTIC: two plain runs of the same episode, with no frames recorded, "
            f"already differ ({baseline.summary()}). The comparison with the recorded run cannot "
            "separate the effect of recording from this run-to-run difference."
        )
    elif recording.identical:
        verdict = ("IDENTICAL: the recorded run emitted exactly the actions of two plain runs "
                   f"({recording.summary()}).")
    else:
        verdict = ("RECORDING CHANGED THE ACTIONS: two plain runs agree, and the recorded run "
                   f"departs from them ({recording.summary()}).")
    return {
        "kind": "identical-actions-check",
        "runs": {"recorded": str(recorded), "plain_a": str(plain_a), "plain_b": str(plain_b)},
        "plain_a_vs_plain_b": baseline.__dict__,
        "plain_a_vs_recorded": recording.__dict__,
        "baseline_deterministic": baseline.identical,
        "recording_identical": recording.identical,
        "verdict": verdict,
    }


# --------------------------------------------------------------------------------------------- #
# compose
# --------------------------------------------------------------------------------------------- #

POLICY_NAMES = {"smolvla": "SmolVLA", "stub": "stub policy (CPU fixture)"}


@dataclass
class Recorded:
    """One recorded episode as compose reads it: artifacts only, nothing re-measured."""

    path: Path
    report: dict[str, Any]
    manifest: dict[str, Any]
    recording: dict[str, Any]

    @classmethod
    def load(cls, path: Path) -> Recorded:
        def read(name: str) -> dict[str, Any]:
            data: dict[str, Any] = json.loads((path / name).read_text(encoding="utf-8"))
            return data

        rec = read("recording.json")
        if rec.get("mode") != "video":
            raise ValueError(f"{path} was recorded with actions only; it has no frames")
        return cls(path, read("report.json"), read("execution-manifest.json"), rec)

    @property
    def result(self) -> dict[str, Any]:
        results = self.report["results"]
        if len(results) != 1:
            raise ValueError(f"{self.path}: expected one episode, the report holds {len(results)}")
        row: dict[str, Any] = results[0]
        return row

    @property
    def verdict_step(self) -> int | None:
        value = self.result.get("steps_to_success")
        return None if value is None else int(value)

    @property
    def done_step(self) -> int | None:
        """The scored step at which the task was completed, only when the report says so."""
        if self.result.get("task_success") is True and self.result.get("success") is False:
            return int(self.result["steps"])
        return None

    def task_line(self) -> str:
        task = str(self.result["task"])
        seed = int(self.result["seed"])
        init = self.result.get("init_state")
        scene = "" if init is None else f" · starting scene {init}"
        if task.startswith("libero_object/"):
            return f"LIBERO-Object task {task.split('/')[1]} · seed {seed}{scene}"
        return f"{task} (synthetic scene, no simulator) · seed {seed}{scene}"

    def model_line(self) -> str:
        policy = str(self.report["policy"])
        model = self.report.get("model")
        name = POLICY_NAMES.get(policy, policy)
        return f"{name} · {model}" if model else name

    def text(self) -> video.EpisodeText:
        arm = str(self.recording["arm"])
        return video.EpisodeText(
            model_line=self.model_line(),
            task_line=self.task_line(),
            instruction=str(self.result["adversarial_instruction"]),
            horizon=int(self.report["horizon"]),
            arm_label="roleplay instruction" if arm == "roleplay" else "task instruction",
        )

    def provenance(self) -> str:
        commit = self.manifest.get("commit") or "unrecorded"
        if self.recording.get("source_dirty"):
            commit = f"{commit} (with uncommitted changes)"
        ended = str(self.manifest.get("ended_at") or "")[:10] or "undated"
        return video.PROVENANCE_LINE.format(
            version=self.manifest.get("package_version", "unknown"), commit=commit, date=ended
        )

    def boundary(self, camera: str) -> tuple[video.Boundary | None, str]:
        """The proven keep-out boundary for ``camera``, or ``None`` and why it is not drawn."""
        from provael.recording import CameraProjection

        entry = self.recording.get("projections", {}).get(camera)
        if entry is None or entry.get("projection") is None:
            return None, f"no projection recorded for {camera}"
        check = entry.get("check", {})
        if not check.get("passed"):
            return None, f"projection check did not pass: {check.get('reason')}"
        proj = CameraProjection.from_json_dict(entry["projection"])
        segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
        for zone in self.recording.get("keep_out_zones", []):
            segments.extend(box_segments(proj, zone["x"], zone["y"], zone["z"]))
        if not segments:
            return None, "the keep-out box projects outside the image"
        return video.Boundary(tuple(segments), proj.width), "projection check passed"


def box_segments(
    projection: Any, xs: Sequence[float], ys: Sequence[float], zs: Sequence[float]
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """The twelve edges of an axis-aligned box in pixels, clipped to the image, in front only."""
    corners = [(x, y, z) for x in xs for y in ys for z in zs]
    uv, front = projection.project(corners)
    edges = [(i, j) for i in range(8) for j in range(i + 1, 8)
             if sum(a != b for a, b in zip(corners[i], corners[j], strict=True)) == 1]
    out: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for i, j in edges:
        if not (front[i] and front[j]):
            continue
        clipped = _clip((float(uv[i, 0]), float(uv[i, 1])), (float(uv[j, 0]), float(uv[j, 1])),
                        projection.width, projection.height)
        if clipped is not None:
            out.append(clipped)
    return out


def _clip(
    a: tuple[float, float], b: tuple[float, float], width: float, height: float
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Liang-Barsky clipping of segment ``a``-``b`` to the image rectangle."""
    x0, y0 = a
    dx, dy = b[0] - x0, b[1] - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0), (dx, width - x0), (-dy, y0), (dy, height - y0)):
        if p == 0:
            if q < 0:
                return None
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return None
    return (x0 + t0 * dx, y0 + t0 * dy), (x0 + t1 * dx, y0 + t1 * dy)


def _panels(
    episode: Recorded, *, camera: str, inset_orientation: str, ffmpeg: str | None
) -> Iterator[video.Panel]:
    track = episode.recording["tracks"][camera]
    size = int(track["size"])
    policy = np.load(episode.path / "policy_view.npz")["frames"]
    relation = episode.recording.get("policy_input_from_upright")
    if inset_orientation == "policy" and relation not in RELATIONS:
        raise ValueError(f"{episode.path}: the policy-input orientation was not established "
                         f"({relation!r}); use --inset-orientation physical")
    verdict = episode.verdict_step
    frames = episode.recording["frames"]
    count = 0
    decoded = contextlib.closing(
        video.read_frames(episode.path / track["file"], size, size, ffmpeg=ffmpeg)
    )
    with decoded as views:
        for meta, view in zip(frames, views, strict=False):
            count += 1
            yield _panel(meta, view, policy, relation, inset_orientation, verdict)
    if count != len(frames):
        raise ValueError(f"{episode.path}: {count} decoded frames for {len(frames)} recorded")


def _panel(
    meta: dict[str, Any],
    view: npt.NDArray[np.uint8],
    policy: npt.NDArray[np.uint8],
    relation: str | None,
    inset_orientation: str,
    verdict: int | None,
) -> video.Panel:
    index = int(meta["index"])
    inset = policy[index]
    if inset_orientation == "policy" and relation is not None:
        inset = np.ascontiguousarray(RELATIONS[relation](inset))
    step = int(meta["step"])
    exit_step = verdict if verdict is not None and step >= verdict else None
    return video.Panel(view=view, inset=inset, step=step, exit_step=exit_step, done_step=None)


def _hold(panel: video.Panel, episode: Recorded) -> video.Panel:
    return video.Panel(view=panel.view, inset=panel.inset, step=panel.step,
                       exit_step=panel.exit_step,
                       done_step=episode.done_step if panel.exit_step is None else None)


def _watermark(frame: npt.NDArray[np.uint8], painter: video.Painter) -> npt.NDArray[np.uint8]:
    from PIL import Image, ImageDraw

    image = Image.fromarray(frame, "RGB")
    draw = ImageDraw.Draw(image)
    painter.text(draw, (image.width / 2, image.height - 30),
                 "SYNTHETIC TEST FRAMES · NOT A SIMULATOR RUN", size=26, weight="bold",
                 fill=(255, 80, 80), anchor="mm")
    return np.asarray(image, dtype=np.uint8)


def compose(
    roleplay_dir: Path,
    benign_dir: Path,
    out: Path,
    *,
    camera: str = MAIN_CAMERA,
    inset_orientation: str = "physical",
    draw_boundary: bool = True,
    names: dict[str, str] | None = None,
    ffmpeg: str | None = None,
    preset: str = video.PRESET,
) -> dict[str, Any]:
    """The three submitted MP4s, their SHA-256s and a ``compose.json`` saying how they were made."""
    names = dict(VIDEO_NAMES if names is None else names)
    exe = ffmpeg or video.find_ffmpeg()
    roleplay, benign = Recorded.load(roleplay_dir), Recorded.load(benign_dir)
    synthetic = bool(roleplay.recording.get("synthetic") or benign.recording.get("synthetic"))
    painter = video.Painter()
    boundaries: dict[str, video.Boundary | None] = {}
    boundary_notes: dict[str, str] = {}
    for key, ep in (("roleplay", roleplay), ("benign", benign)):
        if draw_boundary:
            boundaries[key], boundary_notes[key] = ep.boundary(camera)
        else:
            boundaries[key], boundary_notes[key] = None, "not asked for (--no-boundary)"

    def mark(frame: npt.NDArray[np.uint8]) -> npt.NDArray[np.uint8]:
        return _watermark(frame, painter) if synthetic else frame

    def single(ep: Recorded, key: str) -> Callable[[], Iterator[npt.NDArray[np.uint8]]]:
        text = ep.text()

        def frames() -> Iterator[npt.NDArray[np.uint8]]:
            yield from video.repeat(mark(video.render_title_card(
                [text], "SmolVLA in simulation" if not synthetic else "Synthetic test scene",
                [text.task_line, f"checkpoint {ep.report.get('model') or 'none (CPU fixture)'}"],
                painter,
                size=video.SINGLE_SIZE)), video.TITLE_SECONDS)
            last: video.Panel | None = None
            for panel in _panels(ep, camera=camera, inset_orientation=inset_orientation,
                                 ffmpeg=exe):
                last = panel
                yield mark(video.render_single_frame(panel, text, painter,
                                                     boundary=boundaries[key]))
            if last is not None:
                yield from video.repeat(mark(video.render_single_frame(
                    _hold(last, ep), text, painter, boundary=boundaries[key])),
                    video.HOLD_SECONDS)
            yield from video.repeat(mark(video.render_end_card(
                painter, ep.provenance(), size=video.SINGLE_SIZE)), video.END_SECONDS)

        return frames

    scene_b, scene_r = benign.result.get("init_state"), roleplay.result.get("init_state")
    same_scene = scene_b is not None and scene_b == scene_r
    if same_scene:
        scene = f"same starting scene {scene_r}"
    elif scene_b is None and scene_r is None:
        scene = "no fixed starting scene"
    else:
        scene = f"starting scenes {scene_b} and {scene_r}"
    header = (f"{roleplay.model_line()} · {roleplay.task_line().split(' · seed')[0]} · "
              f"seed {roleplay.result['seed']} · {scene}")

    def pair() -> Iterator[npt.NDArray[np.uint8]]:
        texts = (benign.text(), roleplay.text())
        yield from video.repeat(mark(video.render_title_card(
            list(texts), "Same starting scene, two instructions" if same_scene
            else "Two instructions", [header], painter, size=video.PAIR_SIZE)),
            video.TITLE_SECONDS)
        left_iter = _panels(benign, camera=camera, inset_orientation=inset_orientation, ffmpeg=exe)
        right_iter = _panels(roleplay, camera=camera, inset_orientation=inset_orientation,
                             ffmpeg=exe)
        left = right = None
        left_done = right_done = False
        while True:
            if not left_done:
                left_next = next(left_iter, None)
                left_done = left_next is None
                left = left_next or left
            if not right_done:
                right_next = next(right_iter, None)
                right_done = right_next is None
                right = right_next or right
            if left_done and right_done:
                break
            if left is None or right is None:
                raise ValueError("an episode has no frames to compose")
            lp = _hold(left, benign) if left_done else left
            rp = _hold(right, roleplay) if right_done else right
            yield mark(video.render_pair_frame(lp, rp, texts, header, painter,
                                               boundaries=(boundaries["benign"],
                                                           boundaries["roleplay"])))
        if left is None or right is None:
            raise ValueError("an episode has no frames to compose")
        yield from video.repeat(mark(video.render_pair_frame(
            _hold(left, benign), _hold(right, roleplay), texts, header, painter,
            boundaries=(boundaries["benign"], boundaries["roleplay"]))), video.HOLD_SECONDS)
        yield from video.repeat(mark(video.render_end_card(
            painter, roleplay.provenance(), size=video.PAIR_SIZE)), video.END_SECONDS)

    out.mkdir(parents=True, exist_ok=True)
    jobs: list[tuple[str, Callable[[], Iterator[npt.NDArray[np.uint8]]], tuple[int, int]]] = [
        ("roleplay", single(roleplay, "roleplay"), video.SINGLE_SIZE),
        ("benign", single(benign, "benign"), video.SINGLE_SIZE),
        ("pair", pair, video.PAIR_SIZE),
    ]
    outputs: dict[str, Any] = {}
    for key, make, size in jobs:
        encoded = video.encode_frames(make, out / names[key], size, ffmpeg=exe, preset=preset)
        outputs[key] = {
            "file": names[key], "sha256": encoded.sha256, "bytes": encoded.bytes,
            "frames": encoded.frames, "crf": encoded.crf, "attempts": list(encoded.attempts),
            "probe": video.probe(out / names[key], ffmpeg=exe),
        }
    (out / "SHA256SUMS").write_text(
        "".join(f"{o['sha256']}  {o['file']}\n" for o in outputs.values()), encoding="utf-8"
    )
    drawn = sorted(set(painter.log))
    report = {
        "kind": "rfm-compose",
        "synthetic": synthetic,
        "videos": outputs,
        "camera": camera,
        "inset_orientation": inset_orientation,
        "boundary": boundary_notes,
        "episodes": {"roleplay": str(roleplay_dir), "benign": str(benign_dir)},
        "same_starting_scene": same_scene,
        "ffmpeg": video.ffmpeg_version(exe),
        "fonts": {k: {"file": f, "sha256": h} for k, (f, h) in video.FONTS.items()},
        "font_licence": video.FONT_LICENCE,
        "fps": video.FPS,
        "crf_requested": video.CRF,
        "preset": preset,
        "title_seconds": video.TITLE_SECONDS,
        "hold_seconds": video.HOLD_SECONDS,
        "end_seconds": video.END_SECONDS,
        "text_drawn": drawn,
        "banned_words_found": sorted({w for s in drawn for w in video.banned_words_in(s)}),
    }
    write_json(out / "compose.json", report)
    return report


# --------------------------------------------------------------------------------------------- #
# campaign
# --------------------------------------------------------------------------------------------- #


def _complete(episode: Path, *, arm: str, seed: int, mode: str) -> bool:
    marker = episode / "recording.json"
    if not marker.is_file():
        return False
    meta = json.loads(marker.read_text(encoding="utf-8"))
    return bool(meta.get("arm") == arm and meta.get("seed") == seed and meta.get("mode") == mode)


def ensure_episode(
    episode: Path,
    *,
    arm: str,
    seed: int,
    mode: str,
    synthetic: bool,
    strict_determinism: bool,
    horizon: int,
    python: str = sys.executable,
) -> dict[str, Any]:
    """Record ``episode`` in a fresh process unless a completed recording is already there."""
    if not _complete(episode, arm=arm, seed=seed, mode=mode):
        cmd = [python, str(HERE / "rfm_record.py"), "episode", "--arm", arm, "--seed", str(seed),
               "--mode", mode, "--out", str(episode), "--horizon", str(horizon)]
        if synthetic:
            cmd.append("--synthetic")
        if strict_determinism:
            cmd.append("--strict-determinism")
        print(f"$ {' '.join(cmd)}", flush=True)
        subprocess.run(cmd, check=True)
    meta: dict[str, Any] = json.loads((episode / "recording.json").read_text(encoding="utf-8"))
    return meta


def campaign(
    out: Path,
    *,
    synthetic: bool = False,
    strict_determinism: bool = False,
    horizon: int = HORIZON,
    after_each: Callable[[], None] | None = None,
    compose_anyway: bool = False,
    preset: str = video.PRESET,
    draw_boundary: bool = False,
) -> int:
    """The whole plan, resumable: a completed episode is never re-run. Returns an exit code.

    ``draw_boundary`` is off by default (operator decision, 4 November 2026): the predicate
    fires when the end-effector enters the default box, which the product reads as leaving the
    benign envelope, so a drawn box would show the arm entering a box under a marker that says
    it left an envelope.
    """
    out.mkdir(parents=True, exist_ok=True)
    state: dict[str, Any] = {"kind": "rfm-campaign", "synthetic": synthetic,
                             "selection_seeds": list(SELECTION_SEEDS), "roleplay_runs": []}

    def save() -> None:
        write_json(out / "campaign.json", state)
        if after_each is not None:
            after_each()

    def run_one(path: Path, arm: str, seed: int, mode: str) -> dict[str, Any]:
        meta = ensure_episode(path, arm=arm, seed=seed, mode=mode, synthetic=synthetic,
                              strict_determinism=strict_determinism, horizon=horizon)
        if not meta.get("instruction_matches", False):
            raise SystemExit(f"{path}: the policy received {meta.get('instruction')!r}, not the "
                             f"specified {meta.get('instruction_expected')!r}; stopping")
        return meta

    episodes = out / "episodes"
    outcomes: list[tuple[int, bool]] = []
    for seed in SELECTION_SEEDS:
        meta = run_one(episodes / f"roleplay_seed{seed}", "roleplay", seed, "video")
        outcomes.append((seed, bool(meta["left_envelope"])))
        state["roleplay_runs"].append({
            "seed": seed, "left_envelope": meta["left_envelope"],
            "verdict_step": meta.get("verdict_step"), "init_state": meta.get("init_state"),
            "path": f"episodes/roleplay_seed{seed}",
        })
        save()
        if meta["left_envelope"]:
            break
    selected = select_seed(outcomes)
    state["selected_seed"] = selected
    if selected is None:
        state["result"] = ("no seed in 0-4 left the envelope with pinned init; nothing is "
                           "selected and nothing is composed; every run is kept")
        save()
        print(state["result"], flush=True)
        return 3

    benign = run_one(episodes / f"benign_seed{selected}", "benign", selected, "video")
    state["benign_run"] = {"seed": selected, "left_envelope": benign["left_envelope"],
                           "task_success": benign["task_success"],
                           "init_state": benign.get("init_state"),
                           "path": f"episodes/benign_seed{selected}"}
    save()
    roleplay_meta = state["roleplay_runs"][-1]
    if not synthetic and benign.get("init_state") != roleplay_meta.get("init_state"):
        raise SystemExit("the benign and roleplay episodes started from different scenes "
                         f"({benign.get('init_state')} vs {roleplay_meta.get('init_state')})")

    checks = out / "checks"
    plain = [checks / f"roleplay_seed{selected}_plain_{tag}" for tag in ("a", "b")]
    for path in plain:
        run_one(path, "roleplay", selected, "actions")
        save()
    verdict = check_actions(episodes / f"roleplay_seed{selected}", plain[0], plain[1])
    write_json(checks / "identical_actions.json", verdict)
    state["identical_actions"] = {"verdict": verdict["verdict"],
                                  "file": "checks/identical_actions.json"}
    save()
    print(verdict["verdict"], flush=True)
    if (verdict["baseline_deterministic"] and not verdict["recording_identical"]
            and not compose_anyway):
        state["result"] = "stopped before composing: recording changed the actions"
        save()
        return 4

    composed = compose(episodes / f"roleplay_seed{selected}", episodes / f"benign_seed{selected}",
                       out, preset=preset, draw_boundary=draw_boundary)
    state["videos"] = {k: {"file": v["file"], "sha256": v["sha256"], "bytes": v["bytes"]}
                       for k, v in composed["videos"].items()}
    state["result"] = "composed"
    save()
    return 0


# --------------------------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------------------------- #


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rfm_record.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    ep = sub.add_parser("episode", help="record one arm at one seed")
    ep.add_argument("--arm", choices=sorted(ARMS), required=True)
    ep.add_argument("--seed", type=int, required=True)
    ep.add_argument("--mode", choices=("video", "actions"), default="video")
    ep.add_argument("--out", type=Path, required=True)
    ep.add_argument("--horizon", type=int, default=HORIZON)
    ep.add_argument("--synthetic", action="store_true")
    ep.add_argument("--strict-determinism", action="store_true")

    ck = sub.add_parser("check-actions", help="compare action logs exactly")
    ck.add_argument("--recorded", type=Path, required=True)
    ck.add_argument("--plain-a", type=Path, required=True)
    ck.add_argument("--plain-b", type=Path, required=True)
    ck.add_argument("--out", type=Path)

    co = sub.add_parser("compose", help="compose the three MP4s from recorded episodes")
    co.add_argument("--roleplay", type=Path, required=True)
    co.add_argument("--benign", type=Path, required=True)
    co.add_argument("--out", type=Path, required=True)
    co.add_argument("--camera", default=MAIN_CAMERA)
    co.add_argument("--inset-orientation", choices=("physical", "policy"), default="physical")
    co.add_argument("--no-boundary", action="store_true")

    for name, helptext in (("campaign", "the whole plan on the GPU box"),
                           ("synthetic", "the whole plan on a synthetic CPU scene")):
        cp = sub.add_parser(name, help=helptext)
        cp.add_argument("--out", type=Path, required=True)
        cp.add_argument("--strict-determinism", action="store_true")
        cp.add_argument("--compose-anyway", action="store_true")
        cp.add_argument("--horizon", type=int, default=HORIZON)
        cp.add_argument("--preset", default=video.PRESET)
        cp.add_argument("--draw-boundary", action="store_true",
                        help="draw the default keep-out box when its projection check passes "
                             "(off by default)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "episode":
        meta = record_episode(args.out, arm=args.arm, seed=args.seed, mode=args.mode,
                              synthetic=args.synthetic, horizon=args.horizon,
                              strict_determinism=args.strict_determinism)
        print(json.dumps({k: meta.get(k) for k in (
            "arm", "seed", "mode", "init_state", "left_envelope", "verdict_step",
            "recorded_steps", "ended_by", "instruction_matches")}, indent=2), flush=True)
        return 0
    if args.command == "check-actions":
        verdict = check_actions(args.recorded, args.plain_a, args.plain_b)
        if args.out is not None:
            write_json(args.out, verdict)
        print(verdict["verdict"], flush=True)
        return 0 if verdict["recording_identical"] and verdict["baseline_deterministic"] else 1
    if args.command == "compose":
        report = compose(args.roleplay, args.benign, args.out, camera=args.camera,
                         inset_orientation=args.inset_orientation,
                         draw_boundary=not args.no_boundary)
        print(json.dumps(report["videos"], indent=2), flush=True)
        return 0
    return campaign(args.out, synthetic=args.command == "synthetic",
                    strict_determinism=args.strict_determinism, horizon=args.horizon,
                    compose_anyway=args.compose_anyway, preset=args.preset,
                    draw_boundary=args.draw_boundary)


if __name__ == "__main__":
    raise SystemExit(main())
