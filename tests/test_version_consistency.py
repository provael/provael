"""One guard for every place the release version is restated.

`provael.__version__` is the single source of truth (hatch reads it to build the wheel), but the
version is echoed in a citation file, in the published Action's install pin, and in every
copy-paste CI snippet in the README, the docs and examples/. Those copies drift silently: nothing
imports them, so nothing notices when a release bumps the package and leaves them behind. They were
found at three different versions at once — 0.24.0 packaged, 0.22.0 in CITATION.cff, and 0.8.0 in
an examples snippet — and a snippet that pins a version users cannot get is worse than no snippet.

These assertions are deliberately cheap and mechanical so a release can satisfy them by search and
replace.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from provael import __version__

REPO = Path(__file__).resolve().parent.parent

#: Files carrying a copy-paste `uses: provael/provael@vX.Y.Z` snippet.
_ACTION_SNIPPETS = [
    "README.md",
    "docs/quickstart.md",
    "examples/ci/github-actions.yml",
    "examples/ci/regression-gate.yml",
    "examples/ci/regression-gate.md",
]

_ACTION_REF = re.compile(r"provael/provael@v(\d+\.\d+\.\d+)")


def test_citation_version_matches_the_package() -> None:
    """CITATION.cff is what a citing paper reproduces; a stale version misattributes the work."""
    cff = yaml.safe_load((REPO / "CITATION.cff").read_text(encoding="utf-8"))
    assert cff["version"] == __version__


@pytest.mark.parametrize("relpath", _ACTION_SNIPPETS)
def test_action_snippets_pin_the_current_release(relpath: str) -> None:
    """Every documented `uses: provael/provael@vX.Y.Z` names the version this tree builds."""
    path = REPO / relpath
    if not path.is_file():  # a snippet file may legitimately be removed
        pytest.skip(f"{relpath} not present")
    found = _ACTION_REF.findall(path.read_text(encoding="utf-8"))
    assert found, f"{relpath} carries no provael/provael@vX.Y.Z reference to check"
    stale = sorted({v for v in found if v != __version__})
    assert not stale, f"{relpath} pins {stale}, but this tree is {__version__}"


def test_action_install_pin_admits_the_current_version() -> None:
    """action.yml's default install bound must actually resolve to this release.

    The bound is a range rather than an exact pin, so the failure mode is not a mismatch but an
    EXCLUSION: `>=0.23.0,<0.24.0` silently refuses the very version the repo builds, and the Action
    installs an older release than the one it ships alongside.
    """
    from packaging.requirements import Requirement

    action = yaml.safe_load((REPO / "action.yml").read_text(encoding="utf-8"))
    spec = None
    for step in action["runs"]["steps"]:
        spec = (step.get("env") or {}).get("PROVAEL_VERSION", spec)
    assert spec is not None, "action.yml no longer declares PROVAEL_VERSION"

    # Mirrors the shell expansion in the install step: extras precede the specifier (PEP 508).
    requirement = Requirement(f"provael[attest]{spec}")
    assert requirement.specifier.contains(__version__), (
        f"action.yml pins provael{spec}, which excludes the packaged version {__version__}"
    )


def test_changelog_is_ready_for_the_current_version() -> None:
    """A tagged release extracts its notes from a `## [x.y.z]` heading; without one they are blank.

    Unreleased work lives under `## [Unreleased]`, so this only requires that the CHANGELOG has a
    section for the packaged version OR that the packaged version is still unreleased.
    """
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{__version__}]" in changelog or "## [Unreleased]" in changelog
