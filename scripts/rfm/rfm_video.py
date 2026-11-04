# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Overlays, title and end cards, and H.264 encoding for the RFM Safety Failures episode videos.

CPU ONLY, AND PURE FROM ITS INPUTS. Everything here composes frames a GPU run already recorded
(:mod:`rfm_record` writes them) into the submitted MP4s, so a wording change on a card is a re-run
of this module on the Mac, never a GPU job. Pixels come from the recorded camera tracks and the
policy's own frames; text comes from the constants below and from the episode's ``report.json``
and ``execution-manifest.json``, so nothing on screen is typed in at compose time.

WHAT IS NEVER ON SCREEN. :data:`BANNED_WORDS`: every string is drawn through :meth:`Painter.text`,
which refuses a banned word before it reaches a pixel and keeps a log of what it drew, and
``tests/test_rfm_video.py`` greps that log for a whole rendered video. The end card is one constant,
:data:`END_CARD_LINES`, so the wording changes in one place and the guard still applies.

WHY A BUNDLED FONT. Text rendered from a system font changes with the machine. ``fonts/`` holds
JetBrains Mono 2.304 (SIL Open Font License 1.1, ``fonts/OFL.txt``; the TTFs' own name tables say
the same), each file pinned by SHA-256 in :data:`FONTS` and checked before use, and Pillow's BASIC
layout engine is forced so libraqm's presence or absence cannot move a glyph. With the locked Pillow
the same frames render to the same pixels on any Linux box.

ENCODING. ``ffmpeg`` with libx264, ``yuv420p``, CRF :data:`CRF`, constant :data:`FPS` frames per
second (the simulator's 20 Hz control rate, so one frame is one step and playback is real time), no
interpolation. The binary is imageio-ffmpeg's when that is installed (it ships with the
``[lerobot]`` extra, pinned by ``uv.lock``), otherwise ``ffmpeg`` on ``PATH``; its version line is
recorded beside the output.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import math
import re
import shutil
import subprocess
from collections.abc import Callable, Generator, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import IO, Any

import numpy as np
import numpy.typing as npt
from PIL import Image, ImageDraw, ImageFont

# --------------------------------------------------------------------------------------------- #
# Output constants
# --------------------------------------------------------------------------------------------- #

#: Frames per second: LIBERO's control rate (robosuite ``control_freq=20``), one frame per step.
FPS = 20
#: x264 constant-rate factor for the submitted videos ("about 18" was asked for; 18 it is unless
#: the size guard has to raise it, which :func:`encode_frames` records).
CRF = 18
#: x264 preset. Slower presets spend encoder time, not quality, to make the same CRF smaller.
PRESET = "slow"
#: Ceiling the guard keeps every submitted file under, in bytes (50 MB, decimal, the stricter
#: reading of "under 50 MB").
MAX_BYTES = 50_000_000
#: CRF the size guard may climb to before giving up and saying so.
MAX_CRF = 28
#: Single-episode and side-by-side frame sizes.
SINGLE_SIZE = (1080, 1080)
PAIR_SIZE = (1920, 1080)
#: Seconds on the title card, on the end card, and holding the episode's last frame between them.
TITLE_SECONDS = 3
END_SECONDS = 4
HOLD_SECONDS = 1

# --------------------------------------------------------------------------------------------- #
# Words and text
# --------------------------------------------------------------------------------------------- #

#: Never drawn, in any case: the video shows fragility under an out-of-distribution instruction,
#: and these words describe something else (a deliberate redirection, or a predicate that was
#: fitted). Matched case-insensitively as substrings, so "attacker" and "uncalibrated" are caught.
BANNED_WORDS: tuple[str, ...] = ("attack", "steering", "attacker control", "calibrated")

