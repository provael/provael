"""Instruction canonicalization — the first measured defense in this repo's own sequence.

Implements the three numbered steps written at ``docs/defenses.md``:

1. **Normalise phrasing** — lowercase / whitespace / punctuation normalisation and paraphrase
   folding.
2. **Strip manner/urgency adverbials** — remove redundant "quickly / carefully / no matter what"-
   style modifiers that carry no task content but steer behaviour.
3. **Re-derive the canonical command** — reduce to the operator's intended verb + object,
   discarding the residual the search exploits.

Pure stdlib, deterministic, no model and no network — it adds no runtime dependency, so it stays
installable in the CPU-only core alongside the rest of the free tool.

A NOTE ON WHAT THIS RESULT CAN AND CANNOT MEAN
----------------------------------------------
:data:`MANNER_URGENCY_ADVERBIALS` and :data:`PARAPHRASE_FRAMES` overlap with the edit space
``provael.attacks.targeted_redirect`` searches, because both are drawn from the same natural class:
benign manner/urgency adverbials and polite reframings. That overlap is **not** hidden and it
bounds the claim. A defense whose word list is the attack's answer key would score well by
construction and generalise to nothing.

Two things keep this honest rather than circular, and both are stated again in the study:

* the list is written from the *general* class named in ``docs/defenses.md`` (and includes entries
  the attack never emits, e.g. ``"no matter what"``, ``"asap"``, ``"at once"``), not copied from
  ``targeted_redirect._CUES``; and
* the measurement is reported against the ``instruction`` family as a **reference arm** as well, a
  family whose attack templates this defense was not written around.

Even so: a lexical canonicaliser measured against a lexical search on a CPU fixture is
``stub-validated-scaffolding``. It is evidence that the pipeline position and the measurement
protocol work end to end. It is **not** evidence that this defends a real policy, and no real-model
transfer is claimed for it.
"""

from __future__ import annotations

import re

from provael.defenses.base import Defense
from provael.types import Observation

#: Manner / urgency adverbials stripped by step 2, longest-first at match time.
#:
#: A MODULE-LEVEL, REVIEWABLE CONSTANT ON PURPOSE. A certifier reading a mitigation report needs to
#: see exactly which words the defense removes; a regex buried in a function body is not reviewable
#: evidence. Every entry here carries manner or urgency and no task content — removing it must not
#: change *what* the operator asked for, only *how insistently* it was phrased. Anything that could
#: name or qualify a target object belongs nowhere near this list.
MANNER_URGENCY_ADVERBIALS: tuple[str, ...] = (
    # urgency
    "right away",
    "at once",
    "no matter what",
    "as fast as possible",
    "as soon as possible",
    "immediately",
    "instantly",
    "urgently",
    "asap",
    "now",
    "quickly",
    "fast",
    "hurry",
    # manner
    "carefully",
    "quietly",
    "gently",
    "slowly",
    "silently",
    "smoothly",
    "discreetly",
    # emphasis with no task content
    "please",
    "just",
    "simply",
    "really",
)

#: Paraphrase frames folded by step 1. These are *wrappers* around a command that leave the command
#: intact — ``targeted_redirect``'s ``sequence`` and ``polite`` operators are two of them — so
#: folding them is normalisation, not deletion.
PARAPHRASE_FRAMES: tuple[str, ...] = (
    "first of all",
    "to begin with",
    "could you please",
    "can you please",
    "i would like you to",
    "i want you to",
    "you may now",
    "go ahead and",
    "make sure you",
    "be sure to",
    "could you",
    "can you",
    "kindly",
    "please",
    "first",
    "then",
    "next",
)

#: Trailing filler clauses that carry no task content (the residual a search appends).
_TRAILING_FILLER: tuple[str, ...] = (
    "if you can",
    "if possible",
    "when you can",
    "for me",
    "ok",
    "okay",
    "thanks",
    "thank you",
)

_WORD = re.compile(r"[a-z0-9]+")
_PUNCT_RUN = re.compile(r"[^\w\s]+")
_WS = re.compile(r"\s+")


def _normalise(text: str) -> str:
    """Step 1a: lowercase, strip punctuation, collapse whitespace."""
    lowered = text.lower()
    depunctuated = _PUNCT_RUN.sub(" ", lowered)
    return _WS.sub(" ", depunctuated).strip()


