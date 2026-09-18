#!/usr/bin/env python3
"""Rewrite ``campaign.json`` for every committed campaign, from the shards beside it.

One combined view per ``results/gpu-scheduled/campaign-<version>/`` directory, through
:func:`provael.campaign.combine_campaign` — which uses :mod:`provael.combine`, the combiner
``provael evidence-manifest`` already uses, rather than a second one. What the artifact is and is
not (never ``report.json``, never a ledger row, partial in its own words) is written once, in
:mod:`provael.campaign`'s docstring, and pinned by ``tests/test_campaign.py``.

DETERMINISM. The output is a pure function of the shards on disk: no wall-clock value, so a rerun
on an unchanged tree is a no-op and ``--check`` means "this is current". A directory with no shard
yet has no artifact and passes ``--check`` trivially.

Usage::

    python scripts/combine_campaign.py            # rewrite
    python scripts/combine_campaign.py --check    # fail if a rewrite would change anything
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from provael.campaign import (  # noqa: E402
    CAMPAIGN_JSON,
    campaign_dirs,
    combine_campaign,
    load_plan,
    render_campaign,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Combine each campaign's shards.")
    parser.add_argument("--check", action="store_true", help="fail instead of writing")
    parser.add_argument(
        "--results", type=Path, default=ROOT / "results", help="results tree (default: results/)"
    )
    parser.add_argument("--plan", type=Path, default=None, help="plan file (default: committed)")
    args = parser.parse_args(argv)

    plan = load_plan(args.plan) if args.plan else load_plan()
    stale = 0
    for directory in campaign_dirs(args.results):
        content = combine_campaign(plan, directory)
        out = directory / CAMPAIGN_JSON
        rel = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out
        if content is None:
            print(f"empty    {directory} (no shard has landed)")
            continue
        rendered = render_campaign(content)
        if args.check:
            current = out.read_text(encoding="utf-8") if out.is_file() else ""
            if current != rendered:
                print(f"{rel} is stale. Run `make gen-campaign` and commit it.", file=sys.stderr)
                stale += 1
            else:
                print(f"ok       {rel} ({content['shardsDone']}/{content['shardsTotal']} shards)")
            continue
        out.write_text(rendered, encoding="utf-8")
        print(f"wrote {rel} ({content['shardsDone']}/{content['shardsTotal']} shards)")
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
