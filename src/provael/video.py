# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Episode video: the frames the policy actually saw, written beside the report as MP4.

WHY THIS EXISTS. Every LIBERO step already renders the camera image the policy consumes; until now
those frames went into the model and nowhere else. A rate like 44/50 is the product, but the thing
a reader believes is the clip — the arm turning away from the basket on the roleplay sentence, and
its benign twin at the same seed finishing the task. This writes that clip, per episode, from the
observation *after* the attack and any defense have acted on it, so a patched image is recorded
patched and a canonicalised instruction's episode is recorded as the policy received it.

WHAT IT MUST NOT DO. Touch the report. Frames are copied out of the observation; nothing here
feeds back into the loop, the scorer or ``report.json``, and the flag that enables recording is a
runner argument, not a ``RunConfig`` field — a config field would move the canonical JSON and
therefore every attestation subject digest issued before it (see ``run_episode``'s ``audit_sink``
for the same reasoning). A run with recording on and a run with it off produce byte-identical
reports.

THE UNSAFE STEP IS MARKED, NOT INTERPRETED. The frame at which the suite's predicate first fired is
bordered in red for the rest of the episode; nothing is drawn that the predicate did not decide.
Frames from replayed (``--resume``) episodes are not available — they were never re-rendered — and
those episodes simply have no clip, which the file listing makes obvious.

DEPENDENCIES ARE LAZY. ``imageio`` and its ffmpeg plugin ship with the ``[lerobot]`` extra but not
with the CPU core; :class:`Mp4Writer` imports them on first use and raises a clear error otherwise.
A :class:`FrameList` sink collects frames in memory for tests and for callers that want to compose
their own output (a side-by-side of attacked and benign twins is a few lines on top of it).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

from provael.types import IMAGE_KEY, Observation

#: Width of the red border drawn on frames at and after the first unsafe step.
BORDER_PX = 6
#: Frames per second written to disk. LIBERO runs at 20 Hz (robosuite control frequency);
#: 20 keeps a clip at real time.
DEFAULT_FPS = 20


class FrameSink(Protocol):
    """Receives, per step, the image the policy was shown and whether that step was unsafe."""

    def frame(self, step: int, image: npt.NDArray[Any], unsafe: bool) -> None: ...

    def close(self) -> None: ...


class FrameList:
    """An in-memory sink: ``frames`` holds ``(step, image, unsafe)`` in order."""

    def __init__(self) -> None:
        self.frames: list[tuple[int, npt.NDArray[Any], bool]] = []
        self.closed = False

    def frame(self, step: int, image: npt.NDArray[Any], unsafe: bool) -> None:
        self.frames.append((step, np.array(image, copy=True), unsafe))

    def close(self) -> None:
        self.closed = True


def image_from(observation: Observation) -> npt.NDArray[np.uint8] | None:
    """The RGB uint8 ``(H, W, 3)`` frame in an observation, or ``None`` if it carries no image.

    Accepts what the adapters emit: ``uint8`` HWC, ``float`` HWC in ``[0, 1]``, and CHW variants
    of either. Anything else is returned as ``None`` rather than guessed at — a wrong-shaped clip
    is worse than a missing one.
    """
    raw = observation.get(IMAGE_KEY)
    if raw is None:
        return None
    arr = np.asarray(raw)
    if arr.ndim == 4 and arr.shape[0] == 1:
        arr = arr[0]
    if arr.ndim != 3:
        return None
    if arr.shape[0] in (1, 3) and arr.shape[-1] not in (1, 3):
        arr = np.moveaxis(arr, 0, -1)  # CHW -> HWC
    if arr.shape[-1] == 1:
        arr = np.repeat(arr, 3, axis=-1)
    if arr.shape[-1] != 3:
        return None
    if arr.dtype != np.uint8:
        scaled = np.clip(arr.astype(np.float32), 0.0, 1.0) * 255.0
        arr = scaled.astype(np.uint8)
    return np.ascontiguousarray(arr)


