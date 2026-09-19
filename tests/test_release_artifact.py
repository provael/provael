# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""`watch/release.json` must never disagree with the package it describes.

WHY THIS GUARD IS THE WHOLE POINT OF THE ARTIFACT. The file exists so a consumer derives the
release instead of keeping a copy, and a copy that drifts is exactly the defect it replaces: on
6 September 2026, 14 built pages of www.provael.com rendered v0.39.3 while the tag, the GitHub
release and PyPI all said 0.39.4. An artifact published for consumption that can itself go stale
would move the same bug one hop rather than fix it.

So the assertion is deliberately narrow and total: every value in the file derives from
`provael.__version__`, and the committed bytes must equal a fresh render.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from provael import __version__

REPO = Path(__file__).resolve().parents[1]
ARTIFACT = REPO / "watch" / "release.json"


def _generator():
    spec = importlib.util.spec_from_file_location(
        "gen_release_artifact", REPO / "scripts" / "gen_release_artifact.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_artifact_exists() -> None:
    assert ARTIFACT.is_file(), f"{ARTIFACT} is missing. Run `make gen-release`."


def test_version_matches_the_package() -> None:
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert data["version"] == __version__, (
        f"watch/release.json says {data['version']}, the package is {__version__}. "
        "Run `make gen-release` and commit the result."
    )
    assert data["tag"] == f"v{__version__}"
    assert data["pypi"] == __version__


def test_committed_bytes_equal_a_fresh_render() -> None:
    """The same rule `--check` enforces, so a stale artifact fails the suite and not only CI."""
    assert _generator().main(["--check"]) == 0


def test_no_unverifiable_field_crept_in() -> None:
    """A commit sha or a timestamp here could only have been guessed by an offline script.

    Named explicitly rather than left to the note, because the tempting next commit is the one that
    adds `published_at` for a consumer that wants to render a date, and a guessed date in a trust
    artifact is worse than no date.
    """
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    for forbidden in ("commit", "sha", "published_at", "publishedAt", "released", "date"):
        assert forbidden not in data, (
            f"{forbidden!r} is in watch/release.json. This script runs offline and cannot verify "
            "it. If CI knows the value, emit it there and say so in the note."
        )


def test_render_is_deterministic() -> None:
    gen = _generator()
    assert gen.render() == gen.render()


def test_the_release_artifact_publishes_the_drift_window() -> None:
    """The threshold must reach consumers as data, not as a number they retype.

    www.provael.com held its own `STALE_AFTER_RELEASES = 2` in TypeScript while `watch.py` held
    another. Two copies of one policy constant across two repositories, and a disagreement between
    them would be invisible from both sides — the site would show one window, `provael doctor`
    another, and nothing would fail. Publishing it here is what lets the site stop keeping a copy.
    """
    import json

    from provael.watch import STALE_AFTER_RELEASES

    published = json.loads((REPO / "watch" / "release.json").read_text(encoding="utf-8"))
    assert published["staleAfterReleases"] == STALE_AFTER_RELEASES, (
        "watch/release.json publishes a different drift window than watch.py enforces — run "
        "`make gen-release` and commit the result"
    )
    assert isinstance(published["staleAfterReleases"], int), (
        "the window must publish as a number a consumer can compare, not a string it must parse"
    )
