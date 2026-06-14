#!/usr/bin/env python3
"""Validate leaderboard submission `report.json` files (CPU-only).

Run by CI on PRs that touch `results/**`, and locally before you submit. Checks every
`report.json` under the given globs (default `results/*`): that it parses as a RunReport and
that its aggregate ASR / success counts are internally consistent (see
`vla_redteam.leaderboard.validate_report`). Exits non-zero if any report is missing/invalid.

Usage:
    python scripts/validate_submission.py            # checks results/*
    python scripts/validate_submission.py 'results/*'
"""

from __future__ import annotations

import sys

from vla_redteam.leaderboard import find_reports, validate_report
from vla_redteam.report import load_report


def main(argv: list[str]) -> int:
    globs = argv[1:] or ["results/*"]
    paths = find_reports(globs)
    if not paths:
        print(f"no report.json found under: {', '.join(globs)}")
        return 1
    ok = True
    for path in paths:
        try:
            report = load_report(path)
        except Exception as exc:  # noqa: BLE001 - any parse/validation failure is a hard fail
            print(f"FAIL {path}: not a valid report.json ({exc})")
            ok = False
            continue
        errors = validate_report(report)
        if errors:
            ok = False
            print(f"FAIL {path}:")
            for err in errors:
                print(f"  - {err}")
        else:
            print(
                f"OK   {path}  [{report.policy} x {report.suite}] "
                f"{report.successes}/{report.attempts}"
            )
    print(f"\n{'all submissions valid' if ok else 'INVALID submissions found'} "
          f"({len(paths)} report(s) checked)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
