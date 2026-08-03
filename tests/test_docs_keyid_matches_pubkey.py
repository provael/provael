"""Every documented leaderboard keyid must be the one derived from the published key.

THE DRIFT THIS EXISTS TO STOP. The project signing key was rotated in #74 (the old private key
was unrecoverable), which changed the keyid the published board is signed with. Two documentation
surfaces kept printing the pre-rotation id in the verify command's expected output — with
`docs/leaderboard.md` going further and stating that id was *the only key the published board is
signed with*. A reader who did exactly what the docs said got an answer the docs called
impossible, and their most reasonable conclusion was that the signature is fake. For a project
whose entire pitch is "run the check yourself", a documented check that contradicts its own
documentation is the worst available defect.

The fix has the same shape as `test_counted_claims.py` and `test_version_consistency.py`: the
value has a single source (the published public key — the keyid is *derived from* it, by
`provael.attest.keyid_of`), every restatement is generated from that source
(`scripts/render_keyid.py`), and this guard sweeps every tracked file rather than an allow-list,
because the restatement that drifts is exactly the one nobody remembered to enumerate.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from provael.attest import keyid_of

REPO = Path(__file__).resolve().parent.parent

_PUBKEY = REPO / "leaderboard" / "results" / "leaderboard.pub"

#: A 16-hex token immediately after the token `keyid`, in any of the spellings the repo uses:
#: prose/console output (``keyid 5b9a…``), inline code (``keyid `5b9a…```), and JSON
#: (``"keyid": "5b9a…"``).
_KEYID_RE = re.compile(r"keyid[\"'`]?\s*[:=]?\s*[\"'`]?([0-9a-f]{16})\b")

#: Historical records are exempt, exactly as in `test_version_consistency.py` and
#: `test_counted_claims.py`: the CHANGELOG entry that published the pre-rotation keyid was true
#: when written, and rewriting it would falsify the record rather than correct a claim. Everything
#: else that names a keyid is a claim about *today* and must match the published key.
#: (`docs/errata.md` is NOT exempt — the erratum recording the rotation deliberately phrases the
#: superseded value so it never sits immediately after the token `keyid`.)
_HISTORICAL = frozenset({"CHANGELOG.md"})


def _tracked_text_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout
    return [REPO / name for name in out.split("\0") if name]


def _keyids_in_repo() -> list[tuple[str, str]]:
    """Every ``(path, keyid)`` adjacency in tracked non-historical text files."""
    found: list[tuple[str, str]] = []
    for path in _tracked_text_files():
        rel = path.relative_to(REPO).as_posix()
        if rel in _HISTORICAL:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary
        found.extend((rel, kid) for kid in _KEYID_RE.findall(text))
    return found


def test_the_scan_actually_finds_keyids() -> None:
    """Guard the guard: a sweep that matches nothing passes every assertion below vacuously.

    The signed board itself and both documentation surfaces name the keyid, so a healthy scan
    finds several. Fewer means the pattern rotted, not that the repo went quiet.
    """
    found = _keyids_in_repo()
    assert len(found) >= 3, f"the keyid sweep found only {found}; the pattern is not working"


def test_every_documented_keyid_matches_the_published_key() -> None:
    """No tracked file may claim a keyid the published public key does not derive to."""
    expected = keyid_of(_PUBKEY.read_bytes())
    wrong = sorted(
        {f"{rel}: keyid {kid}" for rel, kid in _keyids_in_repo() if kid != expected}
    )
    assert not wrong, (
        f"these files name a keyid that is not derived from {_PUBKEY.relative_to(REPO)} "
        f"(expected {expected}). Run `uv run python scripts/render_keyid.py` instead of typing "
        "keyids by hand:\n  " + "\n  ".join(wrong)
    )
