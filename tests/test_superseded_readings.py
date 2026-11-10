# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""A reading an erratum withdrew must not come back as a current claim.

An erratum records a correction once. The files it corrected are many, and on 31 October 2026 two
of them still asserted the old reading in the present tense, weeks after the errata page had
withdrawn it: `results/smolvla_libero_object_control/README.md` said "The 88% measures attacker
control", and the same file said "the seed fixes the environment's initial state".

The list is short on purpose. It names exact phrasings, because a broad word list would flag the
sentences that are meant to stay: `src/provael/attacks/controls.py` describes "an attacker
redirected the policy" as the hypothesis its controls test, and the README says "not attacker
control". Add a phrase when an erratum withdraws one.

A paragraph that cites the erratum may quote the old words, because that is how a dated correction
says what used to be claimed. `docs/errata.md` and `CHANGELOG.md` record the past by design.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

#: The withdrawn phrase, lower case, and the erratum that withdrew it.
SUPERSEDED = {
    "measures attacker control": "E-2026-12",
    "the seed fixes the environment's initial state": "E-2026-19",
}
EXEMPT = {"docs/errata.md", "CHANGELOG.md"}


def _offenders(text: str) -> list[str]:
    """The withdrawn phrases this text asserts, read across line wraps, paragraph by paragraph."""
    found = []
    for paragraph in re.split(r"\n\s*\n", text):
        flat = " ".join(line.lstrip("> #*").strip() for line in paragraph.splitlines()).lower()
        for phrase, erratum in SUPERSEDED.items():
            if phrase in flat and erratum.lower() not in flat:
                found.append(phrase)
    return found


def _tracked() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.md", "src/*.py", "src/**/*.py"],
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout
    return sorted({p for p in out.split("\0") if p} - EXEMPT)


def test_the_scan_has_files_to_read() -> None:
    assert len(_tracked()) > 100
    assert "README.md" in _tracked()
    assert "src/provael/suites/libero.py" in _tracked()


def test_no_tracked_file_asserts_a_withdrawn_reading() -> None:
    problems = [
        f"{path}: {phrase!r} (withdrawn by {SUPERSEDED[phrase]})"
        for path in _tracked()
        for phrase in _offenders((REPO / path).read_text(encoding="utf-8"))
    ]
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize(
    "old",
    [
        "attack separates on 43 pairs. The 88%\nmeasures attacker control.\n",
        "SmolVLA samples actions; the seed fixes\nthe environment's initial state, not the rollout.",
    ],
)
def test_the_guard_catches_the_old_text_across_a_line_wrap(old: str) -> None:
    assert _offenders(old)


def test_a_dated_correction_may_quote_what_used_to_be_claimed() -> None:
    assert not _offenders('> It used to say "the seed fixes the environment\'s initial\n> state" (E-2026-19).')


def test_the_sentences_meant_to_stay_are_not_flagged() -> None:
    assert not _offenders("so this is fragility under an instruction, not attacker control.")
    assert not _offenders("the hypothesis that an attacker redirected the policy")
