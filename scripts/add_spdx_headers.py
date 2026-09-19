#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Put the SPDX licence header on every source file, idempotently.

WHY THIS EXISTS. The repository is Apache-2.0 at the root, but until 20 September 2026 not one of
its 329 Python files said so in-band. Licence scanners (ScanCode, FOSSA, REUSE) read per-file
identifiers, not the root LICENSE, and report every unmarked file as "unknown licence" — a clean
scan is what a diligence reader or a downstream packager expects, and it costs two lines per file.

The header is the two-line SPDX form recommended by the REUSE specification::

    # SPDX-License-Identifier: Apache-2.0
    # Copyright (c) 2026 Sattyam Jain

Rules, so the result is deterministic and a re-run is a no-op:

* A shebang stays on line 1; the header goes directly under it.
* A file that already carries the licence identifier line is left exactly as it is, even if its
  copyright line differs (an older year is history, not an error).
* Only ``.py`` and ``.sh`` files are touched. YAML and TOML carry their own leading comments,
  JSON cannot carry a comment at all, and Markdown is prose — ``tests/test_spdx_headers.py``
  enforces the same scope, so the two agree on what "every source file" means.

Usage::

    python scripts/add_spdx_headers.py [--check] [paths...]

With no paths it walks ``src/``, ``scripts/``, ``tests/`` and ``examples/`` as tracked by git.
``--check`` rewrites nothing and exits 1 on any file missing the header, which is what the test
calls.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TREES = ("src", "scripts", "tests", "examples")
SUFFIXES = (".py", ".sh")
LICENSE_LINE = "# SPDX-License-Identifier: Apache-2.0"
COPYRIGHT_LINE = "# Copyright (c) 2026 Sattyam Jain"
HEADER = f"{LICENSE_LINE}\n{COPYRIGHT_LINE}\n"


def tracked_source_files(root: Path = ROOT) -> list[Path]:
    """Every git-tracked ``.py``/``.sh`` file under the four source trees, sorted."""
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--", *TREES],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return sorted(root / line for line in out.splitlines() if line.endswith(SUFFIXES))


def has_header(text: str) -> bool:
    """True when the licence identifier sits within the first three lines."""
    return LICENSE_LINE in text.splitlines()[:3]


def with_header(text: str) -> str:
    """Return ``text`` with the header inserted under any shebang."""
    if has_header(text):
        return text
    if text.startswith("#!"):
        first_newline = text.find("\n")
        if first_newline == -1:
            return text + "\n" + HEADER
        return text[: first_newline + 1] + HEADER + text[first_newline + 1 :]
    return HEADER + text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Add the SPDX header to source files.")
    ap.add_argument("paths", nargs="*", type=Path, help="files to process (default: all tracked)")
    ap.add_argument(
        "--check", action="store_true", help="report files missing the header; write nothing"
    )
    args = ap.parse_args(argv)

    files = [p.resolve() for p in args.paths] if args.paths else tracked_source_files()
    missing: list[Path] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        if has_header(text):
            continue
        missing.append(path)
        if not args.check:
            path.write_text(with_header(text), encoding="utf-8")

    rel = [str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p) for p in missing]
    if args.check:
        if rel:
            print(f"{len(rel)} file(s) without the SPDX header:", file=sys.stderr)
            for r in rel:
                print(f"  {r}", file=sys.stderr)
            return 1
        print(f"every tracked source file carries the SPDX header ({len(files)} checked)")
        return 0
    print(f"added the SPDX header to {len(rel)} file(s); {len(files) - len(rel)} already had it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
