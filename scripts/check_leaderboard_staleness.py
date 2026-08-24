#!/usr/bin/env python3
"""Refuse a published leaderboard whose rows have aged out without saying so.

WHAT WENT WRONG. `leaderboard/results/leaderboard.json` publishes four rows measured with provael
0.32.0 from a board assembled at commit 8cd8d99. By 0.37.0 those numbers were six minor versions
old. The board said so — in prose, in a banner the Space renders — and prose does not stop a
consumer. Anything reading the JSON got four rates, a signature, and no machine-readable way to
tell that the signature vouches for a measurement, not for its currency. A signature over stale
data reads as currency, which is worse than no signature.

WHAT THIS CHECKS, AND WHY NOT SIMPLY "IS IT STALE".

A gate that fails whenever the board is stale would be red today, red tomorrow, and red until a
GPU re-run that is not scheduled — and a detector that is permanently red reports nothing. Worse,
it would be red for a condition that is *disclosed*: a board honestly flagged `stale: true` is
doing exactly what it should.

So the failure condition is **undeclared** staleness: the board is more than
`MAX_MINOR_LAG` minor versions behind the running release AND does not carry `stale: true`. That
is actionable (refresh the flag), it clears, and it catches the real regression — a board quietly
drifting past the line while its own metadata still claims it is current.

The verdict is safe to commit because it is monotone: a row's measured version never changes and
the release only moves forward, so `stale: true` can never become wrong. Only a `false` can decay,
and that single direction is what this re-checks.

    python scripts/check_leaderboard_staleness.py                  # every published board
    python scripts/check_leaderboard_staleness.py --fix            # rewrite the flag in place

`--fix` refreshes `stale` / `stale_reason` only. It never touches `schema_version`, so the fields
stay outside the signing payload of an already-signed board (see `_FIELDS_ADDED_IN`) and the
Ed25519 signature keeps verifying — which is the whole reason a derived, time-dependent field is
not part of the signed subject.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from provael import __version__
from provael.leaderboard import MAX_MINOR_LAG, staleness

ROOT = Path(__file__).resolve().parent.parent
BOARDS = ROOT / "leaderboard" / "results"


def check(path: Path, *, fix: bool) -> list[str]:
    """Problems with one board (empty == fine). Rewrites the flag when ``fix``."""
    data = json.loads(path.read_text(encoding="utf-8"))
    name = path.relative_to(ROOT).as_posix()
    measured_with = data.get("measured_with") or []
    if not measured_with:
        # Not a failure: a board with no provenance predates the field. It is reported by the
        # is_restamp/coverage surfaces, and inventing a verdict here would be worse than silence.
        return []

    stale, reason = staleness(measured_with, __version__)
    declared = data.get("stale")

    if stale is None:
        return [f"{name}: {reason}"]
    if not stale:
        return []
    if declared is True:
        return []

    if fix:
        data["stale"] = True
        data["stale_reason"] = reason
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"fixed {name}: stale=true ({reason})")
        return []
    return [
        f"{name}: measured_with={measured_with} is more than {MAX_MINOR_LAG} minor version(s) "
        f"behind provael {__version__}, but the board declares stale={declared!r}.\n"
        f"    {reason}\n"
        f"    Either re-run the underlying policy, or run:\n"
        f"      python scripts/check_leaderboard_staleness.py --fix"
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix", action="store_true", help="rewrite the flag instead of failing")
    args = parser.parse_args()

    boards = sorted(BOARDS.glob("*.json"))
    if not boards:
        print(f"no published boards under {BOARDS.relative_to(ROOT)}", file=sys.stderr)
        return 1

    problems = [p for board in boards for p in check(board, fix=args.fix)]
    if problems:
        print("undeclared leaderboard staleness:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print(f"{len(boards)} published board(s): staleness declared honestly against {__version__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
