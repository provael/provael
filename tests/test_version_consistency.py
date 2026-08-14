"""One guard for every place the release version is restated.

`provael.__version__` is the single source of truth (hatch reads it to build the wheel), but the
version is echoed in a citation file, in the published Action's install pin, and in every
copy-paste CI snippet in the README, the docs and examples/. Those copies drift silently: nothing
imports them, so nothing notices when a release bumps the package and leaves them behind. They were
found at three different versions at once — 0.24.0 packaged, 0.22.0 in CITATION.cff, and 0.8.0 in
an examples snippet — and a snippet that pins a version users cannot get is worse than no snippet.

WHY THIS SCANS THE REPO INSTEAD OF A LIST OF FILES. The first version of this module checked five
named files. Two pins lived outside that list and drifted for exactly that reason:
``.github/workflows/checkpoint-security-gate.yml`` pinned the action at ``@v0.24.0`` — **a tag that
has never existed**, so the reference workflow a design partner is told to copy failed at ref
resolution — and ``.pre-commit-hooks.yaml`` documented ``v0.6.0`` as its rev, nineteen releases
stale. An allow-list can only guard what someone remembered to add to it, which is the one thing a
drifting pin is guaranteed not to be. So the scan now walks every tracked file and the *exemptions*
are the short, deliberate list.

Note the pins named in this docstring are written without their full syntax on purpose: this file
is scanned like any other, and spelling one out here would make the guard flag its own prose. The
exemption list stays for genuine historical records only, and a missing entry fails loudly rather
than passing silently — the safe direction for a check like this.

Two distinct failures are checked, because they are distinct:

1. **A pin that names a version that does not exist.** Fatal anywhere, including historical
   CHANGELOG entries: a ref that cannot resolve is broken wherever it appears.
2. **An adopter-facing pin that names an older release.** Fatal in copy-paste surfaces, but
   correct and expected in the CHANGELOG, where old entries legitimately name old versions.

These assertions are deliberately cheap and mechanical so a release can satisfy them by search and
replace.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from provael import __version__

REPO = Path(__file__).resolve().parent.parent

#: Pin syntaxes that resolve a **git ref** on the user's side, and therefore break loudly when the
#: ref is wrong. Keyed by a human name used in assertion messages.
_PIN_PATTERNS: dict[str, re.Pattern[str]] = {
    "action ref": re.compile(r"provael/provael@v(\d+\.\d+\.\d+)"),
    "pre-commit rev": re.compile(r"^\s*#?\s*rev:\s*v(\d+\.\d+\.\d+)", re.MULTILINE),
}

#: Files whose pins are historical by nature and must NOT be forced to the current release. The
#: CHANGELOG's 0.3.0 entry describing the Action as it shipped in 0.3.0 is correct, not stale.
#: They are still subject to the "must name a real tag" check — a dead ref is dead anywhere.
_HISTORICAL = frozenset({"CHANGELOG.md"})

#: Surfaces that must never *lose* their pin. The scan below catches a pin that is wrong; it cannot
#: catch one that was deleted, because a file with no pin trivially satisfies every other check.
_MUST_CARRY_A_PIN = ("README.md", "docs/quickstart.md")


def _tracked_text_files() -> list[Path]:
    """Every git-tracked file that reads as text, relative to the repo root."""
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout
    return [REPO / name for name in out.split("\0") if name]


def _released_versions() -> set[str]:
    """Versions a user can actually resolve — the git tags, which are the only authority.

    The CHANGELOG is deliberately *not* used as a fallback: it and the tag list disagree in both
    directions (0.2.x is tagged with no CHANGELOG section; 0.1.0 has a section and no tag), so a
    CHANGELOG-derived set would both miss real tags and vouch for versions nobody can fetch.
    """
    proc = subprocess.run(
        ["git", "tag", "--list", "v*"], cwd=REPO, capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        return set()
    return {line.lstrip("v").strip() for line in proc.stdout.splitlines() if line.strip()}


def _pins_in_repo() -> list[tuple[Path, str, str]]:
    """Every ``(path, kind, version)`` git-ref pin in the tree."""
    found: list[tuple[Path, str, str]] = []
    for path in _tracked_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # a binary asset cannot carry a pin
        for kind, pattern in _PIN_PATTERNS.items():
            found.extend((path, kind, version) for version in pattern.findall(text))
    return found


def test_citation_version_matches_the_package() -> None:
    """CITATION.cff is what a citing paper reproduces; a stale version misattributes the work."""
    cff = yaml.safe_load((REPO / "CITATION.cff").read_text(encoding="utf-8"))
    assert cff["version"] == __version__


def test_the_scan_actually_finds_pins() -> None:
    """Guard the guard: a scan that silently matches nothing passes every assertion below.

    This is the same failure the CI dependency audit had — a check that inspected the wrong thing
    and reported success on every run. A structural check needs its own vacuity guard.
    """
    pins = _pins_in_repo()
    assert len(pins) >= 5, f"the repo-wide pin scan found only {len(pins)} pins; it is not working"
    kinds = {pin[1] for pin in pins}
    assert kinds == set(_PIN_PATTERNS), f"no pins matched for {set(_PIN_PATTERNS) - kinds}"


@pytest.mark.parametrize("relpath", _MUST_CARRY_A_PIN)
def test_the_adopter_surfaces_still_carry_a_pin(relpath: str) -> None:
    """A deleted snippet passes every correctness check by having nothing to check."""
    pinned = {pin[0].relative_to(REPO).as_posix() for pin in _pins_in_repo()}
    assert relpath in pinned, f"{relpath} no longer carries a provael/provael@vX.Y.Z snippet"


def test_every_pin_names_a_tag_that_exists() -> None:
    """The `@v0.24.0` failure: a documented ref pointing at a release that was never tagged.

    ``__version__`` is accepted alongside the published tags because a release PR legitimately
    repins everything to the version it is about to tag. That still catches the original bug: the
    tree was 0.25.0 when the workflow said 0.24.0, so 0.24.0 was neither tagged nor in flight.
    """
    released = _released_versions()
    if not released:
        # Never let this pass quietly where it matters. A shallow CI clone fetches no tags, so the
        # workflow sets `fetch-tags: true`; if that regresses, fail rather than skip.
        assert not os.environ.get("CI"), (
            "no git tags available in CI — the checkout must set `fetch-tags: true` or this "
            "guard silently passes"
        )
        pytest.skip("no git tags available (shallow clone or no git); cannot verify")

    resolvable = released | {__version__}
    broken = sorted(
        {
            f"{path.relative_to(REPO).as_posix()} pins a nonexistent v{version} ({kind})"
            for path, kind, version in _pins_in_repo()
            if version not in resolvable
        }
    )
    assert not broken, "pins naming a tag that does not exist:\n  " + "\n  ".join(broken)


def test_adopter_facing_pins_name_the_current_release() -> None:
    """Every copy-paste pin outside the CHANGELOG names the version this tree builds."""
    stale = sorted(
        {
            f"{path.relative_to(REPO).as_posix()} pins v{version} ({kind})"
            for path, kind, version in _pins_in_repo()
            if path.relative_to(REPO).as_posix() not in _HISTORICAL and version != __version__
        }
    )
    assert not stale, (
        f"this tree is {__version__}, but these pins are stale:\n  " + "\n  ".join(stale)
    )


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


#: `## [1.2.3] <dash> 2026-08-09` — the *dated* form only. An undated heading (`## [Unreleased]`)
#: is a work-in-progress marker and makes no claim about having shipped; a dated one does.
#: Dash class matches scripts/check_changelog.py, which accepts hyphen, en dash and em dash.
_DATED_HEADING = re.compile(r"^##[ \t]+\[(\d+\.\d+\.\d+)\][ \t]*[-–—][ \t]*\d{4}-\d{2}-\d{2}[ \t]*$",
                            re.MULTILINE)


#: Dated headings that predate the tagging discipline and can never be reconciled: you cannot tag
#: a release that was never cut. Recorded here rather than deleted from the CHANGELOG, because the
#: section is the only surviving record of what 0.1.0 contained. :func:`_released_versions` already
#: documents this same asymmetry from the other side ("0.1.0 has a section and no tag").
#: **Do not extend this list to excuse a new gap** — it is history, not a policy.
_UNTAGGABLE_HISTORY = frozenset({"0.1.0"})


def _dated_changelog_versions() -> list[str]:
    """Versions the CHANGELOG presents as released, newest first (file order)."""
    return _DATED_HEADING.findall((REPO / "CHANGELOG.md").read_text(encoding="utf-8"))


def test_every_dated_changelog_version_has_a_tag() -> None:
    """The changelog must not get ahead of the artifact.

    THE FAILURE THIS CATCHES. On 13 August 2026 ``CHANGELOG.md`` carried
    ``## [0.33.1] — 2026-08-13`` and ``CITATION.cff`` carried ``date-released: "2026-08-13"``,
    while ``git tag`` had no ``v0.33.1`` and PyPI's latest was still 0.33.0. Every surface a
    reader consults said the version had shipped; nothing had. That is the same class of drift as
    the counted-claims tests — a claim in the repo with no artifact behind it — and it was found by
    a person, not by CI.

    A **dated** heading is the claim. ``## [Unreleased]`` asserts nothing and is ignored here, so
    the normal workflow (accumulate under Unreleased, promote in the release commit, tag) is
    unaffected until the promotion happens.

    THE ONE EXEMPTION, and its cost. The newest dated heading may be untagged when it names
    :data:`~provael.__version__` — that is the release-prep commit, where promoting the heading and
    pushing the tag cannot be the same event. ``test_every_pin_names_a_tag_that_exists`` grants the
    same window for the same reason. The cost is real and worth stating: this test could not have
    failed on the exact commit that introduced the drift above. What it does catch is the drift
    *persisting* — the moment any further version lands, or a second release is prepared, the
    untagged heading stops being the newest and this fails. A one-commit blind spot in exchange for
    never shipping two.
    """
    tagged = _released_versions()
    if not tagged:
        # Same posture as test_every_pin_names_a_tag_that_exists: never pass vacuously where it
        # matters. Both workflows set `fetch-depth: 0` precisely so this list is real.
        assert not os.environ.get("CI"), (
            "no git tags available in CI — the checkout must set `fetch-depth: 0` or this "
            "test verifies nothing"
        )
        pytest.skip("no git tags available (shallow clone or no git); cannot verify")

    dated = _dated_changelog_versions()
    assert len(dated) >= 5, (
        f"the dated-heading scan found only {len(dated)} headings; it is not working"
    )

    untagged = [
        version for version in dated
        if version not in tagged and version not in _UNTAGGABLE_HISTORY
    ]
    if not untagged:
        return

    in_flight = untagged[0] == dated[0] == __version__
    remaining = untagged[1:] if in_flight else untagged
    assert not remaining, (
        "CHANGELOG.md presents these versions as released, but no git tag exists for them:\n  "
        + "\n  ".join(f"v{version}" for version in remaining)
        + "\n\n  A dated heading is a claim that users can install it. Either cut the tag, or "
        "move the section back under [Unreleased] until you do."
    )
