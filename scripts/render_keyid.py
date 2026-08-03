#!/usr/bin/env python3
"""Rewrite every documented leaderboard keyid to the one derived from the published key.

The keyid is not a fact anyone should type: it is *derived* — the first 16 hex chars of
SHA-256 over ``leaderboard/results/leaderboard.pub`` (`provael.attest.keyid_of`). The signing
key rotated in #74 and two docs kept printing the pre-rotation id in the verify command's
expected output, so a reader following the docs got an answer the docs called impossible.

This script is the single writer of that value into prose. Run it after any key rotation:

    uv run python scripts/render_keyid.py            # rewrite in place
    uv run python scripts/render_keyid.py --check    # exit 1 on drift, write nothing

`tests/test_docs_keyid_matches_pubkey.py` sweeps every tracked file for the same pattern, so a
hand-typed keyid anywhere fails CI whether or not it was listed here.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from provael.attest import keyid_of  # noqa: E402

PUBKEY = REPO / "leaderboard" / "results" / "leaderboard.pub"

#: The documentation surfaces that restate the keyid. The sweep test guards the whole tree; this
#: list only says where a rewrite is *expected* — a file here with no match is an error, because
#: it means the verify example lost its expected-output line.
TARGETS = ("README.md", "docs/leaderboard.md")

_KEYID_RE = re.compile(r"(keyid[ \t]*`?)([0-9a-f]{16})\b")


def main() -> int:
    check_only = "--check" in sys.argv[1:]
    expected = keyid_of(PUBKEY.read_bytes())
    drifted: list[str] = []

    for name in TARGETS:
        path = REPO / name
        text = path.read_text(encoding="utf-8")
        matches = _KEYID_RE.findall(text)
        if not matches:
            print(f"ERROR: {name} contains no `keyid <16-hex>` to render", file=sys.stderr)
            return 2
        rendered = _KEYID_RE.sub(lambda m: m.group(1) + expected, text)
        if rendered != text:
            drifted.append(name)
            if not check_only:
                path.write_text(rendered, encoding="utf-8")

    if drifted:
        verb = "would rewrite" if check_only else "rewrote"
        print(f"keyid {expected}: {verb} {', '.join(drifted)}")
        return 1 if check_only else 0
    print(f"keyid {expected}: all targets already current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
