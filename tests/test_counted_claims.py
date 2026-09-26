# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""One guard for every prose claim that restates a number derived from the registry.

THE DRIFT THIS EXISTS TO STOP. `universal_patch` was registered in 0.29.0, taking the registry
from fourteen adversarial families to fifteen. The CHANGELOG entry for that very release said
"15 adversarial families (was 14)" — and `README.md`, `SAFETY.md` and `docs/roadmap.md` went on
saying **fourteen** for a whole release, because nothing imports prose and so nothing noticed.
`tests/test_recipes.py` already asserts that `full-sweep` covers every registry family; what it
could not see is that the documentation describing that sweep had fallen a family behind.

THE MIRROR OF IT. On 21 September 2026 the prose ran a release *ahead* instead. The day #278 (the
three-way calibration split) and #279 (the contact / force predicate) merged to `main`, six lines
in five files — `docs/roadmap.md` twice, `docs/glossary.md`, `docs/quickstart.md`,
`docs/attestation.md` and the module docstring of `suites/libero.py` — said both had shipped
"since 0.45" while `__version__` was 0.44.0 and both still sat under `[Unreleased]`. Four of those
pages publish from `main` to docs.provael.com/dev/. Nothing looked, because every guard here only
ever asked whether prose had fallen *behind*. `tests/test_roadmap_honesty.py` holds "shipped is not
called planned"; `test_no_doc_or_docstring_names_an_unreleased_version` below holds "unreleased is
not called released". They are the two directions of one error, not duplicates — delete neither.

AND THE SUMMARY. `CHANGELOG.md` opens with "Recent, in twenty lines", the block a reader arriving
today is told runs newest at the top. On 26 September 2026 its newest bullet was still 0.43.0, six
days after 0.44.0 was cut and headed in the same file.
`test_the_changelog_summary_names_the_newest_release` below closes it: unreleased is not called
released, and the summary names the newest release.

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
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pytest
from packaging.version import Version

from provael.attacks.baseline import FAMILY as BASELINE_FAMILY
from provael.attacks.registry import ATTACKS
from provael.coverage import NON_ADVERSARIAL_FAMILIES, coverage
from provael.suites import SUITES

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
        "suites": len(SUITES),
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
    # The coverage prose moved from README.md to docs/attacks.md on 20 September 2026, when the
    # README was cut to 200 lines; the sentences and their guards moved together.
    _Claim("docs/attacks.md", r"It ships \*\*(\w+) adversarial families", "adversarial families"),
    _Claim("docs/attacks.md", r"runs every one of the (\w+);", "adversarial families"),
    _Claim("SAFETY.md", r"registry ships \*\*(\w+) adversarial families\*\*", "adversarial families"),
    _Claim("docs/roadmap.md", r"\*\*Attacks:\*\* (\w+) adversarial families", "adversarial families"),
    _Claim("docs/index.md", r"all (\w+) adversarial families", "adversarial families"),
    _Claim("docs/quickstart.md", r"# (\w+) attacks across", "total attacks"),
    _Claim("docs/quickstart.md", r"attacks across (\w+) families", "total families"),
    _Claim("docs/quickstart.md", r"families \((\w+) adversarial", "adversarial families"),
    # README's `list-attacks` comment said "28 attacks" for two releases while
    # `docs/quickstart.md` — the same claim, one directory away — was corrected in 0.29.1,
    # because the enumerated list above only ever named quickstart. The README line itself left
    # with the 200-line cut (20 September 2026); quickstart's pair above is the surviving claim,
    # and the sweep below is the fix for the class of miss.
    # The leaderboard Space renders a coverage line but installs no `provael` (see its
    # requirements.txt), so it cannot import the registry and must hardcode the denominator.
    # That makes it exactly the kind of claim this guard exists for.
    _Claim("leaderboard/app.py", r"TOTAL_ADVERSARIAL_FAMILIES = (\d+)", "adversarial families"),
    # README's suite tally. It said **5** — the number of RUNNABLE suites — while `SUITES` held six
    # and `watch/registry.json` published 6, so the repo's own artifact contradicted its own README
    # in public. Anchored on this exact sentence rather than swept for, because "suite" is an
    # overloaded word here: LIBERO has ten task suites, VLA-Arena eleven benchmark suites, and a
    # sweep for "N suites" flags every one of them. A narrow guard that holds beats a broad one
    # that gets reverted.
    _Claim("docs/attacks.md", r"Suites: \*\*(\w+)\*\*", "suites"),
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
    "examples/recipes/core-sweep.yml",
    "src/provael/recipes.py",
    # Quotes the four disagreeing surfaces of its incident ("… across 15\nadversarial families")
    # verbatim in its docstring; the sweep reads across line breaks since 20 September 2026, which
    # is right for prose and wrong for a quotation of the numbers of that day.
    "scripts/gen_registry_artifact.py",
})

