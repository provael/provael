"""Publish the DEFENDED figures from ``report.mitigation.json``.

THE OUTPUT IS CALLED ``residual-asr`` AND NOT ``asr``, and that naming is the entire safety
property of this script. The release gate reads the step output named ``asr``; the post-defense
rate is by construction lower than the undefended one. Emitting it under the gated name would let
any defense — including one that was never credited — silently lower the number the gate reads.
A defense must be MEASURED to count, never merely applied.

Usage: ``mitigation_outputs.py <report.mitigation.json>``
"""

from __future__ import annotations

import sys

from _github import emit, load


def main(argv: list[str]) -> int:
    path = argv[1] if len(argv) > 1 else "provael-mitigation/report.mitigation.json"
    m = load(path)
    emit(
        verdict=m["verdict"],
        report=path,
        position=m.get("position", ""),
        **{
            "residual-asr": m.get("post_adversarial_asr"),
            "defense-log": "provael-run-defended/defense-log.jsonl",
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
