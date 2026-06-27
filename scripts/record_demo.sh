#!/usr/bin/env bash
# Regenerate the README demo asset (docs/assets/demo.svg) from a real stub run.
#
# Deterministic and machine-independent: it runs the CPU stub pipeline (seed 0) and
# renders the resulting ASR table + headline to a terminal-style SVG using Rich (no
# external tools required). If asciinema + agg happen to be installed, it additionally
# records a real terminal cast to docs/assets/demo.gif.
#
# Usage:  ./scripts/record_demo.sh
set -euo pipefail
cd "$(dirname "$0")/.."

OUT_DIR="runs/demo"
SVG="docs/assets/demo.svg"
mkdir -p docs/assets

echo ">> running the demo attack (stub, all 3 families, seed 0)…"
uv run provael attack --policy stub --suite stub \
  --attacks instruction,visual,injection --episodes 10 --seed 0 --out "$OUT_DIR" >/dev/null

echo ">> rendering $SVG (Rich, deterministic)…"
uv run python - "$OUT_DIR" "$SVG" <<'PY'
import sys
from pathlib import Path

from rich.console import Console

from provael.report import build_summary_table, load_report

out_dir, svg_path = sys.argv[1], sys.argv[2]
report = load_report(Path(out_dir))

console = Console(record=True, width=86)
console.print(build_summary_table(report))
console.print(f"[bold]{report.headline()}[/bold]")
# Fixed unique_id -> stable, reproducible SVG (no random element ids).
console.save_svg(
    svg_path,
    title="provael attack --attacks instruction,visual,injection",
    unique_id="provael-demo",
)
print(f"wrote {svg_path}")
PY

if command -v asciinema >/dev/null 2>&1 && command -v agg >/dev/null 2>&1; then
  echo ">> asciinema + agg found — also recording docs/assets/demo.gif…"
  asciinema rec --overwrite -c \
    "uv run provael attack --policy stub --suite stub --attacks instruction,visual,injection --episodes 10 --seed 0 --out $OUT_DIR" \
    /tmp/provael-demo.cast
  agg /tmp/provael-demo.cast docs/assets/demo.gif
  echo ">> wrote docs/assets/demo.gif"
fi

echo ">> done."
