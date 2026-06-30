# Provael demo — recording as code.
#
# Regenerate the README demo GIF with VHS (https://github.com/charmbracelet/vhs):
#   vhs scripts/demo.tape
#
# Deterministic: it runs the CPU stub pipeline (seed 0, all four families). For the
# static SVG variant (no external tools), use ./scripts/record_demo.sh instead.

Output docs/assets/demo.gif

Set Shell bash
Set FontSize 16
Set Width 1200
Set Height 640
Set Padding 20
Set TypingSpeed 40ms

Type "provael attack --recipe full-sweep --out runs/demo"
Sleep 500ms
Enter
Sleep 4s
