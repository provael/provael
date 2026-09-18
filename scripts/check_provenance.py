#!/usr/bin/env python3
"""Refuse to record a shard whose execution manifest lacks the provenance a published number needs.

WHY THIS EXISTS. Every scheduled-lane manifest ever committed reported four gaps under
``missing_fields`` — ``repository``, ``commit``, ``dep_lock_digest``, ``precision`` — and the lane
recorded the run anyway, because nothing read that list. The 2026-09-15 run did so a day after the
workflow's checkout step gained the comment saying the commit gap was fixed: the fix lived in the
repository's ``main`` while the container installed the released wheel, which read no
``PROVAEL_COMMIT`` at all. A gap that is admitted and then ignored is worse than one nobody
noticed, and these shards are now combined into a campaign that displaces the published measurement.

So the workflow runs this BEFORE ``provael watch --record``, on every shard the run declared, and
stops on the first shard that cannot say what code and what package set produced it. The message
names the shard and the field, because "provenance incomplete" is not something anyone can act on.

The rule itself lives in :func:`provael.campaign.provenance_gaps`, where the combiner applies the
same test; this script is the workflow's way of calling it, lifted out of YAML so it can be tested.

Usage::

    python scripts/check_provenance.py results/gpu-scheduled/campaign-0.42.0/<shard> ...
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from provael.campaign import REQUIRED_PROVENANCE, check_provenance  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail if any shard's execution manifest lacks required provenance."
    )
    parser.add_argument("shards", nargs="+", type=Path, help="shard directories to check")
    args = parser.parse_args(argv)

    problems = check_provenance(list(args.shards))
    if problems:
        for shard, gaps in sorted(problems.items()):
            print(f"{shard}: missing {', '.join(gaps)}", file=sys.stderr)
        print(
            f"\n{len(problems)} shard(s) lack provenance a published number needs "
            f"({', '.join(REQUIRED_PROVENANCE)}). Nothing was recorded. Either the container ran "
            "a provael release that predates these fields (the lane's PROVAEL_PIN must be >= the "
            "release that carries them) or the driver stopped passing PROVAEL_REPOSITORY / "
            "PROVAEL_COMMIT into the image.",
            file=sys.stderr,
        )
        return 1
    for shard in args.shards:
        print(f"ok       {shard}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
