"""One guard against publishing a confidence interval that carries no information.

THE DRIFT THIS EXISTS TO STOP. `README.md` published `[0%, 0%]` as the task-clustered 95% interval
for `patch`, `decoy_object` and `scene_text` — three arms that scored 0/50 — while the website
published a non-zero upper bound for those same three results. Two public surfaces, one dataset,
contradictory claims. Nothing caught it for months.

`cluster_bootstrap_ci` was not careless; it was guarded on a proxy. It refuses to answer below two
tasks, precisely because "a bootstrap over one task resamples the same thing every time and returns
a zero-width interval — a confident-looking number carrying no information, which is worse than
declining to answer". That reasoning is exactly right and the guard implementing it counted
clusters. Ten tasks that all score zero pass a cluster count and are just as degenerate: every draw
returns the same rate, so the percentiles collapse onto it. The function now declines on the
interval it computed rather than on the shape of its input, and `tests/test_paired.py` pins that.

WHY A SECOND, DOCUMENT-LEVEL GUARD. The unit test proves the function cannot emit a zero width. It
cannot prove a document does not contain one. This table is hand-maintained — `cluster_bootstrap_ci`
has no caller in `src/`, so no regeneration step would ever have corrected the published number, and
the original `[0%, 0%]` outlived the code that produced it. A number transcribed by hand needs a
guard that reads what was published, not what the library would return if asked.

SCOPE, DELIBERATELY. Only markdown TABLE ROWS are checked. Prose may legitimately discuss a
zero-width interval — the README now explains the correction and quotes the old `[0%, 0%]` to say
what it replaced, and a guard that failed on that would punish the disclosure. Claims live in the
table; the surrounding text is where they get explained.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: A markdown table row publishing an interval whose bounds are identical: [0%, 0%], [100%, 100%].
#: The backreference is the whole point — [0%, 12%] is a real interval and must pass.
DEGENERATE_ROW = re.compile(r"^\|.*\[\s*([0-9]+(?:\.[0-9]+)?)\s*%\s*,\s*\1\s*%\s*\]")

#: A record of what shipped is not a claim about today — the same exemption
#: `test_counted_claims.py` grants for historical counts.
#:
#: `errata.md` is exempt for that reason and no other. Its whole purpose is to state, in a
#: "Superseded value" column, exactly what a past artifact published — E-2026-03 records this
#: very defect. Flagging it would make the guard punish the disclosure it exists to force,
#: which is the same reasoning the module docstring gives for scoping to table rows in the
#: first place. Both files are records; every other document is a claim.
EXEMPT = {"CHANGELOG.md", "errata.md"}


def _documents() -> list[Path]:
    return [
        p
        for p in REPO.rglob("*.md")
        if ".git" not in p.parts
        and "node_modules" not in p.parts
        and p.name not in EXEMPT
    ]


def test_no_document_publishes_a_zero_width_interval() -> None:
    offenders: list[str] = []
    for doc in _documents():
        for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if DEGENERATE_ROW.match(line.strip()):
                offenders.append(f"{doc.relative_to(REPO)}:{lineno}: {line.strip()[:100]}")

    assert not offenders, (
        "A confidence interval with identical bounds claims certainty the data does not support.\n"
        "0/50 is consistent with a true rate near 7%, so [0%, 0%] is not a narrow answer, it is a\n"
        "wrong one. Publish the exact binomial bound, or an em dash where the clustered bootstrap\n"
        "declines.\n  " + "\n  ".join(offenders)
    )


def test_the_guard_can_actually_fail() -> None:
    """A guard that matches nothing is indistinguishable from a guard that passed.

    This repo has been bitten by that twice — the vacuous dependency audit and the pin scan that
    found no pins — so the pattern is tested against the exact string that shipped.
    """
    shipped = "| visual | `patch` | 0/50 (0%) | [0%, 0%] | 0.5 | 1.0 |"
    assert DEGENERATE_ROW.match(shipped), "the regression this guard exists for must match"

    real = "| instruction | `paraphrase` | 3/50 (6%) | [0%, 12%] | 1.0 | 1.0 |"
    assert not DEGENERATE_ROW.match(real), "a genuine interval must not be flagged"

    prose = "previously published `[0%, 0%]` for them. The clustered bootstrap declines when"
    assert not DEGENERATE_ROW.match(prose), "prose explaining the correction must not be flagged"