#: Any phrasing that states a family count. The count token must be digits or a number word this
#: guard knows — the first draft matched any `\w+` and flagged `compliance.py`'s "No EAI-tagged
#: adversarial families were run", which states no count at all. Building the alternation from
#: :data:`_WORDS` keeps the two in step: a stale count is always *some* number, so narrowing the
#: token to numbers loses no real claim while dropping the prose false positives.
#: ``\**`` between the number and the noun phrase: `examples/recipes/README.md` said "all **14**
#: adversarial families" for six releases past the count, because the bold markers sat between the
#: digits and the words this pattern keyed on (and the file was on the historical allow-list for a
#: different sentence). Emphasis is not a different claim.
_SWEEP = re.compile(
    r"\b(\d+|" + "|".join(_WORDS) + r")\**\s+adversarial families", re.IGNORECASE
)


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


# --------------------------------------------------------------------------- #
# THE SWEEP: every count claim, not only the ones somebody remembered to list
# --------------------------------------------------------------------------- #
#
# `_CLAIMS` above enumerates phrase patterns. That is useful and it is not sufficient, and the
# insufficiency shipped: while every `_CLAIMS` entry passed, `docs/attacks.md` opened with
# "**Fourteen** adversarial families" and `docs/examples.md` said "`full-sweep` runs all 14". Both
# were two releases stale and neither was in the list, so the suite was green and four published
# surfaces disagreed with each other. A test that checks the claims it was given, rather than the
# claims that exist, measures the list rather than the docs.
#
# This sweeps every `<number> … families` and `<number> … attacks` construction in README.md and
# docs/**/*.md and requires each to be either a registry-derived value or a NAMED subset.
#
# WHY A NAMED-SUBSET LIST AND NOT A SMARTER REGEX. Plenty of legitimate claims are about a subset:
# "four optimized search families", "3 of the 16 adversarial families", a historical changelog line
# reading "v0.1.0 — 3 attack families". No regex separates those from a stale total, because the
# difference is semantic. Naming them costs one line each and makes every future subset claim a
# decision somebody made rather than a pattern that happened to slip through.

#: Numbers a whole-registry claim is allowed to be, each derived.
def _derived_values() -> dict[int, str]:
    c = coverage()
    return {
        c.adversarial_families: "adversarial families",
        c.families_total: "total registered families (incl. baseline + control)",
        c.adversarial_attacks: "adversarial attacks",
        c.attacks_total: "total registered attacks (incl. baseline + controls)",
        len(c.stub_only_families): "families with no real-policy measurement",
        len(c.real_policy_families): "families measured against a real policy",
    }


