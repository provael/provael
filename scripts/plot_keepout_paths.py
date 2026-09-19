#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Draw each episode's end-effector path against the task's keep-out zone, as SVG.

WHY. The keep-out predicate is the one thing in a LIBERO result a reader cannot see: a report says
"unsafe at step 143" and the clip shows the arm moving, but nothing shows WHERE the boundary was
and how the benign and the attacked paths relate to it. Issue #136 is, at bottom, that question —
whether the default box sits inside the benign workspace — and a picture of forty benign paths
against the box answers it faster than any rate. Since 0.40 every episode record carries the
end-effector trajectory (``AttackResult.trajectory``, float32 × 3 per step), so this needs no
simulator: it reads the committed ``report.json`` shards and writes one SVG per task.

WHAT IT DRAWS. A top-down (x, y) panel and a side (x, z) panel per task. The keep-out zone(s) for
the task — the committed calibration if one exists, else the documented default — as a shaded
rectangle; every benign-arm path in blue; every path of the chosen attack arm in red, with a
marker at the first step the predicate fired; every other arm faint grey when ``--all-arms`` is
given. Nothing is drawn that the report does not carry: no camera projection, no smoothing, no
inferred contact.

No third-party plotting library: the SVG is written directly, so the output is deterministic and
the CPU core gains no dependency. Open the files in any browser.

Usage::

    python scripts/plot_keepout_paths.py results/<run> --out results/<run>/figures
    python scripts/plot_keepout_paths.py results/<run> --attack goal_substitution --all-arms
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from provael.suites.keepout_zones import KeepOutZone, zones_for  # noqa: E402
from provael.types import AttackResult  # noqa: E402

W, H, PAD = 420, 320, 36
BLUE, RED, GREY, ZONE = "#2f6fd6", "#d0342c", "#b0b0b0", "#f2b8b4"


def _load_results(run_dir: Path) -> list[AttackResult]:
    paths = [run_dir / "report.json"] if (run_dir / "report.json").exists() else sorted(
        run_dir.glob("*/report.json")
    )
    results: list[AttackResult] = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        results.extend(AttackResult(**r) for r in data.get("results", []))
    if not results:
        raise SystemExit(f"no report.json under {run_dir}")
    return results


Extent = tuple[float, float, float, float]
Path3 = list[list[float]]


def _extent(paths: list[Path3], zones: list[KeepOutZone], a: int, b: int) -> Extent:
    xs = [p[a] for path in paths for p in path]
    ys = [p[b] for path in paths for p in path]
    for z in zones:
        rx, ry = (z.x, z.y, z.z)[a], (z.x, z.y, z.z)[b]
        xs += list(rx)
        ys += list(ry)
    lo_x, hi_x, lo_y, hi_y = min(xs), max(xs), min(ys), max(ys)
    mx, my = max(0.02, 0.06 * (hi_x - lo_x)), max(0.02, 0.06 * (hi_y - lo_y))
    return lo_x - mx, hi_x + mx, lo_y - my, hi_y + my


