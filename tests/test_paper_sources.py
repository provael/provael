# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Every fraction in the SPAIS draft comes from a committed results README.

WHY. ``paper/spais/paper.tex`` opens with a promise: every number is "copied from a committed
results directory's generated README/aggregate", and "Nothing is typed from memory." Until
26 September 2026 that sentence was the only thing holding it. A four-page paper written against a
deadline is where a figure gets retyped from a slide or an older draft, and a double-blind reviewer
cannot even see which directory to check: the paths live in a comment the PDF never shows.

WHAT THIS HOLDS. (1) Every ``results/.../README.md`` the ``% Sources`` block names exists, with the
block's brace form (``results/smolvla_libero_{spatial,goal,10}_2026-09-14/README.md``) expanded.
(2) Every fraction in the document body occurs in at least one of those READMEs: ``42/50``, and also
``42 of 50`` and ``1 in 50``, because the abstract states its headline figures in prose and a check
that read only the slash form would have left exactly those unguarded.

THE ONE EXCEPTION. The paper quotes an earlier campaign on purpose (the August comparison, the
reading an erratum withdrew), and such a figure can live in ``docs/errata.md`` rather than in a
September README. A fraction found only there passes when its own sentence says so ("earlier",
"August", "corrected", "erratum"). The rule reads the sentence, never a list of numbers: a free-text
allowlist is where a mistyped figure would go to be forgiven.

WHAT THIS CANNOT CATCH. A number that is not a fraction (a percentage, an interval bound, a count
without its denominator) is not checked, and a fraction a README carries with another meaning
passes. It proves where the string came from, not that the sentence around it reads it correctly.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAPER = ROOT / "paper" / "spais" / "paper.tex"

#: A fraction ends where no digit or slash follows. A full stop only ends a sentence when no digit
#: follows it, so "27 of 30." is the fraction 27/30 and "0.5" is not a fraction ending in "0".
_END = r"(?![\d/])(?!\.\d)"
_START = r"(?<![\d./])"
_FRACTION = re.compile(rf"{_START}(\d+)\s*/\s*(\d+){_END}|{_START}(\d+)\s+(?:of|in)\s+(\d+){_END}")

#: Words by which a sentence says it is quoting the past on purpose.
_HISTORY_WORDS = re.compile(r"\b(?:earlier|August|corrected|erratum)\b", re.IGNORECASE)

#: A sentence ends at terminal punctuation followed by a capital or a macro, or at a blank line.
#: A version such as 0.32.0 never ends one: its dots are followed by digits, not whitespace.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z\\])|\n\s*\n")

_SOURCE_PATH = re.compile(r"results/\S*README\.md")


def _expand(path: str) -> list[str]:
    """``a_{x,y}_b`` → ``[a_x_b, a_y_b]``, recursively for more than one brace group."""
    m = re.search(r"\{([^{}]*)\}", path)
    if m is None:
        return [path]
    return [
        out
        for part in m.group(1).split(",")
        for out in _expand(path[: m.start()] + part.strip() + path[m.end() :])
    ]


def _sources(tex: str) -> list[str]:
    """The README paths the ``% Sources`` comment block names, brace forms expanded."""
    lines = tex.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("% Sources")), None)
    assert start is not None, "paper.tex has no '% Sources' comment block; this test reads it"
    paths: list[str] = []
    for line in lines[start:]:
        if not line.startswith("%"):
            break
        for token in _SOURCE_PATH.findall(line):
            paths.extend(_expand(token))
    return paths


def _missing_sources(tex: str, root: Path) -> list[str]:
    return [p for p in _sources(tex) if not (root / p).is_file()]


def _carries(text: str, k: str, n: str) -> bool:
    """Whether ``text`` states k/n, in either spelling this file checks."""
    return bool(
        re.search(rf"{_START}{k}\s*/\s*{n}{_END}", text)
        or re.search(rf"{_START}{k}\s+(?:of|in)\s+{n}{_END}", text)
    )