#: `(file, exact matched text)` → why this number is not a whole-registry count.
_NAMED_SUBSETS: dict[tuple[str, str], str] = {
    # The phrases moved with their sections in the 20 September 2026 README cut: the coverage
    # prose to docs/attacks.md, the scope-and-limitations list to docs/index.md; the README keeps
    # one short limits list of its own.
    ("README.md", "four bounded search families"): "the optimized* subset, not the registry",
    ("docs/attacks.md", "four **optimized** search families"): (
        "the optimized* subset, not the registry"
    ),
    ("docs/index.md", "four optimized search families"): "the optimized* subset, not the registry",
    ("docs/index.md", "Four **optimized** families"): "the optimized* subset, not the registry",
    ("README.md", "3 attack families"): "a v0.1.0 changelog line; historical, must not be updated",
    ("docs/examples.md", "four core attack families"): "the core-sweep subset, not the registry",
    ("docs/findings/2026-instruction-transfer.md", "six attacks"): (
        "how many attacks THAT study screened at once, for the multiplicity correction"
    ),
    ("docs/findings/2026-instruction-transfer.md", "eight families"): (
        "how many families THAT run covered; a fact about the run, not the registry"
    ),
    ("docs/studies/eai04-action-space-transfer.md", "four EAI04 attacks"): (
        "the EAI04 subset, not the registry"
    ),
    ("docs/leaderboard.md", "**fourteen families"): (
        "how many of the 17 are absent from the published BOARD (17 - the 3 it covers); a fact "
        "about the board, not the registry's real-policy partition, which the same sentence now "
        "breaks down as nine unmeasured and five probed"
    ),
    ("docs/errata.md", "14 families"): (
        "E-2026-09/E-2026-10 state the real-policy partition as it stood on 13 Sep 2026 (3 measured, "
        "14 not); the 14 Sep breadth probe moved it to 8 and 9. An erratum's numbers are the numbers "
        "of its day"
    ),
    ("docs/errata.md", "three families"): (
        "E-2026-08 describes the keep-out face-selection study's own run (six attacks across three "
        "families on one task); a fact about that run, not the registry"
    ),
    ("docs/attacks.md", "Three sim-only attacks"): "the humanoid subset, not the registry",
    ("docs/studies/humanoid-locomotion-transfer.md", "three attacks"): (
        "the humanoid subset, not the registry"
    ),
    ("docs/studies/humanoid-locomotion-transfer.md", "three humanoid attacks"): (
        "the humanoid subset, not the registry"
    ),
    ("docs/crosswalk/foresight-safety-vla.md", "three families"): (
        "ForesightSafety-VLA's OWN taxonomy (Safe-Core, Safe-Lang, ...), not provael's registry"
    ),
    ("docs/errata.md", "16 families"): (
        "E-2026-09 quotes the superseded count the website published between 1 and 3 September "
        "2026; an erratum must name the wrong number to record it. Historical, must not be updated"
    ),
    ("docs/errata.md", "42 registered attacks"): (
        "E-2026-09/E-2026-10 state the registry as it stood on 13 Sep 2026 (42 attacks, before "
        "the scrambled_text and roleplay_no_target controls of 14 Sep); an erratum's numbers are "
        "the numbers of its day"
    ),
    ("docs/errata.md", "38 attacks"): (
        "E-2026-09 quotes the superseded count the website published between 1 and 3 September "
        "2026; an erratum must name the wrong number to record it. Historical, must not be updated"
    ),
    ("docs/errata.md", "six attacks"): (
        "how many attacks recorded a trajectory in ONE run — the 6 September canary, whose "
        "seventh arm (mcp_tool_desc) has no surface in a direct LIBERO loop and wrote none. A "
        "fact about that run's usable episodes, not about the registry"
    ),
}

#: Number words this project actually writes. Digits are matched separately.
_WORDS_RE = (
    "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
    "sixteen|seventeen|eighteen|nineteen|twenty"
)
#: `<number> <up to three words> (adversarial )?(families|attacks)`. Markdown emphasis is kept in
#: the captured text so a subset entry can name the exact string a reader sees.
#: `\**` around the NUMBER as well as the words after it. Without that, `**Fourteen** adversarial
#: families` — the exact string that shipped two releases stale on docs/attacks.md — does not match,
#: because the emphasis markers sit between the lookbehind and the digit. The first draft of this
#: regex had that hole and silently skipped the claim it was written to catch.
_COUNT_CLAIM = re.compile(
    rf"(?<![\w%])(\**(?:\d+|{_WORDS_RE})\**(?:\s+\**[\w-]+\**){{0,3}}?\s+(?:adversarial\s+)?"
    r"(?:attack\s+)?(?:families|attacks))\b",
    re.IGNORECASE,
)


def _sweep_files() -> list[Path]:
    root = Path(__file__).resolve().parent.parent
    return [root / "README.md", *sorted((root / "docs").rglob("*.md"))]


