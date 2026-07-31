"""One guard: every evidence citation in the Top 10 must name a source a reader can go find.

THE DRIFT THIS EXISTS TO STOP. In July 2026 an independent audit fact-checked this repo's
citation corpus with a fleet of research agents. It came back clean on almost everything —
roughly fifteen papers and four CVEs, all real, all correctly attributed, zero fabricated or
transposed identifiers, including every 2026-dated arXiv ID. It flagged exactly two citations as
unverifiable and told the founder to "verify or soften both before any deck":

  * EAI09's "cited at the U.S. Senate" — the audit found only a *House* committee reference and
    concluded the chamber was wrong.
  * EAI10's a16z "The Physical AI Deployment Gap" — "no independent trace found".

Both are true. The Senate one is written testimony to the Commerce Subcommittee on Science,
Manufacturing, and Competitiveness, hearing of 3 Mar 2026, hosted on commerce.senate.gov — a
*different, also-real* event from the House hearing the audit surfaced. The a16z piece is by
Oliver Hsu, published 13 Jan 2026, and the quoted sentence is verbatim.

So the audit was wrong twice — and it was wrong for a reason worth encoding. Look at what
separated the citations it verified from the two it did not: **every citation it confirmed
carried an arXiv ID or a CVE number. The two it failed on carried neither.** It was not
checking harder on the ones it got right; it simply had something to resolve. A named document
with no identifier is not a weaker citation, it is an *unresolvable* one, and a diligent third
party who cannot resolve it does not record "unverified" — they record "probably made up", and
then they discount the ninety-odd citations that were fine.

That is the whole product thesis turned back on its own documentation. Provael's pitch is that a
defence is a number you can re-derive, not a press release; a taxonomy whose evidence a reader
cannot check is exactly the press release it exists to argue against. The cost of getting this
wrong is asymmetric and it is not hypothetical — it already cost this repo two false accusations
of fabrication in a document written for an investor.

WHAT THIS CHECKS, AND WHAT IT DELIBERATELY DOES NOT. It asserts that every tagged evidence
segment carries at least one *globally resolvable* identifier — an arXiv ID, a CVE number, or a
URL. It does **not** dereference them: CI here is hermetic and offline by design (no network, CPU
only), and a link-liveness check belongs in a scheduled job, not in the gate that runs on every
push. The invariant is "a reader can check this", not "this checked out today".

The vacuity guard matters as much as the rule. A regex that silently matches nothing is the
failure mode this repo has been bitten by twice already (the vacuous dependency audit, the pin
scan that found no pins), so the parser's own yield is asserted against the risk headings: ten
`## EAIxx` headings must produce ten evidence blocks, and every heading must be accounted for.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

_TOP10 = Path(__file__).resolve().parents[1] / "docs" / "TOP10.md"

# `## EAI01 — Policy & instruction jailbreak (direct command channel)`
_RISK_HEADING = re.compile(r"^## (EAI\d\d) — .*$", re.M)

# The `**Evidence.**` paragraph runs until the next bold lead-in (`**Why it matters.**`,
# `**Mitigations.**`, ...) or the end of the section.
_EVIDENCE = re.compile(r"^\*\*Evidence\.\*\*(.*?)(?=^\*\*[A-Z]|\Z)", re.S | re.M)

# Evidence is tagged by provenance class. Each tag opens a segment that makes its own claim, so
# each is checked on its own rather than letting one arXiv ID vouch for the whole paragraph.
_TAG = re.compile(r"\*\[(research|incident|emerging|framework)\]\*")

# What counts as resolvable: something a reader can paste into a browser or an arXiv/CVE lookup
# and land on the source. Deliberately narrow — "ICLR 2025" or "a16z's blog" is a description of
# a source, not a handle for one.
_RESOLVABLE = (
    re.compile(r"\barXiv[: ]\s?\d{4}\.\d{4,5}\b", re.IGNORECASE),
    re.compile(r"\bCVE-\d{4}-\d{4,}\b"),
    re.compile(r"https?://[^\s<>)\]]+"),
)


@dataclass(frozen=True)
class _Segment:
    risk: str
    tag: str
    text: str


def _segments() -> list[_Segment]:
    """Every tagged evidence segment in the Top 10, in document order."""
    doc = _TOP10.read_text(encoding="utf-8")
    headings = _RISK_HEADING.findall(doc)
    # Slice the document into one section per risk so a segment can be blamed on its EAI id.
    bounds = [m.start() for m in _RISK_HEADING.finditer(doc)] + [len(doc)]
    out: list[_Segment] = []
    for risk, start, end in zip(headings, bounds[:-1], bounds[1:], strict=True):
        for block in _EVIDENCE.findall(doc[start:end]):
            flat = " ".join(block.split())
            parts = _TAG.split(flat)
            # _TAG.split gives [pre, tag, body, tag, body, ...]; the pre-text is prose, not a claim.
            for tag, body in zip(parts[1::2], parts[2::2], strict=True):
                out.append(_Segment(risk=risk, tag=tag, text=body.strip()))
    return out


def test_every_evidence_citation_carries_a_resolvable_identifier() -> None:
    """An evidence claim a reader cannot resolve reads as a fabricated one. See module docstring."""
    unresolvable = [
        s for s in _segments() if not any(pattern.search(s.text) for pattern in _RESOLVABLE)
    ]
    if unresolvable:
        detail = "\n".join(f"  {s.risk} *[{s.tag}]* {s.text[:160]}" for s in unresolvable)
        pytest.fail(
            f"{len(unresolvable)} evidence citation(s) in docs/TOP10.md name a source with no "
            f"arXiv ID, CVE number, or URL — a reader cannot check them, and an auditor who "
            f"cannot check a citation records it as fabricated rather than as unverified:\n"
            f"{detail}\n\n"
            f"Add the identifier (e.g. `arXiv 2410.13691`, `CVE-2025-60250`, or a URL). Do not "
            f"delete the claim to silence this — an unresolvable citation is a sourcing bug, not "
            f"a reason to drop the evidence."
        )


def test_the_parser_sees_every_risk() -> None:
    """Vacuity guard: a citation rule that matches nothing is worse than no rule at all."""
    doc = _TOP10.read_text(encoding="utf-8")
    headings = _RISK_HEADING.findall(doc)
    segments = _segments()
    covered = {s.risk for s in segments}

    assert len(headings) == 10, f"expected the Top 10 to have ten `## EAIxx` headings, got {headings}"
    assert len(headings) == len(set(headings)), f"duplicate risk heading in TOP10.md: {headings}"
    assert covered == set(headings), (
        "the evidence parser found no citation for "
        f"{sorted(set(headings) - covered)} — either a risk lost its `**Evidence.**` paragraph or "
        "the paragraph was reworded so the parser stopped matching it. Both are failures."
    )
    assert len(segments) >= len(headings), (
        f"parsed only {len(segments)} evidence segments for {len(headings)} risks — the `*[tag]*` "
        "convention was probably reworded, which would make the citation check vacuous."
    )


def test_the_two_citations_an_external_audit_could_not_verify_stay_pinned() -> None:
    """Regression pin on the exact two claims that were read as fabricated once already.

    These have history, so the general rule above is not enough: both would still pass it on the
    strength of a *neighbouring* identifier in the same segment. The specific thing that has to
    survive is the attribution detail that makes each one findable in the first place.
    """
    doc = _TOP10.read_text(encoding="utf-8")

    # EAI09 — the chamber, the subcommittee, and the hearing date, so nobody lands on the House
    # hearing on the same subject and concludes the chamber is wrong (which is what happened).
    for fragment in ("U.S. Senate", "Science, Manufacturing, and Competitiveness", "3 Mar 2026"):
        assert fragment in doc, (
            f"docs/TOP10.md no longer names {fragment!r} for the Unitree G1 Senate citation. An "
            "external audit already mistook this claim for a fabrication when it read only "
            '"cited at the U.S. Senate" — the hearing has to stay identifiable.'
        )

    # EAI10 — author, date, and URL, because "a16z's 'The Physical AI Deployment Gap'" alone was
    # returned as "no independent trace found".
    for fragment in ("Oliver Hsu", "13 Jan 2026", "a16z.news/p/the-physical-ai-deployment-gap"):
        assert fragment in doc, (
            f"docs/TOP10.md no longer names {fragment!r} for the a16z deployment-gap citation, "
            "which an external audit previously could not trace at all."
        )