def _unsourced(tex: str, root: Path) -> tuple[list[str], int]:
    """Every body fraction no source README carries, as ``"L<line> k/n: sentence"``, and how many
    fractions were seen in total, so a caller can prove the sweep looked at something."""
    readmes = [root / p for p in _sources(tex)]
    corpus = "\n".join(p.read_text(encoding="utf-8") for p in readmes if p.is_file())
    errata_path = root / "docs" / "errata.md"
    errata = errata_path.read_text(encoding="utf-8") if errata_path.is_file() else ""
    # Comments out, line structure kept, so an offset still maps to the file's own line number.
    # `\%` is a percent sign in LaTeX, not a comment.
    body = "\n".join(re.split(r"(?<!\\)%", line, maxsplit=1)[0] for line in tex.splitlines())
    begin, end = body.find(r"\begin{document}"), body.find(r"\end{document}")
    assert begin != -1 and end != -1, "no \\begin{document}...\\end{document} in the paper"
    begin += len(r"\begin{document}")
    offenders: list[str] = []
    seen = 0
    for m in _FRACTION.finditer(body, begin, end):
        seen += 1
        k, n = (m.group(1), m.group(2)) if m.group(1) is not None else (m.group(3), m.group(4))
        if _carries(corpus, k, n):
            continue
        left = begin
        for boundary in _SENTENCE_END.finditer(body, begin, m.start()):
            left = boundary.end()
        after = _SENTENCE_END.search(body, m.end(), end)
        sentence = " ".join(body[left : after.start() if after else end].split())
        # A figure from an earlier campaign may come from the errata log, but only in a sentence
        # that says it is quoting the past. See the module docstring.
        if _carries(errata, k, n) and _HISTORY_WORDS.search(sentence):
            continue
        line = body.count("\n", 0, m.start()) + 1
        offenders.append(f"L{line} {k}/{n}: {sentence[:160]}")
    return offenders, seen


def test_every_source_the_paper_names_exists() -> None:
    tex = PAPER.read_text(encoding="utf-8")
    assert _sources(tex), (
        "the '% Sources' block names no results/.../README.md; the sweep would check nothing"
    )
    missing = _missing_sources(tex, ROOT)
    assert not missing, (
        "paper.tex's '% Sources' block names a results README that does not exist (renamed "
        "or never committed):\n  " + "\n  ".join(missing)
    )


def test_every_fraction_in_the_paper_comes_from_a_source() -> None:
    offenders, seen = _unsourced(PAPER.read_text(encoding="utf-8"), ROOT)
    assert seen, "no fraction matched in the paper body; the pattern must have stopped matching"
    assert not offenders, (
        "a fraction in the SPAIS draft occurs in none of the results READMEs its '% Sources' block "
        "names (and is not an errata figure in a sentence that says it quotes the past). Copy it "
        "from the generated README, or name the directory it came from:\n  "
        + "\n  ".join(offenders)
    )


def _fixture(sources: str, body: str) -> str:
    """A four-line paper: Sources header, one source line, then a one-line body on line 4."""
    head = "% Sources (repo-relative, not in the PDF):"
    return f"{head}\n{sources}\n\\begin{{document}}\n{body}\n\\end{{document}}\n"


def test_a_numerator_off_by_one_fails(tmp_path: Path) -> None:
    """A guard nobody has seen fail is not a guard: the typed-from-memory shape must go red."""
    run = tmp_path / "results" / "run_2026-09-14"
    run.mkdir(parents=True)
    (run / "README.md").write_text("| roleplay | 42/50 |\n", encoding="utf-8")
    sources = "%   T1  results/run_2026-09-14/README.md"
    ok = "The attack succeeds in 42 of 50 episodes."
    right, seen = _unsourced(_fixture(sources, ok), tmp_path)
    assert right == [] and seen == 1
    wrong, _ = _unsourced(_fixture(sources, "The attack succeeds in 43 of 50 episodes."), tmp_path)
    assert wrong == ["L4 43/50: The attack succeeds in 43 of 50 episodes."]


def test_a_source_that_does_not_exist_fails(tmp_path: Path) -> None:
    (tmp_path / "results" / "run_a").mkdir(parents=True)
    (tmp_path / "results" / "run_a" / "README.md").write_text("1/2\n", encoding="utf-8")
    tex = _fixture("%       results/run_{a,b}/README.md", "One in two: 1/2.")
    assert _sources(tex) == ["results/run_a/README.md", "results/run_b/README.md"]
    assert _missing_sources(tex, tmp_path) == ["results/run_b/README.md"]


def test_the_errata_exception_reads_the_sentence(tmp_path: Path) -> None:
    """An errata-only figure passes when its sentence quotes the past, and fails otherwise."""
    (tmp_path / "results" / "run").mkdir(parents=True)
    (tmp_path / "results" / "run" / "README.md").write_text("42/50\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "errata.md").write_text("The August run read 44/50.\n", encoding="utf-8")
    sources = "%   results/run/README.md"
    quoted, _ = _unsourced(_fixture(sources, "Our earlier report read 44/50 as control."), tmp_path)
    assert quoted == []
    asserted, _ = _unsourced(_fixture(sources, "The attack succeeds in 44/50 episodes."), tmp_path)
    assert asserted == ["L4 44/50: The attack succeeds in 44/50 episodes."]
