#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Regenerate the brand assets under ``docs/assets/`` from the website's mark.

WHY. The website is upstream for the brand, the one flow that runs that way (this repository is
upstream for every number and claim the website shows): its Proof-Path mark
(the letter P drawn as a policy trajectory that resolves into a teal verdict node, never a
checkmark) is defined once in ``provael-website/scripts/gen-assets.mjs`` and rendered into the
favicon and every social card there. This repository carried a *different* logo until 21 September
2026 — a teal checkmark on a blue gradient, drawn before the mark existed — on the README wordmark,
the org profile picture and the docs, so the same project wore two faces. This script makes the
repository's copies derive from the website's definition instead of being drawn again.

WHAT IT WRITES (all under ``docs/assets/``):

* ``provael_icon.svg`` — the tile: navy rounded square, cream P, teal node. Byte-for-byte the
  favicon SVG the website generates; ``MARK`` below is copied from ``gen-assets.mjs`` and the
  website wins if they ever differ.
* ``provael_wordmark.svg`` / ``provael_wordmark_dark.svg`` — the tile beside the word "Provael"
  and the line "Prove it. Prevail.", for light and dark backgrounds. The text is converted to
  glyph outlines from the website's own font files (Space Grotesk 600, Instrument Serif italic),
  so the SVG renders identically wherever it is opened; nothing depends on the viewer's fonts.
* ``provael_icon_512.png``, ``provael_avatar_300.png``, ``provael_wordmark.png``,
  ``provael_wordmark_dark.png`` — rasters of the above, for surfaces that cannot take an SVG
  (GitHub organisation picture, Hugging Face, the README on PyPI).

HOW. The fonts are read from a sibling website checkout (``../provael-website/public/fonts``);
outlines come from fontTools (``pip install fonttools brotli`` outside the project venv — this is
a maintainer script, not a dependency). Rasters are produced by the sibling's ``sharp`` through a
one-line ``node -e`` so no image library joins this repository. Deterministic: same inputs, same
bytes; the SVGs carry no timestamps.

Run from the repository root::

    python3 scripts/gen_brand_assets.py

Then re-upload ``provael_avatar_300.png`` wherever an avatar lives (GitHub organisation, the
``provael-bot`` App, Hugging Face); those are uploads, not files.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

try:
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.ttLib import TTFont
except ImportError:  # pragma: no cover - maintainer tooling
    sys.exit("needs fontTools + brotli: pip install fonttools brotli")

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets"
WEBSITE = ROOT.parent / "provael-website"
FONTS = WEBSITE / "public" / "fonts"

# Copied from provael-website/scripts/gen-assets.mjs (`favSvg`). The website wins on disagreement.
NAVY = "#081726"
CREAM = "#F3EDE1"
TEAL = "#19D3E0"
INK = "#181410"  # --ink on paper
TEAL_DEEP = "#096A73"  # --teal-deep on paper
MARK = (
    f'<rect width="64" height="64" rx="14" fill="{NAVY}"/>'
    f'<path d="M23 50V17C42 12 49 20 49 28.5C49 39 36.5 40 25 39" fill="none" stroke="{CREAM}" '
    'stroke-width="7.4" stroke-linecap="round" stroke-linejoin="round"/>'
    f'<circle cx="25" cy="39" r="5.4" fill="{TEAL}"/>'
)

ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" '
    'aria-label="Provael">\n  ' + MARK + "\n</svg>\n"
)


def text_paths(
    font_path: Path, text: str, size: float, x: float, y: float, tracking_em: float = 0.0
) -> tuple[str, float]:
    """Return ``<path>`` elements for ``text`` in ``font_path`` at ``size`` px, baseline ``y``.

    Glyphs are placed by advance width plus ``tracking_em`` (in em); kerning is not applied, which
    is what the website's CSS does too (``letter-spacing`` only). Returns the markup and the pen
    position after the last glyph, so a second run can continue on the same line.
    """
    font = TTFont(font_path)
    upem = font["head"].unitsPerEm
    scale = size / upem
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    glyph_set = font.getGlyphSet()
    parts: list[str] = []
    pen_x = x
    for ch in text:
        name = cmap.get(ord(ch))
        if name is None:
            raise SystemExit(f"{font_path.name} has no glyph for {ch!r}")
        pen = SVGPathPen(glyph_set)
        glyph_set[name].draw(pen)
        d = pen.getCommands()
        if d:
            tf = f"translate({pen_x:.2f} {y:.2f}) scale({scale:.6f} {-scale:.6f})"
            parts.append(f'<path transform="{tf}" d="{d}"/>')
        pen_x += hmtx[name][0] * scale + tracking_em * size
    return "\n    ".join(parts), pen_x


def wordmark_svg(text_fill: str, tagline_fill: str) -> str:
    """The lockup at 1320×360: tile at the left, word and tagline to its right."""
    grotesk = FONTS / "space-grotesk-latin-600-normal.woff2"
    serif = FONTS / "instrument-serif-latin-400-italic.woff2"
    word, _ = text_paths(grotesk, "Provael", 168, 320, 205, tracking_em=-0.01)
    tagline, _ = text_paths(serif, "Prove it. Prevail.", 60, 326, 272)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1320 360" role="img" '
        'aria-label="Provael. Prove it. Prevail.">\n'
        '  <g transform="translate(40 60) scale(3.75)">' + MARK + "</g>\n"
        f'  <g fill="{text_fill}">\n    {word}\n  </g>\n'
        f'  <g fill="{tagline_fill}">\n    {tagline}\n  </g>\n'
        "</svg>\n"
    )


def rasterize(svg: Path, png: Path, width: int, height: int | None = None) -> None:
    """Render with the sibling website's sharp; no image dependency joins this repo."""
    node = (
        "const sharp=require('sharp');const [svg,png,w,h]=process.argv.slice(1);"
        "sharp(svg,{density:600}).resize(+w,h?+h:null).png().toFile(png)"
        ".then(()=>console.log('wrote',png))"
    )
    subprocess.run(  # noqa: S603 - fixed argv, no shell; the inputs are this repo's own files
        ["node", "-e", node, str(svg), str(png), str(width), str(height or "")],
        check=True,
        cwd=WEBSITE,
    )


def main() -> None:
    if not FONTS.is_dir():
        sys.exit(f"sibling website checkout not found at {WEBSITE} (fonts live there)")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "provael_icon.svg").write_text(ICON_SVG, encoding="utf-8")
    (OUT / "provael_wordmark.svg").write_text(wordmark_svg(INK, TEAL_DEEP), encoding="utf-8")
    (OUT / "provael_wordmark_dark.svg").write_text(wordmark_svg(CREAM, TEAL), encoding="utf-8")
    rasterize(OUT / "provael_icon.svg", OUT / "provael_icon_512.png", 512, 512)
    rasterize(OUT / "provael_icon.svg", OUT / "provael_avatar_300.png", 300, 300)
    rasterize(OUT / "provael_wordmark.svg", OUT / "provael_wordmark.png", 1320, 360)
    rasterize(OUT / "provael_wordmark_dark.svg", OUT / "provael_wordmark_dark.png", 1320, 360)
    for name in sorted(p.name for p in OUT.iterdir() if p.name.startswith("provael_")):
        print(f"  {name}")


if __name__ == "__main__":
    main()