#: The end card, one line per paragraph, in order. One constant, so it changes in one place.
END_CARD_LINES: tuple[str, ...] = (
    "Simulation only.",
    "The keep-out envelope is our default boundary. It was not fitted to this policy, and leaving "
    "it is not a measured hazard.",
    "This is fragility under an out-of-distribution instruction, not the model carrying out the "
    "request: the same frame with a one-word filler leaves the envelope 27 of 30 times "
    "(erratum E-2026-12).",
)
#: The end card's last line, filled from the episode's execution manifest at compose time.
PROVENANCE_LINE = "provael {version} · commit {commit} · {date}"

#: The marker drawn from the first scored envelope exit onward.
EXIT_MARKER = "left keep-out envelope at step {step}"
#: Beside the marker: the report's episode ends at the verdict, the frames do not.
PAST_VERDICT_NOTE = "steps after {step} are shown, not scored"
#: Drawn on the held last frame when the report records the task as completed.
TASK_DONE_MARKER = "task completed at step {step}"
#: Above the inset of the policy's own 256x256 frame.
INSET_LABEL = "what the policy sees"
#: Beside the drawn boundary, when the projection check passed and drawing was asked for.
BOUNDARY_LABEL = "default keep-out boundary"


class BannedWordError(ValueError):
    """A string about to be drawn carries a word that must never be on screen."""


def banned_words_in(text: str) -> list[str]:
    """The :data:`BANNED_WORDS` that occur in ``text``, case-insensitively."""
    folded = text.casefold()
    return [word for word in BANNED_WORDS if word in folded]


def guard_text(text: str) -> str:
    """Return ``text`` unchanged, or raise :class:`BannedWordError` naming the word."""
    found = banned_words_in(text)
    if found:
        raise BannedWordError(f"refusing to draw {text!r}: it contains {found}")
    return text


# --------------------------------------------------------------------------------------------- #
# Fonts
# --------------------------------------------------------------------------------------------- #

FONT_DIR = Path(__file__).resolve().parent / "fonts"
#: Bundled font files and their SHA-256, checked before first use.
FONTS: dict[str, tuple[str, str]] = {
    "regular": (
        "JetBrainsMono-Regular.ttf",
        "a0bf60ef0f83c5ed4d7a75d45838548b1f6873372dfac88f71804491898d138f",
    ),
    "bold": (
        "JetBrainsMono-Bold.ttf",
        "5590990c82e097397517f275f430af4546e1c45cff408bde4255dad142479dcb",
    ),
}
FONT_LICENCE = (
    "JetBrains Mono 2.304, Copyright 2020 The JetBrains Mono Project Authors, "
    "SIL Open Font License 1.1 (scripts/rfm/fonts/OFL.txt)"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@lru_cache(maxsize=4)
def font_path(weight: str) -> Path:
    """The bundled TTF for ``weight``, after checking its bytes are the pinned ones."""
    name, expected = FONTS[weight]
    path = FONT_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"bundled font {path} is missing")
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(f"{path} has sha256 {actual}, expected {expected}; text would not "
                         "render identically to the reviewed frames")
    return path


@lru_cache(maxsize=64)
def load_font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(
        str(font_path(weight)), size, layout_engine=ImageFont.Layout.BASIC
    )


# --------------------------------------------------------------------------------------------- #
# Colours
# --------------------------------------------------------------------------------------------- #

RGB = tuple[int, int, int]
BACKGROUND: RGB = (14, 17, 22)
BAR: RGB = (22, 27, 34)
TEXT: RGB = (245, 247, 250)
MUTED: RGB = (154, 164, 178)
AMBER: RGB = (255, 179, 0)
ON_AMBER: RGB = (17, 17, 17)
DONE: RGB = (46, 125, 50)
INSET_BORDER: RGB = (230, 237, 243)
DIVIDER: RGB = (60, 68, 80)


# --------------------------------------------------------------------------------------------- #
# Painting
# --------------------------------------------------------------------------------------------- #


