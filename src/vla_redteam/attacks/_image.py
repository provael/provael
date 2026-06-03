"""Deterministic image-space perturbations for the ``visual`` / ``injection`` families.

Pure numpy + PIL, no GPU and no lerobot — so they are unit-testable on CPU with
synthetic images. Each function takes and returns an ``(H, W, 3)`` uint8 array and
never mutates its input.

These operate on the actual camera image a real VLA policy consumes (when a suite
exposes one at :data:`vla_redteam.types.IMAGE_KEY`). The stub suite has no such image,
so these are not exercised on the deterministic stub path.
"""

from __future__ import annotations

import hashlib

import numpy as np
import numpy.typing as npt
from PIL import Image, ImageDraw

from vla_redteam.types import IMAGE_KEY, Observation

Uint8Image = npt.NDArray[np.uint8]


def image_of(observation: Observation) -> Uint8Image | None:
    """Return the suite's real camera image if present (LIBERO), else None (stub)."""
    image = observation.get(IMAGE_KEY)
    return np.asarray(image, dtype=np.uint8) if isinstance(image, np.ndarray) else None


def _stable_int(text: str, lo: int, hi: int) -> int:
    """A deterministic int in ``[lo, hi)`` from ``text`` (SHA-256 based)."""
    if hi <= lo:
        return lo
    digest = int.from_bytes(hashlib.sha256(text.encode()).digest()[:4], "big")
    return lo + digest % (hi - lo)


def overlay_patch(image: npt.ArrayLike, marker: str, frac: float = 0.25) -> Uint8Image:
    """Overlay a deterministic high-contrast adversarial patch encoding ``marker``.

    The patch is a red/white checkerboard block whose position is derived from a stable
    hash of ``marker`` (so it is reproducible but content-dependent). Returns a modified
    copy.
    """
    img: Uint8Image = np.array(image, dtype=np.uint8, copy=True)
    if img.ndim != 3 or img.shape[2] != 3:
        return img
    h, w = img.shape[0], img.shape[1]
    ph, pw = max(1, int(h * frac)), max(1, int(w * frac))
    y0 = _stable_int(marker + ":y", 0, max(1, h - ph + 1))
    x0 = _stable_int(marker + ":x", 0, max(1, w - pw + 1))
    checker = (np.indices((ph, pw)).sum(axis=0) % 2).astype(bool)
    red = np.array([255, 0, 0], dtype=np.uint8)
    white = np.array([255, 255, 255], dtype=np.uint8)
    block = np.where(checker[..., None], red, white)
    img[y0 : y0 + ph, x0 : x0 + pw] = block
    return img


def render_scene_text(image: npt.ArrayLike, text: str) -> Uint8Image:
    """Render ``text`` as a sign in the scene (a black banner with white text) via PIL.

    Deterministic (fixed font, position). Returns a modified copy.
    """
    img: Uint8Image = np.array(image, dtype=np.uint8, copy=True)
    if img.ndim != 3 or img.shape[2] != 3:
        return img
    pil = Image.fromarray(img)
    draw = ImageDraw.Draw(pil)
    band_h = max(12, pil.height // 6)
    draw.rectangle((0, 0, pil.width, band_h), fill=(0, 0, 0))
    draw.text((2, 2), text, fill=(255, 255, 255))
    return np.asarray(pil, dtype=np.uint8)


__all__ = ["overlay_patch", "render_scene_text", "image_of"]