def test_every_count_claim_is_derived_or_a_named_subset() -> None:
    """No `<n> families` / `<n> attacks` claim may disagree with the registry.

    See the header above: the enumerated `_CLAIMS` list was green while four published surfaces
    disagreed, because it checked the claims it was handed rather than the claims that exist.
    """
    root = Path(__file__).resolve().parent.parent
    values = _derived_values()
    problems: list[str] = []

    for path in _sweep_files():
        rel = path.relative_to(root).as_posix()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for raw in _COUNT_CLAIM.findall(line):
                text = raw.strip()
                number = _as_int(re.split(r"\s+", text)[0].strip("*"))
                if number is None:
                    continue
                if (rel, text) in _NAMED_SUBSETS:
                    continue
                # "3 of the 16 adversarial families" — the scoped numerator is carried by the
                # denominator immediately after it, so only the denominator is a registry claim.
                if re.search(rf"{re.escape(text)}", line) and re.search(
                    rf"\b{number}\s+of\s+(?:the\s+)?\d+", line
                ):
                    continue
                if number in values:
                    continue
                problems.append(
                    f"{rel}:{lineno} — {text!r} is {number}, which is not any registry count "
                    f"({', '.join(f'{k} = {v}' for k, v in sorted(values.items()))}). "
                    f"Fix the number, or add it to _NAMED_SUBSETS with the subset it describes."
                )

    assert not problems, "stale or unexplained count claims:\n  " + "\n  ".join(problems)


# --------------------------------------------------------------------------- #
# the enumerations — the shape that got past every check above
# --------------------------------------------------------------------------- #

#: WHY A THIRD CLASS OF CHECK. Everything above guards a NUMBER. On 4 September 2026 every number
#: in this repo was right and three documents were still wrong, because what had drifted was the
#: LIST beside the number:
#:
#: * ``README.md`` annotated ``provael list-attacks`` with "42 attacks across 19 families:" and
#:   then enumerated **eighteen** of them. ``control`` had been missing since it was registered.
#:   :data:`_LIST_ATTACKS_COUNT` matched that very line, read "42" and "19", found both correct,
#:   and passed — it was never looking at the names.
#: * ``docs/quickstart.md`` said "19 families (17 adversarial + the benign baseline)". Both numbers
#:   correct; 17 + 1 = 18.
#: * ``README.md`` and ``docs/quickstart.md`` both said **5 suites** and enumerated the same five,
#:   while ``keepout_zones``… in fact while ``ai2_bridge`` had been registered as a sixth. The
#:   published ``watch/registry.json`` said 6 the whole time, so the artifact and the prose
#:   contradicted each other in public.
#:
#: A count and its enumeration are the same claim made twice. Guarding one of them is guarding
#: half a claim.
_FAMILY_TOKEN = r"[a-z][a-z0-9_]{2,}"  # noqa: S105 - a regex for family names, not a secret

#: A run of family names joined by ``/``. Five is the threshold and it is chosen, not arbitrary:
#: the largest legitimate PARTIAL enumeration in this repo is ``CORE_FAMILIES`` at four
#: (``recipes.py`` renders "nine attacks across four families"), so five or more slash-joined
#: registry names is a list that means to be complete. A lower threshold would flag real subsets
#: and the guard would be reverted inside a week, which is worse than no guard.
_SLASH_RUN = re.compile(rf"{_FAMILY_TOKEN}(?:/{_FAMILY_TOKEN})+")
_MIN_RUN = 5


def test_no_family_enumeration_is_missing_a_family() -> None:
    """A slash-joined list of five or more registry families must name all of them."""
    every = {ctor().family for ctor in ATTACKS.values()}
    offenders: list[str] = []
    checked = 0
    for path in _tracked_text_files():
        rel = path.relative_to(REPO).as_posix()
        if rel in _HISTORICAL or rel.startswith("tests/") or rel == "watch/registry.json":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for run in _SLASH_RUN.findall(text):
            names = run.split("/")
            hits = [name for name in names if name in every]
            # A run is an enumeration of families only if MOST of it is family names; otherwise it
            # is a path, a URL fragment, or an unrelated slash-joined list.
            if len(hits) < _MIN_RUN or len(hits) < len(names) - 1:
                continue
            checked += 1
            missing = sorted(every - set(hits))
            if missing:
                offenders.append(f"{rel}: names {len(hits)} of {len(every)}, missing {missing}")

    assert checked, (
        "the family-enumeration sweep matched no lists at all. Either the enumerations were "
        "removed or their formatting changed; a sweep that inspects nothing passes vacuously."
    )
    assert not offenders, (
        "family enumerations that do not name every registered family:\n  "
        + "\n  ".join(offenders)
        + "\n\n  These lines are generated. Run `python scripts/gen_doc_counts.py`."
    )