class Painter:
    """Draws text through the banned-word guard and logs every string it draws."""

    def __init__(self) -> None:
        self.log: list[str] = []

    def text(
        self,
        draw: ImageDraw.ImageDraw,
        xy: tuple[float, float],
        text: str,
        *,
        size: int,
        weight: str = "regular",
        fill: RGB = TEXT,
        anchor: str = "la",
    ) -> None:
        guard_text(text)
        self.log.append(text)
        draw.text(xy, text, font=load_font(weight, size), fill=fill, anchor=anchor)

    @staticmethod
    def width(text: str, *, size: int, weight: str = "regular") -> float:
        return float(load_font(weight, size).getlength(text))

    def wrap(self, text: str, *, size: int, max_width: float, weight: str = "regular") -> list[str]:
        """Greedy word wrap of ``text`` into lines no wider than ``max_width`` pixels."""
        lines: list[str] = []
        current = ""
        for word in text.split():
            trial = word if not current else f"{current} {word}"
            if self.width(trial, size=size, weight=weight) <= max_width or not current:
                current = trial
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines


def _canvas(size: tuple[int, int]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", size, BACKGROUND)
    return image, ImageDraw.Draw(image)


def _fit(frame: npt.NDArray[np.uint8], side: int) -> Image.Image:
    """A square camera frame resized to ``side`` pixels (Lanczos: a downscale here, never up)."""
    image = Image.fromarray(np.ascontiguousarray(frame), "RGB")
    if image.size != (side, side):
        image = image.resize((side, side), Image.Resampling.LANCZOS)
    return image


@dataclass(frozen=True)
class EpisodeText:
    """The fixed text of one episode's overlay, all of it read from recorded artifacts."""

    model_line: str
    task_line: str
    instruction: str
    horizon: int
    arm_label: str


@dataclass(frozen=True)
class Boundary:
    """A projected keep-out box: line segments in track pixels, drawn only when proven."""

    segments: tuple[tuple[tuple[float, float], tuple[float, float]], ...]
    track_size: int


@dataclass(frozen=True)
class Panel:
    """One episode frame to paint: the camera view, the policy's frame, and the step's status."""

    view: npt.NDArray[np.uint8]
    inset: npt.NDArray[np.uint8] | None
    step: int
    exit_step: int | None
    done_step: int | None


def _dashed(
    draw: ImageDraw.ImageDraw,
    a: tuple[float, float],
    b: tuple[float, float],
    *,
    fill: RGB,
    width: int,
    dash: float = 14.0,
    gap: float = 9.0,
) -> None:
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    if length <= 0.0:
        return
    ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    pos = 0.0
    while pos < length:
        end = min(pos + dash, length)
        draw.line(
            [(a[0] + ux * pos, a[1] + uy * pos), (a[0] + ux * end, a[1] + uy * end)],
            fill=fill, width=width,
        )
        pos = end + gap


def _paint_status(
    painter: Painter,
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    panel: Panel,
    *,
    size: int,
) -> None:
    """The status row: the amber exit marker from the verdict on, or the task-completed badge."""
    x0, y0, x1, y1 = box
    if panel.exit_step is not None:
        draw.rectangle(box, fill=AMBER)
        marker = EXIT_MARKER.format(step=panel.exit_step)
        note = PAST_VERDICT_NOTE.format(step=panel.exit_step)
        note_size = max(14, int(size * 0.68))
        pad = 14
        mid = (y0 + y1) / 2
        fits = (
            painter.width(marker, size=size, weight="bold")
            + painter.width(note, size=note_size) + 3 * pad <= (x1 - x0)
        )
        if fits:
            painter.text(draw, (x0 + pad, mid), marker, size=size, weight="bold", fill=ON_AMBER,
                         anchor="lm")
            painter.text(draw, (x1 - pad, mid), note, size=note_size, fill=ON_AMBER, anchor="rm")
        else:
            painter.text(draw, (x0 + pad, y0 + (y1 - y0) * 0.33), marker, size=size,
                         weight="bold", fill=ON_AMBER, anchor="lm")
            painter.text(draw, (x0 + pad, y0 + (y1 - y0) * 0.76), note, size=note_size,
                         fill=ON_AMBER, anchor="lm")
    elif panel.done_step is not None:
        label = TASK_DONE_MARKER.format(step=panel.done_step)
        right = x0 + 28 + painter.width(label, size=size, weight="bold")
        draw.rectangle((x0, y0, int(min(x1, right)), y1), fill=DONE)
        painter.text(draw, (x0 + 14, (y0 + y1) / 2), label, size=size, weight="bold", fill=TEXT,
                     anchor="lm")


def _paint_scene(
    painter: Painter,
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    origin: tuple[int, int],
    side: int,
    panel: Panel,
    boundary: Boundary | None,
    *,
    label_size: int,
) -> None:
    """The camera view at ``origin``, the proven boundary on it, and the inset in its corner."""
    ox, oy = origin
    image.paste(_fit(panel.view, side), (ox, oy))
    if boundary is not None:
        scale = side / boundary.track_size
        topmost: tuple[float, float] | None = None
        for (ua, va), (ub, vb) in boundary.segments:
            a = (ox + ua * scale, oy + va * scale)
            b = (ox + ub * scale, oy + vb * scale)
            _dashed(draw, a, b, fill=AMBER, width=3)
            for point in (a, b):
                if topmost is None or point[1] < topmost[1]:
                    topmost = point
        if topmost is not None:
            half = painter.width(BOUNDARY_LABEL, size=label_size) / 2 + 8
            lx = min(max(topmost[0], ox + half), ox + side - half)
            ly = max(topmost[1] - 10, oy + label_size + 4)
            painter.text(draw, (lx, ly), BOUNDARY_LABEL, size=label_size, fill=AMBER,
                         anchor="mb")
    if panel.inset is not None:
        # Top-right, at the policy's own resolution (1:1, never rescaled): on LIBERO-Object task 0
        # that corner is empty floor, while the basket the benign arm reaches for sits lower right.
        inset = Image.fromarray(np.ascontiguousarray(panel.inset), "RGB")
        margin = 14
        label_h = label_size + 12
        ix = ox + side - inset.width - margin
        iy = oy + margin + label_h
        lw = painter.width(INSET_LABEL, size=label_size) + 16
        draw.rectangle((ix - 3, iy - 3 - label_h, ix - 3 + lw, iy - 3), fill=BAR)
        painter.text(draw, (ix + 5, iy - 3 - label_h / 2), INSET_LABEL, size=label_size,
                     fill=TEXT, anchor="lm")
        draw.rectangle((ix - 3, iy - 3, ix + inset.width + 2, iy + inset.height + 2),
                       fill=INSET_BORDER)
        image.paste(inset, (ix, iy))


def render_single_frame(
    panel: Panel,
    text: EpisodeText,
    painter: Painter,
    *,
    boundary: Boundary | None = None,
    size: tuple[int, int] = SINGLE_SIZE,
) -> npt.NDArray[np.uint8]:
    """One 1080x1080 episode frame: top bar, status row, the camera view and the inset."""
    width, height = size
    image, draw = _canvas(size)
    margin = 40
    draw.rectangle((0, 0, width, 200), fill=BAR)
    painter.text(draw, (margin, 16), text.model_line, size=24, fill=MUTED)
    painter.text(draw, (width - margin, 14), f"step {panel.step} / {text.horizon}", size=28,
                 weight="bold", anchor="ra")
    painter.text(draw, (margin, 48), text.task_line, size=22, fill=MUTED)
    lines = painter.wrap(f"“{text.instruction}”", size=28, max_width=width - 2 * margin)
    if len(lines) > 3:
        lines = painter.wrap(f"“{text.instruction}”", size=22, max_width=width - 2 * margin)
    line_h = 36 if len(lines) <= 3 else 28
    for i, line in enumerate(lines):
        painter.text(draw, (margin, 84 + i * line_h), line, size=28 if line_h == 36 else 22)
    _paint_status(painter, draw, (margin, 206, width - margin, 252), panel, size=26)
    side = height - 260
    _paint_scene(painter, image, draw, ((width - side) // 2, 260), side, panel, boundary,
                 label_size=20)
    return np.asarray(image, dtype=np.uint8)


def render_pair_frame(
    left: Panel,
    right: Panel,
    texts: tuple[EpisodeText, EpisodeText],
    header: str,
    painter: Painter,
    *,
    boundaries: tuple[Boundary | None, Boundary | None] = (None, None),
    size: tuple[int, int] = PAIR_SIZE,
) -> npt.NDArray[np.uint8]:
    """One 1920x1080 frame with two episodes side by side, each with its own text and counter."""
    width, height = size
    image, draw = _canvas(size)
    draw.rectangle((0, 0, width, 60), fill=BAR)
    painter.text(draw, (width / 2, 30), header, size=24, fill=MUTED, anchor="mm")
    gap = 16
    panel_w = (width - 3 * gap) // 2
    for index, (panel, text, boundary) in enumerate(
        zip((left, right), texts, boundaries, strict=True)
    ):
        x0 = gap + index * (panel_w + gap)
        draw.rectangle((x0, 66, x0 + panel_w, 262), fill=BAR)
        painter.text(draw, (x0 + 18, 78), text.arm_label, size=22, fill=MUTED)
        painter.text(draw, (x0 + panel_w - 18, 74), f"step {panel.step} / {text.horizon}",
                     size=26, weight="bold", anchor="ra")
        lines = painter.wrap(f"“{text.instruction}”", size=26, max_width=panel_w - 36)
        for i, line in enumerate(lines[:3]):
            painter.text(draw, (x0 + 18, 110 + i * 34), line, size=26)
        _paint_status(painter, draw, (x0 + 18, 214, x0 + panel_w - 18, 256), panel, size=24)
        side = height - 272
        _paint_scene(painter, image, draw, (x0 + (panel_w - side) // 2, 272), side, panel,
                     boundary, label_size=18)
    draw.line([(width / 2, 66), (width / 2, height)], fill=DIVIDER, width=2)
    return np.asarray(image, dtype=np.uint8)


def _block_height(
    painter: Painter,
    lines: Sequence[tuple[str, int, str, RGB]],
    *,
    max_width: float,
    spacing: float = 1.35,
) -> float:
    """The height :func:`_centered_block` will use for ``lines``, so a card can centre it."""
    total = 0.0
    for text, size, weight, _colour in lines:
        count = len(painter.wrap(text, size=size, max_width=max_width, weight=weight))
        total += count * size * spacing + size * 0.45
    return total


def _centered_block(
    painter: Painter,
    draw: ImageDraw.ImageDraw,
    lines: Sequence[tuple[str, int, str, RGB]],
    *,
    width: int,
    top: float,
    max_width: float,
    spacing: float = 1.35,
) -> float:
    """Draw ``(text, size, weight, colour)`` paragraphs wrapped and centred; return the next y."""
    y = top
    for text, size, weight, colour in lines:
        for line in painter.wrap(text, size=size, max_width=max_width, weight=weight):
            painter.text(draw, (width / 2, y), line, size=size, weight=weight, fill=colour,
                         anchor="ma")
            y += size * spacing
        y += size * 0.45
    return y


def render_title_card(
    texts: Sequence[EpisodeText],
    title: str,
    subtitle_lines: Sequence[str],
    painter: Painter,
    *,
    size: tuple[int, int],
) -> npt.NDArray[np.uint8]:
    """The opening card: what is shown, from which checkpoint, and each instruction verbatim."""
    width, height = size
    image, draw = _canvas(size)
    block: list[tuple[str, int, str, RGB]] = [(title, 42, "bold", TEXT)]
    block += [(line, 24, "regular", MUTED) for line in subtitle_lines]
    columns = len(texts)
    col_w = (width * 0.9) / columns
    wrapped = [painter.wrap(f"“{t.instruction}”", size=30, max_width=col_w * 0.9) for t in texts]
    tallest = max((len(w) for w in wrapped), default=0)
    total = _block_height(painter, block, max_width=width * 0.86) + 78 + tallest * 42
    y = _centered_block(painter, draw, block, width=width, top=max(40.0, (height - total) / 2),
                        max_width=width * 0.86)
    for i, text in enumerate(texts):
        cx = width * 0.05 + col_w * (i + 0.5)
        cy = y + 34
        painter.text(draw, (cx, cy), f"{text.arm_label}:", size=24, fill=MUTED, anchor="ma")
        cy += 44
        for line in wrapped[i]:
            painter.text(draw, (cx, cy), line, size=30, anchor="ma")
            cy += 42
    painter.text(draw, (width / 2, height - 60),
                 f"played at the simulator's control rate, {FPS} steps per second", size=22,
                 fill=MUTED, anchor="ma")
    return np.asarray(image, dtype=np.uint8)


def render_end_card(
    painter: Painter,
    provenance: str,
    *,
    size: tuple[int, int],
    lines: Sequence[str] = END_CARD_LINES,
) -> npt.NDArray[np.uint8]:
    """The closing card: :data:`END_CARD_LINES` and the recording's provenance line."""
    width, height = size
    image, draw = _canvas(size)
    block: list[tuple[str, int, str, RGB]] = []
    for i, line in enumerate(lines):
        block.append((line, 40 if i == 0 else 30, "bold" if i == 0 else "regular", TEXT))
    max_width = min(width * 0.86, 1180.0)
    total = _block_height(painter, block, max_width=max_width, spacing=1.38)
    _centered_block(painter, draw, block, width=width, top=max(40.0, (height - total) / 2 - 20),
                    max_width=max_width, spacing=1.38)
    painter.text(draw, (width / 2, height - 64), provenance, size=22, fill=MUTED, anchor="ma")
    return np.asarray(image, dtype=np.uint8)


# --------------------------------------------------------------------------------------------- #
# ffmpeg
# --------------------------------------------------------------------------------------------- #


def find_ffmpeg() -> str:
    """imageio-ffmpeg's bundled binary when installed (the ``[lerobot]`` extra), else ``ffmpeg``."""
    try:
        # Imported by name: imageio-ffmpeg is in the [lerobot] extra and absent from the CPU build.
        bundled = importlib.import_module("imageio_ffmpeg")
        exe = str(bundled.get_ffmpeg_exe())
        if exe:
            return exe
    except Exception:  # noqa: BLE001, S110 - not installed or no binary: fall back to PATH
        pass
    found = shutil.which("ffmpeg")
    if found is None:
        raise FileNotFoundError(
            "no ffmpeg: install the [lerobot] extra (imageio-ffmpeg bundles one) or put ffmpeg "
            "with libx264 on PATH"
        )
    return found


def ffmpeg_version(ffmpeg: str) -> str:
    out = subprocess.run([ffmpeg, "-hide_banner", "-version"], capture_output=True, text=True,
                         check=False, timeout=30)
    return (out.stdout.splitlines() or ["unknown"])[0].strip()


@dataclass
class FfmpegWriter:
    """RGB frames into an H.264 MP4 through an ffmpeg pipe, at a constant frame rate."""

    path: Path
    width: int
    height: int
    fps: int = FPS
    crf: int = CRF
    preset: str = PRESET
    pix_fmt: str = "yuv420p"
    ffmpeg: str | None = None
    frames: int = 0
    _proc: subprocess.Popen[bytes] | None = field(default=None, repr=False)

    def command(self) -> list[str]:
        exe = self.ffmpeg or find_ffmpeg()
        return [
            exe, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{self.width}x{self.height}",
            "-r", str(self.fps), "-i", "-",
            "-an", "-c:v", "libx264", "-preset", self.preset, "-crf", str(self.crf),
            "-pix_fmt", self.pix_fmt, "-r", str(self.fps),
            "-movflags", "+faststart", "-map_metadata", "-1",
            "-fflags", "+bitexact", "-flags:v", "+bitexact",
            str(self.path),
        ]

    def __enter__(self) -> FfmpegWriter:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._proc = subprocess.Popen(self.command(), stdin=subprocess.PIPE,
                                      stderr=subprocess.PIPE)
        return self

    def write(self, frame: npt.NDArray[np.uint8]) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise RuntimeError("FfmpegWriter used outside its context")
        array = np.ascontiguousarray(frame, dtype=np.uint8)
        if array.shape != (self.height, self.width, 3):
            raise ValueError(f"frame is {array.shape}, writer expects "
                             f"({self.height}, {self.width}, 3)")
        self._proc.stdin.write(array.tobytes())
        self.frames += 1

    def __exit__(self, *exc: object) -> None:
        proc = self._proc
        if proc is None:
            return
        stdin: IO[bytes] | None = proc.stdin
        if stdin is not None:
            stdin.close()
        stderr = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
        code = proc.wait()
        self._proc = None
        if code != 0 and exc[0] is None:
            raise RuntimeError(f"ffmpeg exited {code} writing {self.path}: {stderr.strip()}")


def read_frames(
    path: Path, width: int, height: int, *, ffmpeg: str | None = None
) -> Generator[npt.NDArray[np.uint8], None, None]:
    """Decode an MP4 to RGB frames of a known size, in order."""
    exe = ffmpeg or find_ffmpeg()
    proc = subprocess.Popen(
        [exe, "-hide_banner", "-loglevel", "error", "-i", str(path),
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    frame_bytes = width * height * 3
    stdout = proc.stdout
    if stdout is None:
        raise RuntimeError("ffmpeg was started without a stdout pipe")
    try:
        while True:
            chunk = stdout.read(frame_bytes)
            if not chunk:
                break
            if len(chunk) != frame_bytes:
                raise ValueError(f"{path}: truncated frame ({len(chunk)} of {frame_bytes} bytes)")
            yield np.frombuffer(chunk, dtype=np.uint8).reshape(height, width, 3).copy()
    finally:
        stdout.close()
        stderr = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
        code = proc.wait()
        if code not in (0, -13, 141) and stderr:
            raise RuntimeError(f"ffmpeg exited {code} reading {path}: {stderr.strip()}")


_DURATION = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_STREAM = re.compile(
    r"Video:\s*(?P<codec>\w+)(?:\s*\((?P<profile>[^)]*)\))?.*?,\s*(?P<pix>[a-z0-9]+)"
    r"(?:\([^)]*\))?,\s*(?P<w>\d+)x(?P<h>\d+).*?,\s*(?P<fps>[\d.]+)\s*fps"
)


def probe(path: Path, *, ffmpeg: str | None = None) -> dict[str, Any]:
    """Codec, profile, pixel format, size, frame rate, duration and bytes of an MP4.

    ``ffprobe`` when it is on PATH; otherwise the stream line ``ffmpeg -i`` prints, since
    imageio-ffmpeg ships ffmpeg without ffprobe.
    """
    info: dict[str, Any] = {"bytes": path.stat().st_size}
    ffprobe = shutil.which("ffprobe")
    if ffprobe is not None:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0", "-count_frames",
             "-show_entries",
             "stream=codec_name,profile,pix_fmt,width,height,r_frame_rate,nb_read_frames",
             "-show_entries", "format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, check=True, timeout=300,
        )
        data = json.loads(out.stdout)
        stream = data["streams"][0]
        num, den = (int(v) for v in str(stream["r_frame_rate"]).split("/"))
        info.update(
            codec=stream["codec_name"], profile=stream.get("profile"), pix_fmt=stream["pix_fmt"],
            width=int(stream["width"]), height=int(stream["height"]), fps=num / den,
            frames=int(stream.get("nb_read_frames", 0)),
            duration_s=float(data["format"]["duration"]), probed_with="ffprobe",
        )
        return info
    exe = ffmpeg or find_ffmpeg()
    err = subprocess.run([exe, "-hide_banner", "-i", str(path)], capture_output=True,
                         text=True, check=False, timeout=60).stderr
    duration = _DURATION.search(err)
    stream_match = _STREAM.search(err)
    if duration is None or stream_match is None:
        raise ValueError(f"could not read the stream description of {path}:\n{err}")
    hours, minutes, seconds = duration.groups()
    info.update(
        codec=stream_match["codec"], profile=stream_match["profile"],
        pix_fmt=stream_match["pix"], width=int(stream_match["w"]),
        height=int(stream_match["h"]), fps=float(stream_match["fps"]),
        duration_s=int(hours) * 3600 + int(minutes) * 60 + float(seconds),
        probed_with="ffmpeg -i",
    )
    return info


@dataclass(frozen=True)
class Encoded:
    """What :func:`encode_frames` wrote, and at which CRF."""

    path: Path
    frames: int
    crf: int
    bytes: int
    sha256: str
    attempts: tuple[tuple[int, int], ...]


def encode_frames(
    make_frames: Callable[[], Iterable[npt.NDArray[np.uint8]]],
    path: Path,
    size: tuple[int, int],
    *,
    crf: int = CRF,
    max_bytes: int = MAX_BYTES,
    max_crf: int = MAX_CRF,
    ffmpeg: str | None = None,
    preset: str = PRESET,
) -> Encoded:
    """Encode ``make_frames()`` (a fresh iterable each call) and keep the file under ``max_bytes``.

    The frames are regenerated rather than held, so a 1920x1080 video never sits in memory. If the
    first encode is too large the CRF is raised two at a time; every attempt is returned, and a file
    still too large at ``max_crf`` raises rather than ship over the limit.
    """
    attempts: list[tuple[int, int]] = []
    current = crf
    while True:
        writer = FfmpegWriter(path, size[0], size[1], crf=current, ffmpeg=ffmpeg, preset=preset)
        with writer:
            for frame in make_frames():
                writer.write(frame)
        written = path.stat().st_size
        attempts.append((current, written))
        if written <= max_bytes:
            return Encoded(path, writer.frames, current, written, sha256_file(path),
                           tuple(attempts))
        if current >= max_crf:
            raise RuntimeError(f"{path} is {written} bytes at CRF {current}, over {max_bytes}; "
                               f"attempts {attempts}")
        current = min(max_crf, current + 2)


def repeat(
    frame: npt.NDArray[np.uint8], seconds: float, fps: int = FPS
) -> Iterator[npt.NDArray[np.uint8]]:
    """``frame`` held for ``seconds`` at ``fps`` (a hold, not an interpolation)."""
    return (frame for _ in range(int(round(seconds * fps))))


__all__ = [
    "BANNED_WORDS",
    "BOUNDARY_LABEL",
    "CRF",
    "END_CARD_LINES",
    "END_SECONDS",
    "EXIT_MARKER",
    "FONTS",
    "FONT_LICENCE",
    "FPS",
    "HOLD_SECONDS",
    "INSET_LABEL",
    "MAX_BYTES",
    "PAIR_SIZE",
    "PAST_VERDICT_NOTE",
    "PROVENANCE_LINE",
    "SINGLE_SIZE",
    "TASK_DONE_MARKER",
    "TITLE_SECONDS",
    "BannedWordError",
    "Boundary",
    "Encoded",
    "EpisodeText",
    "FfmpegWriter",
    "Painter",
    "Panel",
    "banned_words_in",
    "encode_frames",
    "find_ffmpeg",
    "ffmpeg_version",
    "guard_text",
    "probe",
    "read_frames",
    "render_end_card",
    "render_pair_frame",
    "render_single_frame",
    "render_title_card",
    "repeat",
    "sha256_file",
]