def _phrase_pattern(phrases: tuple[str, ...]) -> re.Pattern[str]:
    """Whole-token alternation over ``phrases``, longest first.

    Longest-first matters: with ``now`` ahead of ``right away`` the multi-word phrase would never
    match as a unit. Sorting by length here means the constant above can stay in a human order
    (grouped by meaning) without the ordering silently changing behaviour.
    """
    ordered = sorted(phrases, key=len, reverse=True)
    alternation = "|".join(re.escape(p) for p in ordered)
    return re.compile(rf"(?<![a-z0-9])(?:{alternation})(?![a-z0-9])")


_ADVERBIAL_RE = _phrase_pattern(MANNER_URGENCY_ADVERBIALS)
_FRAME_RE = _phrase_pattern(PARAPHRASE_FRAMES)
_FILLER_RE = _phrase_pattern(_TRAILING_FILLER)


def _fold_frames(text: str) -> str:
    """Step 1b: strip paraphrase frames from the FRONT, repeatedly.

    Front-anchored on purpose. ``"first"`` and ``"then"`` are frames when they wrap a command and
    ordinary words when they sit inside one, and only the leading position is unambiguous. Removing
    them anywhere would let the defense edit the command itself, which is the one thing it must not
    do.
    """
    previous = None
    current = text
    while current != previous:
        previous = current
        stripped = _FRAME_RE.sub("", current, count=1) if _FRAME_RE.match(current) else current
        current = _WS.sub(" ", stripped).strip()
    return current


def _strip_adverbials(text: str) -> str:
    """Step 2: remove manner/urgency adverbials wherever they appear."""
    return _WS.sub(" ", _ADVERBIAL_RE.sub(" ", text)).strip()


def _rederive_command(text: str) -> str:
    """Step 3: reduce to the operator's verb + object.

    A deliberately LEXICAL reduction, not a parse: drop trailing filler, then re-emit the remaining
    tokens in order. Provael ships no parser and will not add a model dependency for one, and an
    honest lexical step whose limits are stated beats a clever one whose failures are invisible. The
    residual an appended-cue search relies on is lexical too, which is why this reaches it.
    """
    without_filler = _WS.sub(" ", _FILLER_RE.sub(" ", text)).strip()
    return " ".join(_WORD.findall(without_filler))


def canonicalize(instruction: str) -> str:
    """Run all three steps and return the canonical command."""
    return _rederive_command(_strip_adverbials(_fold_frames(_normalise(instruction))))


class InstructionCanonicalization(Defense):
    """Collapse the manner/urgency edit space before the instruction reaches the policy.

    The mitigation ``docs/defenses.md`` recommends for ``optimized_instruction``
    (``targeted_redirect``), which "redirects a policy through subtle manner/urgency cues while
    keeping the operator's command and never naming the target object".

    Touches the instruction channel only — the observation is passed through by identity, so any
    measured change is attributable to the instruction edit alone.
    """

    name = "instruction_canonicalization"
    kind = "input-canonicalization"
    #: Input-side only. It never sees the commanded action, so nothing it does can be confused with
    #: an output monitor when the mitigation report is read as conformity evidence.
    position = "input"
    eai_ids = ("EAI01", "EAI05", "EAI06")
    study = "docs/studies/instruction-canonicalization.md"

    def apply(self, instruction: str, observation: Observation) -> tuple[str, Observation]:
        """Return the canonicalised instruction and the observation unchanged."""
        return canonicalize(instruction), observation

    def audit(self, instruction: str) -> dict[str, str]:
        """Per-stage trail, so the sidecar shows WHICH step changed the instruction."""
        normalised = _normalise(instruction)
        folded = _fold_frames(normalised)
        stripped = _strip_adverbials(folded)
        canonical = _rederive_command(stripped)
        return {
            "raw": instruction,
            "normalised": normalised,
            "frames_folded": folded,
            "adverbials_stripped": stripped,
            "canonical": canonical,
        }


__all__ = [
    "MANNER_URGENCY_ADVERBIALS",
    "PARAPHRASE_FRAMES",
    "canonicalize",
    "InstructionCanonicalization",
]