def test_the_generated_inventory_lines_are_regenerated() -> None:
    """`scripts/gen_doc_counts.py --check` must be clean, the way the registry artifact must be.

    Same posture as ``tests/test_registry_artifact_agrees.py``: the generator is only worth having
    if a stale output fails the build rather than waiting to be noticed.
    """
    import importlib.util  # noqa: PLC0415 - the idiom tests/test_check_changelog_entry.py uses

    spec = importlib.util.spec_from_file_location(
        "gen_doc_counts", REPO / "scripts" / "gen_doc_counts.py"
    )
    assert spec and spec.loader
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)

    assert gen.main(["--check"]) == 0, (
        "a generated inventory line is stale. Run `python scripts/gen_doc_counts.py` and commit "
        "the result; do not edit those lines by hand."
    )


# --------------------------------------------------------------------------- #
# the other direction — prose naming a release that does not exist yet
# --------------------------------------------------------------------------- #

#: Files that may name a version above the current one, exempt by path and each for a reason:
#:
#: * ``CHANGELOG.md`` — ``[Unreleased]`` is written ahead of the cut that ships it. A changelog that
#:   could not name a version above the current one could never be written before its release.
#: * ``docs/errata.md`` — an erratum quotes the past, including a version as it was wrongly printed.
_UNRELEASED_EXEMPT = frozenset({"CHANGELOG.md", "docs/errata.md"})

#: A version-introduction phrase: "since 0.45", "the default since 0.45", "as of 0.45",
#: "(…, in 0.45)", "in release 0.45". ``\s`` rather than a space throughout, because prose is
#: hard-wrapped and "since\n0.45" is the same claim. Two exclusions came from running the first
#: draft over the tree; the third is a precaution the fixtures below exercise:
#:
#: * ``removed in`` is a deprecation schedule, which names a future release on purpose —
#:   ``provael certify`` is "removed in 0.46.0". A promise about a release is not a claim it shipped.
#: * the major is capped at two digits, so an arXiv id ("in 2505.16640") is not read as a version;
#: * a unit after the number ("in 1.5 s") makes it a measurement.
_VERSION_INTRO = re.compile(
    r"(?<!removed\s)\b(?:since|as\s+of|in)\s+(?:(?:version|release)\s+)?v?"
    r"(\d{1,2}\.\d{1,3}(?:\.\d{1,3})?)(?![\d.]*\d)"
    r"(?!\s*(?:(?:s|ms|m|mm|cm|N|Hz|rad|deg|x|seconds?|minutes?|hours?)\b|%|°|×))",
    re.IGNORECASE,
)


def _ahead_of_release(root: Path, rels: Iterable[str], current: str) -> tuple[list[str], int]:
    """Every phrase in ``rels`` (under ``root``) naming a release after ``current``, and a count.

    Returns ``(offenders as "file:line: 'phrase'", version phrases seen in total)``; the count lets
    a caller prove the sweep looked at something. Versions are compared as
    :class:`packaging.version.Version`, never as strings: as text "0.10" sorts before "0.9", and a
    guard that read 0.10 as older than 0.9 would pass on exactly the day it was needed.
    """
    now = Version(current)
    offenders: list[str] = []
    seen = 0
    for rel in rels:
        if rel in _UNRELEASED_EXEMPT:
            continue
        text = (root / rel).read_text(encoding="utf-8")
        for match in _VERSION_INTRO.finditer(text):
            seen += 1
            if Version(match.group(1)) > now:
                line = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{rel}:{line}: {' '.join(match.group(0).split())!r}")
    return offenders, seen


def _docs_and_src_modules() -> list[str]:
    """Every tracked Markdown document, and every module under ``src/`` — docstrings ship in the
    wheel, so a module that says "since 0.45" publishes it as surely as a docs page does."""
    rels = [path.relative_to(REPO).as_posix() for path in _tracked_text_files()]
    return [r for r in rels if r.endswith(".md") or (r.startswith("src/") and r.endswith(".py"))]