def mark_unsafe(image: npt.NDArray[np.uint8]) -> npt.NDArray[np.uint8]:
    """A copy of ``image`` with a red border: the suite's predicate has fired."""
    out = np.array(image, copy=True)
    b = min(BORDER_PX, out.shape[0] // 2, out.shape[1] // 2)
    out[:b, :, :] = (220, 30, 30)
    out[-b:, :, :] = (220, 30, 30)
    out[:, :b, :] = (220, 30, 30)
    out[:, -b:, :] = (220, 30, 30)
    return out


def clip_name(task: str, seed: int, attack: str) -> str:
    """``libero_object/3`` + seed 2 + ``roleplay`` -> ``libero_object-3__seed2__roleplay.mp4``."""
    safe_task = re.sub(r"[^A-Za-z0-9_.-]+", "-", task)
    return f"{safe_task}__seed{seed}__{attack}.mp4"


class Mp4Writer:
    """One episode's frames to an MP4 as they arrive, red-bordered from the first unsafe step.

    Frames are written with ``imageio``'s ffmpeg plugin (H.264, ``yuv420p`` so every player opens
    it). The border latches: once the predicate fires, every later frame carries it, so a viewer
    scrubbing the clip sees where the episode was scored, not only the single frame.
    """

    def __init__(self, path: Path, *, fps: int = DEFAULT_FPS) -> None:
        try:
            import imageio.v2 as imageio  # noqa: PLC0415 - optional, lazy by design
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise ImportError(
                "episode video needs imageio with its ffmpeg plugin: "
                "pip install imageio imageio-ffmpeg (both ship with provael[lerobot])"
            ) from exc
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._writer = imageio.get_writer(
            str(path), fps=fps, codec="libx264", pixelformat="yuv420p", macro_block_size=1
        )
        self._unsafe_seen = False
        self.frames_written = 0

    def frame(self, step: int, image: npt.NDArray[Any], unsafe: bool) -> None:
        del step
        rgb = image_from({IMAGE_KEY: image})
        if rgb is None:
            return
        self._unsafe_seen = self._unsafe_seen or unsafe
        self._writer.append_data(mark_unsafe(rgb) if self._unsafe_seen else rgb)
        self.frames_written += 1

    def close(self) -> None:
        self._writer.close()


#: Width of the divider drawn between the two halves of a composed clip.
GAP_PX = 8


def _read_frames(path: Path) -> list[npt.NDArray[np.uint8]]:
    """Every frame of an MP4 as RGB uint8 ``(H, W, 3)`` arrays, in order."""
    import imageio.v2 as imageio  # noqa: PLC0415 - optional, lazy by design

    reader = imageio.get_reader(str(path))
    try:
        return [np.ascontiguousarray(np.asarray(f)[..., :3], dtype=np.uint8) for f in reader]
    finally:
        reader.close()


def _pad_to_height(frame: npt.NDArray[np.uint8], height: int) -> npt.NDArray[np.uint8]:
    if frame.shape[0] >= height:
        return frame
    pad = np.zeros((height - frame.shape[0], frame.shape[1], 3), dtype=np.uint8)
    return np.concatenate([frame, pad], axis=0)


def compose_side_by_side(
    left: Path, right: Path, out: Path, *, fps: int = DEFAULT_FPS, gap_px: int = GAP_PX
) -> int:
    """Write ``out`` with ``left`` and ``right`` playing beside each other, aligned step for step.

    The reader's clip: the benign twin on one side, the attacked episode on the other, at the same
    task and seed, so the divergence is visible at the step it happens and the red border on the
    attacked half marks where the predicate fired. The shorter clip holds its last frame until the
    longer one ends — an episode the predicate stopped early stays on screen at its verdict rather
    than vanishing. Frames are composed exactly as written by :class:`Mp4Writer`; nothing is drawn
    that the clips do not already carry, and the divider is the only added pixel.

    Returns the number of frames written.
    """
    a, b = _read_frames(left), _read_frames(right)
    if not a or not b:
        raise ValueError(f"nothing to compose: {left} has {len(a)} frames, {right} has {len(b)}")
    height = max(a[0].shape[0], b[0].shape[0])
    divider = np.full((height, gap_px, 3), 200, dtype=np.uint8)
    writer = Mp4Writer(out, fps=fps)
    n = max(len(a), len(b))
    for t in range(n):
        fa = _pad_to_height(a[min(t, len(a) - 1)], height)
        fb = _pad_to_height(b[min(t, len(b) - 1)], height)
        writer.frame(t + 1, np.concatenate([fa, divider, fb], axis=1), unsafe=False)
    writer.close()
    return writer.frames_written


__all__ = [
    "BORDER_PX",
    "DEFAULT_FPS",
    "GAP_PX",
    "FrameList",
    "FrameSink",
    "Mp4Writer",
    "clip_name",
    "compose_side_by_side",
    "image_from",
    "mark_unsafe",
]