def _panel(
    title: str,
    axes: tuple[int, int],
    labels: tuple[str, str],
    zones: list[KeepOutZone],
    benign: list[list[list[float]]],
    attacked: list[tuple[list[list[float]], int | None]],
    others: list[list[list[float]]],
    offset_x: int,
) -> str:
    a, b = axes
    everything = benign + [p for p, _ in attacked] + others
    lo_x, hi_x, lo_y, hi_y = _extent(everything, zones, a, b)

    def sx(v: float) -> float:
        return offset_x + PAD + (v - lo_x) / (hi_x - lo_x) * (W - 2 * PAD)

    def sy(v: float) -> float:
        return PAD + (hi_y - v) / (hi_y - lo_y) * (H - 2 * PAD)

    out = [
        f'<rect x="{offset_x}" y="0" width="{W}" height="{H}" fill="#ffffff"/>',
        f'<text x="{offset_x + PAD}" y="{PAD - 14}" font-size="13" font-family="sans-serif" '
        f'fill="#222">{title}</text>',
    ]
    for z in zones:
        rx, ry = (z.x, z.y, z.z)[a], (z.x, z.y, z.z)[b]
        out.append(
            f'<rect x="{sx(rx[0]):.1f}" y="{sy(ry[1]):.1f}" width="{sx(rx[1]) - sx(rx[0]):.1f}" '
            f'height="{sy(ry[0]) - sy(ry[1]):.1f}" fill="{ZONE}" stroke="{RED}" '
            f'stroke-dasharray="4 3" opacity="0.8"><title>keep-out {z.name}</title></rect>'
        )

    def polyline(path: list[list[float]], colour: str, width: float, opacity: float) -> str:
        pts = " ".join(f"{sx(p[a]):.1f},{sy(p[b]):.1f}" for p in path)
        return (
            f'<polyline points="{pts}" fill="none" stroke="{colour}" stroke-width="{width}" '
            f'opacity="{opacity}"/>'
        )

    out += [polyline(p, GREY, 1.0, 0.5) for p in others]
    out += [polyline(p, BLUE, 1.2, 0.75) for p in benign]
    for path, first_unsafe in attacked:
        out.append(polyline(path, RED, 1.4, 0.8))
        if first_unsafe is not None and 1 <= first_unsafe <= len(path):
            p = path[first_unsafe - 1]
            out.append(
                f'<circle cx="{sx(p[a]):.1f}" cy="{sy(p[b]):.1f}" r="4" fill="{RED}" '
                f'stroke="#fff" stroke-width="1"><title>first unsafe step {first_unsafe}'
                "</title></circle>"
            )
    out.append(
        f'<rect x="{offset_x + PAD}" y="{PAD}" width="{W - 2 * PAD}" height="{H - 2 * PAD}" '
        'fill="none" stroke="#444"/>'
    )
    out.append(
        f'<text x="{offset_x + W / 2:.0f}" y="{H - 8}" font-size="11" font-family="sans-serif" '
        f'text-anchor="middle" fill="#444">{labels[0]} [{lo_x:.2f}, {hi_x:.2f}] m</text>'
    )
    out.append(
        f'<text x="{offset_x + 12}" y="{H / 2:.0f}" font-size="11" font-family="sans-serif" '
        f'text-anchor="middle" fill="#444" transform="rotate(-90 {offset_x + 12} {H / 2:.0f})">'
        f'{labels[1]} [{lo_y:.2f}, {hi_y:.2f}] m</text>'
    )
    return "\n".join(out)


def render_task(
    task: str, rows: list[AttackResult], attack: str, all_arms: bool, zones: list[KeepOutZone]
) -> str | None:
    benign: list[list[list[float]]] = []
    attacked: list[tuple[list[list[float]], int | None]] = []
    others: list[list[list[float]]] = []
    for r in rows:
        if r.trajectory is None or r.trajectory.shape[1] != 3:
            continue
        path = r.trajectory.decode()
        if r.attack == "none":
            benign.append(path)
        elif r.attack == attack:
            attacked.append((path, r.steps_to_success))
        elif all_arms:
            others.append(path)
    if not benign and not attacked:
        return None
    n_hit = sum(1 for _, s in attacked if s is not None)
    legend = (
        f"{task} — benign `none` ×{len(benign)} (blue) · `{attack}` ×{len(attacked)} (red, "
        f"{n_hit} reached the zone; dot = first unsafe step)"
        + (f" · other arms ×{len(others)} (grey)" if others else "")
    )
    body = "\n".join([
        _panel("top-down: x against y", (0, 1), ("x", "y"), zones, benign, attacked, others, 0),
        _panel("side: x against z", (0, 2), ("x", "z"), zones, benign, attacked, others, W + 10),
    ])
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{2 * W + 10}" height="{H + 26}" '
        f'viewBox="0 0 {2 * W + 10} {H + 26}" font-family="sans-serif">\n'
        f'<rect width="100%" height="100%" fill="#ffffff"/>\n{body}\n'
        f'<text x="6" y="{H + 18}" font-size="11" fill="#333">{_escape(legend)}</text>\n</svg>\n'
    )


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--out", type=Path, default=None, help="default: <run_dir>/figures")
    parser.add_argument("--attack", default="roleplay", help="the arm drawn in red")
    parser.add_argument("--all-arms", action="store_true", help="draw every other arm in grey")
    args = parser.parse_args()
    out_dir = args.out or (args.run_dir / "figures")
    results = _load_results(args.run_dir)
    by_task: dict[str, list[AttackResult]] = defaultdict(list)
    for r in results:
        by_task[r.task].append(r)
    written = 0
    for task in sorted(by_task):
        zones = zones_for(task, strict=False) if "/" in task else []
        svg = render_task(task, by_task[task], args.attack, args.all_arms, zones)
        if svg is None:
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"{task.replace('/', '-')}__{args.attack}.svg"
        target.write_text(svg, encoding="utf-8")
        written += 1
        print(f"wrote {target}")
    if written == 0:
        print(
            f"no episode under {args.run_dir} carries a 3-D trajectory (reports written before "
            "0.40 do not); nothing drawn",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
