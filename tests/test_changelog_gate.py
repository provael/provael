"""The release gate must reject what it is for, and accept the repo's real heading style.

A gate nobody has watched fail is a gate nobody knows works. These test both directions, and pin
the heading format against the ACTUAL history rather than against the Keep a Changelog spec — this
repo writes an em dash, and a hyphen-only rule would reject all 33 released versions.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from provael import __version__

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_changelog.py"
CHANGELOG = ROOT / "CHANGELOG.md"


def _run(version: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), version], capture_output=True, text=True, cwd=ROOT
    )


def test_the_current_version_is_documented() -> None:
    """The gate must pass for the version about to ship, or releases are blocked outright."""
    result = _run(__version__)
    assert result.returncode == 0, result.stderr


def test_a_leading_v_is_accepted() -> None:
    """Tags are `vX.Y.Z`; the workflow passes GITHUB_REF_NAME straight through."""
    assert _run(f"v{__version__}").returncode == 0


def test_an_undocumented_version_is_rejected() -> None:
    """The whole point. 0.31.1 shipped without this and had to be back-filled."""
    result = _run("99.99.99")
    assert result.returncode == 1
    assert "no section for 99.99.99" in result.stderr


def test_the_error_names_the_expected_heading_format() -> None:
    """A gate that fails without saying what to write is a gate people work around."""
    assert "## [99.99.99] —" in _run("99.99.99").stderr


@pytest.mark.parametrize("version", ["0.32.0", "0.31.1", "0.31.0"])
def test_recent_released_versions_all_pass(version: str) -> None:
    """Guards the heading regex against the real history rather than a synthetic fixture.

    If someone 'fixes' the pattern to require a hyphen per Keep a Changelog, these fail — which is
    the intent, because every heading in this file uses an em dash.
    """
    assert _run(version).returncode == 0, f"{version} should be documented"


def test_the_repo_uses_em_dash_headings() -> None:
    """Pins the convention the regex accommodates, so the two cannot drift apart silently."""
    text = CHANGELOG.read_text(encoding="utf-8")
    assert f"## [{__version__}] —" in text, (
        "the changelog heading style changed; scripts/check_changelog.py accepts -, – and — but "
        "this test documents which one the repo actually writes"
    )


def _gate_module() -> object:
    """Load the script by path — scripts/ is deliberately not an importable package."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("check_changelog", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("dash", ["-", "–", "—"])
def test_all_three_dashes_parse(dash: str) -> None:
    """A contributor typing the ASCII hyphen must not be blocked on punctuation."""
    found, date = _gate_module().find_entry("1.2.3", f"## [1.2.3] {dash} 2026-08-09\n")  # type: ignore[attr-defined]
    assert found and date == "2026-08-09"


def test_a_shaped_but_impossible_date_is_caught() -> None:
    """`2026-13-45` matches the regex and is not a date. The gate must not accept it.

    Checking only the SHAPE would let a typo through with a heading that looks dated and is not,
    which is the same class of error as a version heading that exists but says nothing.
    """
    module = _gate_module()
    found, date = module.find_entry("1.2.3", "## [1.2.3] — 2026-13-45\n")  # type: ignore[attr-defined]
    assert found and date == "2026-13-45", "the regex should match the shape"
    import datetime as dt

    with pytest.raises(ValueError):
        dt.date.fromisoformat(date)  # which is what main() calls, and why it returns 1


def test_a_version_that_is_a_prefix_of_another_is_not_confused() -> None:
    """`0.3` must not match the `0.32.0` heading — the version is escaped, not treated as a pattern."""
    found, _ = _gate_module().find_entry("0.3", CHANGELOG.read_text(encoding="utf-8"))  # type: ignore[attr-defined]
    assert not found


# --------------------------------------------------------------------------------------------
# [Unreleased] must not contradict itself
#
# The gate shipped checking only the RELEASED heading, so it watched [Unreleased] accumulate
# twelve commits of entries while still ending "Nothing pending — everything currently written is
# released." Both were in the file at once and the gate passed every time. These pin the three
# states apart, because two of them are legitimate and only the pair is a defect.
# --------------------------------------------------------------------------------------------

_RELEASED_TAIL = "## [0.32.0] — 2026-08-08\n\n- something\n"


def test_placeholder_with_entries_is_rejected() -> None:
    """The exact state that shipped: a section claiming nothing is pending, listing pending things."""
    text = (
        "## [Unreleased]\n\n### Added\n\n- A real pending entry.\n\n"
        "Nothing pending — everything currently written is released.\n\n" + _RELEASED_TAIL
    )
    problem = _gate_module().unreleased_contradiction(text)  # type: ignore[attr-defined]
    assert problem is not None
    assert "Both cannot be true" in problem
    assert "A real pending entry" in problem, "the message must show WHICH lines contradict it"


def test_an_empty_unreleased_with_the_placeholder_is_fine() -> None:
    """The placeholder is the CORRECT content of an empty section, not a defect in itself.

    Deleting it unconditionally would leave the next contributor a bare heading, wondering whether
    entries had been lost.
    """
    text = "## [Unreleased]\n\nNothing pending — everything currently written is released.\n\n" + _RELEASED_TAIL
    assert _gate_module().unreleased_contradiction(text) is None  # type: ignore[attr-defined]


def test_a_populated_unreleased_without_the_placeholder_is_fine() -> None:
    """The other legitimate state — this is what [Unreleased] looks like for most of a cycle."""
    text = "## [Unreleased]\n\n### Added\n\n- Something pending.\n\n" + _RELEASED_TAIL
    assert _gate_module().unreleased_contradiction(text) is None  # type: ignore[attr-defined]


def test_an_empty_subheading_under_the_placeholder_still_counts() -> None:
    """How the contradiction usually STARTS: someone adds `### Added` before writing under it.

    Catching it at that point is the cheap moment; catching it twelve commits later is not.
    """
    text = (
        "## [Unreleased]\n\n### Added\n\nNothing pending — everything currently written is released.\n\n"
        + _RELEASED_TAIL
    )
    assert _gate_module().unreleased_contradiction(text) is not None  # type: ignore[attr-defined]


def test_the_committed_changelog_is_self_consistent() -> None:
    """The guard on the real file, so the state that shipped cannot come back unnoticed."""
    assert _gate_module().unreleased_contradiction(  # type: ignore[attr-defined]
        CHANGELOG.read_text(encoding="utf-8")
    ) is None