def test_no_doc_or_docstring_names_an_unreleased_version() -> None:
    """Unreleased is not called released — the mirror of the universal_patch story in the header."""
    from provael import __version__

    ahead, seen = _ahead_of_release(REPO, _docs_and_src_modules(), __version__)
    assert seen, "no version phrase matched anywhere; the pattern must have stopped matching"
    assert not ahead, (
        f"prose names a release after {__version__}, which does not exist yet. Say what is true "
        f'("on main since <date>, not yet in a release") and name the version once it is cut:\n  '
        + "\n  ".join(ahead)
    )


def test_the_unreleased_guard_fails_on_a_release_that_does_not_exist(tmp_path: Path) -> None:
    """A guard nobody has seen fail is not a guard: the shape that shipped must go red."""
    (tmp_path / "doc.md").write_text("the column exists since 0.45 (`ContactRule`)\n", encoding="utf-8")
    assert _ahead_of_release(tmp_path, ["doc.md"], "0.44.0")[0] == ["doc.md:1: 'since 0.45'"]
    # Hard-wrapped, and past the point where string comparison gets it backwards.
    (tmp_path / "wrapped.md").write_text("a fit (the default since\n0.10) scores the eval split\n", encoding="utf-8")
    assert _ahead_of_release(tmp_path, ["wrapped.md"], "0.9.0")[0] == [
        "wrapped.md:1: 'since 0.10'"
    ]


def test_the_unreleased_guard_allows_honest_history(tmp_path: Path) -> None:
    """…and it must not forbid the past, a deprecation schedule, or a number that is no version."""
    (tmp_path / "doc.md").write_text(
        "the column exists since 0.44 (`ContactRule`)\n"
        "`certify` is a deprecated alias (removed in 0.46.0)\n"
        "as reported in 2505.16640, the force settles in 1.5 s\n",
        encoding="utf-8",
    )
    (tmp_path / "CHANGELOG.md").write_text("## [Unreleased]\n- lands in 0.45\n", encoding="utf-8")
    ahead, seen = _ahead_of_release(tmp_path, ["doc.md", "CHANGELOG.md"], "0.44.0")
    assert ahead == []
    assert seen == 1, "the honest 'since 0.44' must still be SEEN, or this passes by not looking"


# --------------------------------------------------------------------------- #
# the summary — "Recent, in twenty lines" names the newest release
# --------------------------------------------------------------------------- #


def _newest_release(changelog: str) -> str | None:
    """The version of the first released ``## [x.y.z]`` heading; ``[Unreleased]`` is not one."""
    m = re.search(r"^## \[(\d+\.\d+\.\d+)\]", changelog, re.MULTILINE)
    return m.group(1) if m else None


def _recent_names(changelog: str, version: str) -> bool:
    """Whether a bullet's bold lead in the "Recent" block (the text above the first ``## [``
    heading) names ``version``. "0.42.1 / 0.42.0 (…)" names both."""
    start = changelog.find("**Recent, in")
    assert start != -1, "CHANGELOG.md has no '**Recent, in …**' summary; this test reads it"
    end = changelog.find("\n## [", start)
    block = changelog[start : end if end != -1 else len(changelog)]
    leads = re.finditer(r"^- \*\*([^*]+)\*\*", block, re.MULTILINE)
    return any(version in lead.group(1) for lead in leads)


def test_the_changelog_summary_names_the_newest_release() -> None:
    """The summary a reader arriving today is sent to lists the newest release."""
    text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    newest = _newest_release(text)
    assert newest, "no released '## [x.y.z]' heading in CHANGELOG.md"
    assert _recent_names(text, newest), (
        f"CHANGELOG.md's 'Recent' summary has no bullet for {newest}, the newest release heading in "
        "the same file. Add one written from that section's own text (what changed and why, no new "
        "figure), and fold the oldest bullet so the block keeps its stated size."
    )


def test_the_summary_guard_fails_when_the_newest_release_is_missing() -> None:
    """The shape that stood for six days must go red: a release cut and headed, not summarised."""
    changelog = (
        "**Recent, in twenty lines.** Newest at the top.\n\n"
        "- **0.44.0 (20 Sep 2026)** — the previous release.\n\n"
        "## [Unreleased]\n\n## [0.45.0] — 2026-10-01\n\n## [0.44.0] — 2026-09-20\n"
    )
    assert _newest_release(changelog) == "0.45.0"
    assert not _recent_names(changelog, "0.45.0")
    assert _recent_names(changelog, "0.44.0")
