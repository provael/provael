"""One guard for every prose claim that restates a number derived from the registry.

THE DRIFT THIS EXISTS TO STOP. `universal_patch` was registered in 0.29.0, taking the registry
from fourteen adversarial families to fifteen. The CHANGELOG entry for that very release said
"15 adversarial families (was 14)" — and `README.md`, `SAFETY.md` and `docs/roadmap.md` went on
saying **fourteen** for a whole release, because nothing imports prose and so nothing noticed.
`tests/test_recipes.py` already asserts that `full-sweep` covers every registry family; what it
could not see is that the documentation describing that sweep had fallen a family behind.

A counted claim is the cheapest thing in this repo to get wrong and one of the more expensive to
be caught getting wrong: the product's entire pitch is that its numbers are checkable, so a
reader who counts `provael list-attacks` and gets a different answer from the README has found a
reason to distrust every other number on the page. This guard is the same discipline as the
SHA-pinned workflows and `test_version_consistency.py` — the count has a single source (the
registry), and every restatement of it is checked against that source rather than trusted.

TWO CHECKS, BECAUSE THEY FAIL DIFFERENTLY.

1. **The enumerated claims** (`_CLAIMS`) pin an exact sentence in an exact file. If the number is
   stale it fails with both numbers; if the sentence was *reworded* the pattern stops matching and
   it fails too — a guard that silently matches nothing is the failure mode this repo has already
   been bitten by twice (the vacuous dependency audit, the pin scan that found no pins).
2. **The sweep** (`test_no_stale_family_count_anywhere`) re-reads every adopter-facing document
   for the phrase regardless of whether anyone remembered to enumerate it here. An allow-list only
   guards what someone thought to add to it, which is exactly what a new stale claim will not be.

WHY SOME FILES ARE EXEMPT. A count is not stale when it is *historical*. `CHANGELOG.md` describes
each release as it shipped; `docs/studies/action-envelope.md` reports a study measured on 0.28.0
over the fourteen families that existed then, and rewriting it to fifteen would attribute a
measurement to a registry that did not produce it. Those are records, not claims about today.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from provael.attacks.baseline import FAMILY as BASELINE_FAMILY
from provael.attacks.registry import ATTACKS
from provael.coverage import NON_ADVERSARIAL_FAMILIES

REPO = Path(__file__).resolve().parent.parent

#: Number words the prose actually uses. Deliberately not a general spell-out library: the range a
#: family count can plausibly occupy is small, and an unknown word should fail loudly rather than
#: be silently coerced.
_WORDS: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
}


def _as_int(token: str) -> int:
    """Parse a count written as either digits or an English word."""
    if token.isdigit():
        return int(token)
    try:
        return _WORDS[token.lower()]
    except KeyError:  # pragma: no cover - only reachable via a prose edit
        raise AssertionError(
            f"counted claim {token!r} is neither digits nor a number word this guard knows; "
            f"either it is prose the pattern should not have matched, or _WORDS needs extending"
        ) from None


# --------------------------------------------------------------------------- #
# the counts, derived from the registry — never hand-maintained
# --------------------------------------------------------------------------- #


def _registry_counts() -> dict[str, int]:
    """The numbers the documentation restates, computed from `ATTACKS` itself."""
    families = {ctor().family for ctor in ATTACKS.values()}
    adversarial = [n for n, ctor in ATTACKS.items() if ctor().family != BASELINE_FAMILY]
    return {
        "adversarial families": len(families - NON_ADVERSARIAL_FAMILIES),
        "total families": len(families),
        "total attacks": len(ATTACKS),
        "adversarial attacks": len(adversarial),
    }


@dataclass(frozen=True)
class _Claim:
    """A sentence in a shipped document that restates a registry-derived count."""

    relpath: str
    #: Must contain exactly one capture group: the number as written.
    pattern: str
    count: str


#: Every adopter-facing restatement of a registry count. Adding a new one here is cheap; the sweep
#: below is what catches the ones nobody added.
_CLAIMS: tuple[_Claim, ...] = (
    _Claim("README.md", r"It ships \*\*(\w+) adversarial families", "adversarial families"),
    _Claim("README.md", r"runs every one of the (\w+);", "adversarial families"),
    _Claim("SAFETY.md", r"registry ships \*\*(\w+) adversarial families\*\*", "adversarial families"),
    _Claim("docs/roadmap.md", r"\*\*Attacks:\*\* (\w+) adversarial families", "adversarial families"),
    _Claim("docs/index.md", r"all (\w+) adversarial families", "adversarial families"),
    _Claim("docs/quickstart.md", r"# (\w+) attacks across", "total attacks"),
    _Claim("docs/quickstart.md", r"attacks across (\w+) families", "total families"),
    _Claim("docs/quickstart.md", r"families \((\w+) adversarial", "adversarial families"),
    # README's `list-attacks` comment. It said "28 attacks" for two releases while
    # `docs/quickstart.md` — the same claim, one directory away — was corrected in 0.29.1,
    # because the enumerated list below only ever named quickstart. This pair is the fix for
    # that specific miss; the sweep is the fix for the class of it.
    _Claim("README.md", r"# (\w+) attacks across", "total attacks"),
    _Claim("README.md", r"attacks across (\w+) families", "total families"),
    # The leaderboard Space renders a coverage line but installs no `provael` (see its
    # requirements.txt), so it cannot import the registry and must hardcode the denominator.
    # That makes it exactly the kind of claim this guard exists for.
    _Claim("leaderboard/app.py", r"TOTAL_ADVERSARIAL_FAMILIES = (\d+)", "adversarial families"),
)


@pytest.mark.parametrize("claim", _CLAIMS, ids=lambda c: f"{c.relpath}:{c.count}")
def test_documented_count_matches_the_registry(claim: _Claim) -> None:
    expected = _registry_counts()[claim.count]
    path = REPO / claim.relpath
    assert path.is_file(), f"{claim.relpath} does not exist; the claim list is stale"
    found = re.findall(claim.pattern, path.read_text(encoding="utf-8"))

    # A pattern that matches nothing passes every assertion below it. Fail instead.
    assert found, (
        f"{claim.relpath} no longer contains the sentence this guard checks "
        f"(pattern {claim.pattern!r}). Either the prose was reworded — update the pattern — or the "
        f"claim was deleted. It is not safe to assume the count is still right."
    )
    for token in found:
        actual = _as_int(token)
        assert actual == expected, (
            f"{claim.relpath} says {token!r} ({actual}) {claim.count}, but the registry has "
            f"{expected}. The registry is the source of truth — update the prose, not this test. "
            f"(Run `provael list-attacks` to see the current set.)"
        )


def test_the_leaderboard_space_names_the_current_release() -> None:
    """The Space installs no `provael`, so its "you are here" version is an unguarded string.

    It is what makes `measured_with: ["0.1.0"]` legible as *stale* rather than merely *a version*.
    If it silently fell behind, the banner would understate the gap it exists to state.
    """
    from provael import __version__

    text = (REPO / "leaderboard" / "app.py").read_text(encoding="utf-8")
    found = re.findall(r'CURRENT_RELEASE = "([\d.]+)"', text)
    assert found, "leaderboard/app.py no longer declares CURRENT_RELEASE"
    for version in found:
        assert version == __version__, (
            f"leaderboard/app.py says CURRENT_RELEASE = {version!r} but the package is "
            f"{__version__!r}. The Space cannot import provael, so nothing else will catch this."
        )


def test_the_claim_scan_is_not_vacuous() -> None:
    """Guard the guard: if every pattern quietly stopped matching, the suite would still pass."""
    total = sum(
        len(re.findall(c.pattern, (REPO / c.relpath).read_text(encoding="utf-8"))) for c in _CLAIMS
    )
    assert total >= len(_CLAIMS), (
        f"the counted-claim scan matched {total} times across {len(_CLAIMS)} claims; it is not "
        f"inspecting what it thinks it is"
    )


# --------------------------------------------------------------------------- #
# the sweep — catches a stale count in a file nobody enumerated above
# --------------------------------------------------------------------------- #

#: Files whose counts are **historical records**, not claims about the current registry, and which
#: must therefore NOT be forced to today's number:
#:
#: * ``CHANGELOG.md`` — each entry describes the registry as it was at that release.
#: * ``docs/studies/action-envelope.md`` — a study stamped ``Tool version 0.28.0`` whose committed
#:   report digests were produced over the fourteen families that existed then. Rewriting it would
#:   attribute a measurement to a registry that never produced it.
#: * ``examples/recipes/*`` and ``src/provael/recipes.py`` — prose explaining *why* `core-sweep`
#:   was renamed, which is a statement about the registry size at the time of the rename.
#: * ``tests/`` — this file quotes the phrase in its own patterns, and `test_recipes.py` documents
#:   the original four-of-fourteen bug in its docstring.
_HISTORICAL = frozenset({
    "CHANGELOG.md",
    "docs/studies/action-envelope.md",
    "examples/recipes/README.md",
    "examples/recipes/core-sweep.yml",
    "src/provael/recipes.py",
})

#: Any phrasing that states a family count. The count token must be digits or a number word this
#: guard knows — the first draft matched any `\w+` and flagged `compliance.py`'s "No EAI-tagged
#: adversarial families were run", which states no count at all. Building the alternation from
#: :data:`_WORDS` keeps the two in step: a stale count is always *some* number, so narrowing the
#: token to numbers loses no real claim while dropping the prose false positives.
_SWEEP = re.compile(r"\b(\d+|" + "|".join(_WORDS) + r") adversarial families", re.IGNORECASE)


def _tracked_text_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout
    return [REPO / name for name in out.split("\0") if name]


def test_no_stale_family_count_anywhere() -> None:
    """Re-read the whole tree, so a new stale claim fails even if nobody enumerated it above."""
    expected = _registry_counts()["adversarial families"]
    stale: list[str] = []
    scanned = 0
    for path in _tracked_text_files():
        rel = path.relative_to(REPO).as_posix()
        if rel in _HISTORICAL or rel.startswith("tests/"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # a binary asset cannot carry a claim
        for token in _SWEEP.findall(text):
            scanned += 1
            if _as_int(token) != expected:
                stale.append(f"{rel}: says {token!r} ({_as_int(token)}), registry has {expected}")

    assert scanned, "the family-count sweep matched nothing at all; the phrasing must have changed"
    assert not stale, "stale family counts:\n  " + "\n  ".join(stale)


# --------------------------------------------------------------------------- #
# the `list-attacks` sweep — the shape that got past both checks above
# --------------------------------------------------------------------------- #

#: WHY A SECOND SWEEP. `README.md` said "28 attacks across …" for two releases while
#: `docs/quickstart.md` — the identical claim one directory away — was corrected in 0.29.1. Neither
#: check above could see it. The enumerated list named only quickstart, and
#: :data:`_SWEEP` keys on the noun phrase "adversarial families", which that README line never
#: used: it wrote the count against an *enumerated family list* inside a shell comment in a fenced
#: code block. Nothing about being in a code fence hid it — the sweep reads whole files — the
#: phrasing simply fell outside the only pattern being looked for.
#:
#: WHY THIS ANCHOR AND NOT A BROADER ONE. Sweeping every "N attacks" or "N families" in the tree
#: is the obvious generalisation and it is wrong: most such phrases are true statements about a
#: *subset*, not restatements of the registry. `attacks/action.py` says "Two attacks" of its own
#: family, `recipes.py` says "nine attacks across four families" of the `quick` preset, and the
#: crosswalk says "three families" of a mapping. A guard that failed on those would be reverted
#: within a week, which is worse than no guard.
#:
#: `provael list-attacks` is the anchor that carries the meaning, because
#: :func:`provael.cli.list_attacks` iterates :data:`~provael.attacks.registry.ATTACKS` and prints
#: every family — so a count offered as *what that command shows* is a claim about the whole
#: registry, always, with no subset reading available. That is exactly the claim that was wrong in
#: `README.md`, and it was wrong a second time in `notebooks/01_provael_in_5_minutes.ipynb`, which
#: annotated `list-attacks` with the `quick` recipe's nine-attacks-four-families figure.
_LIST_ATTACKS_COUNT = re.compile(
    r"list-attacks\b[^\n]{0,120}?\b(\d+|" + "|".join(_WORDS) + r")\s+attacks"
    r"(?:[^\n]{0,40}?\b(\d+|" + "|".join(_WORDS) + r")\s+families)?",
    re.IGNORECASE,
)


def test_list_attacks_counts_describe_the_whole_registry() -> None:
    """Any count offered as the output of `list-attacks` must be the registry's own."""
    attacks = _registry_counts()["total attacks"]
    families = _registry_counts()["total families"]
    wrong: list[str] = []
    matched = 0
    for path in _tracked_text_files():
        rel = path.relative_to(REPO).as_posix()
        if rel in _HISTORICAL or rel.startswith("tests/"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for got_attacks, got_families in _LIST_ATTACKS_COUNT.findall(text):
            matched += 1
            if _as_int(got_attacks) != attacks:
                wrong.append(
                    f"{rel}: annotates `list-attacks` with {got_attacks!r} attacks, "
                    f"registry has {attacks}"
                )
            if got_families and _as_int(got_families) != families:
                wrong.append(
                    f"{rel}: annotates `list-attacks` with {got_families!r} families, "
                    f"registry has {families}"
                )

    assert matched, (
        "no document annotates `list-attacks` with a count any more. Either the phrasing changed "
        "— update the pattern — or the claims were deleted. A sweep that matches nothing passes "
        "vacuously, which is how the README line survived two releases."
    )
    assert not wrong, (
        "`list-attacks` prints the whole registry, so a count attached to it is a claim about the "
        "whole registry — not about a recipe's subset:\n  " + "\n  ".join(wrong)
    )


def test_the_list_attacks_sweep_catches_a_fenced_shell_comment() -> None:
    """Mutation guard: pin the exact shape that escaped, so a pattern edit cannot silently drop it.

    The regression was a shell comment inside a fenced code block. Asserting the pattern against a
    synthetic copy of that shape costs nothing and means a future rewrite of
    :data:`_LIST_ATTACKS_COUNT` has to keep working on the case it was written for, rather than
    merely on whatever the tree happens to contain that day.
    """
    stale_fence = (
        "```bash\n"
        "uv run provael list-attacks             # 28 attacks across 15 families: instruction/visual\n"
        "```\n"
    )
    found = _LIST_ATTACKS_COUNT.findall(stale_fence)
    assert found, "the sweep no longer matches a count in a fenced shell comment"
    got_attacks, got_families = found[0]
    assert _as_int(got_attacks) == 28 and _as_int(got_families) == 15, (
        "the sweep matched but captured the wrong tokens; it would report a misleading number"
    )
    # …and the same shape carrying today's registry counts must be accepted.
    live = stale_fence.replace("28 attacks", f"{_registry_counts()['total attacks']} attacks").replace(
        "15 families", f"{_registry_counts()['total families']} families"
    )
    got_attacks, got_families = _LIST_ATTACKS_COUNT.findall(live)[0]
    assert _as_int(got_attacks) == _registry_counts()["total attacks"]
    assert _as_int(got_families) == _registry_counts()["total families"]
