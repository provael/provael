"""The gate that would have caught #157 and #158 merging with no changelog line.

`check_changelog.py` gates a RELEASE and could not have caught either: `[Unreleased]` was
non-empty, so it was satisfied by entries about an unrelated change while a corrected confidence
interval went unrecorded. This one gates the PR.

The decision function is pure, so these tests need no checkout, no network and no GitHub event.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "check_changelog_entry", REPO / "scripts" / "check_changelog_entry.py"
)
assert _spec and _spec.loader
cce = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cce)


def test_src_change_without_a_changelog_line_is_refused() -> None:
    ok, msg = cce.decide(["src/provael/scoring/paired.py"], [])
    assert not ok
    assert "src/provael/scoring/paired.py" in msg


def test_results_change_without_a_changelog_line_is_refused() -> None:
    ok, _ = cce.decide(["results/smolvla_libero_object_suite/README.md"], [])
    assert not ok


def test_readme_change_without_a_changelog_line_is_refused() -> None:
    """The exact shape of #157: a published number moved on README.md and nothing recorded it."""
    ok, _ = cce.decide(["README.md"], [])
    assert not ok


def test_a_changelog_line_alongside_the_change_passes() -> None:
    ok, _ = cce.decide(["src/provael/scoring/paired.py", "CHANGELOG.md"], [])
    assert ok


def test_the_skip_label_allows_a_no_op() -> None:
    ok, msg = cce.decide(["src/provael/runner.py"], ["no-changelog"])
    assert ok
    assert "no-changelog" in msg


def test_an_unrelated_label_does_not_allow_it() -> None:
    """Only the named label skips. Any label passing would make the gate decorative."""
    ok, _ = cce.decide(["src/provael/runner.py"], ["bug", "documentation"])
    assert not ok


def test_untouched_areas_do_not_require_an_entry() -> None:
    """docs/, tests/ and .github/ are out of scope: requiring a line for every test would train
    contributors to write filler, which hides the real entries."""
    ok, _ = cce.decide(["tests/test_paired.py", "docs/errata.md", ".github/workflows/ci.yml"], [])
    assert ok


def test_readme_is_matched_exactly_not_by_prefix() -> None:
    """`README.md` is a watched FILE, not a prefix — a nested README is covered only when it is
    under a watched directory, and `docs/README.md` is not."""
    ok, _ = cce.decide(["docs/README.md"], [])
    assert ok
    ok, _ = cce.decide(["results/smolvla_libero_object_suite/README.md"], [])
    assert not ok


def test_the_guard_can_actually_fail() -> None:
    """Pin the decision against the real #157 diff shape, so the watched list cannot quietly stop
    matching the paths it was written for."""
    pr157_published_paths = [
        "src/provael/scoring/paired.py",
        "README.md",
        "results/smolvla_libero_object_suite/README.md",
    ]
    ok, _ = cce.decide(pr157_published_paths, [])
    assert not ok, "the watched list no longer matches the change this gate was written for"
    assert cce.watched(pr157_published_paths) == sorted(pr157_published_paths)
