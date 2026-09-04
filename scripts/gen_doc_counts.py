"""Write the inventory lines in the docs from the registries, so no human types them.

WHY THIS EXISTS, AND WHY GUARDING THE NUMBER WAS NOT ENOUGH. ``tests/test_counted_claims.py``
already checks that every restated count matches the registry, and it works — no count in this
repo has been wrong since it landed. What it cannot see is the LIST beside the count, because a
list is not a number and no pattern was looking at it:

* ``README.md`` annotated ``provael list-attacks`` with "42 attacks across 19 families:" followed
  by an enumeration of **eighteen** family names. The 19 was checked and correct; the enumeration
  had been missing ``control`` since that family was registered.
* ``docs/quickstart.md`` annotated the same command with "19 families (17 adversarial + the benign
  baseline)". 17 + 1 = 18. Every individual number in that sentence was right and the sentence did
  not add up.
* Both files, plus ``README.md``'s prose, said **5 suites** and enumerated ``stub + reach +
  humanoid + LIBERO + Meta-World`` while ``keepout_zones`` had been registered as a sixth.

Three surfaces, one shape: an inventory maintained by hand beside a registry that grew. That is the
argument a reviewer makes for you — a tool whose own catalogue is incomplete is not a catalogue.

WHAT THIS OWNS, AND WHAT IT DELIBERATELY DOES NOT. It rewrites the trailing ``#`` comment on
``provael list-<thing>`` lines and nothing else. ``list-attacks`` is the anchor
``tests/test_counted_claims.py`` already identified as the one that "carries the meaning, because
:func:`provael.cli.list_attacks` iterates the registry and prints every family — so a count offered
as *what that command shows* is a claim about the whole registry, always". A generator that owned
prose would be rewriting arguments; this one owns the parts that are pure inventory.

Usage::

    python scripts/gen_doc_counts.py            # rewrite
    python scripts/gen_doc_counts.py --check    # fail if a rewrite would change anything

``--check`` is what CI runs, via ``tests/test_counted_claims.py``. The rewrite runs beside
``gen_registry_artifact.py`` in ``coverage-badge.yml``, which already commits to the tree.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from provael.attacks.registry import ATTACKS
from provael.coverage import NON_ADVERSARIAL_FAMILIES
from provael.policies.registry import POLICIES, SCAFFOLDING_POLICIES
from provael.suites import FIXTURE_SUITES, REQUIRES_LEROBOT, SCAFFOLDING_SUITES, SUITES

ROOT = Path(__file__).resolve().parent.parent


def families() -> list[str]:
    """Every registered family, adversarial ones first, each group alphabetical.

    The order is a rendering decision and it is deliberate: a reader scanning for coverage wants
    the attacks, and the two non-adversarial arms are the footnote that makes the total add up.
    """
    every = {ctor().family for ctor in ATTACKS.values()}
    adversarial = sorted(every - NON_ADVERSARIAL_FAMILIES)
    benign = sorted(every & NON_ADVERSARIAL_FAMILIES)
    return adversarial + benign


def _counts() -> dict[str, int]:
    every = families()
    return {
        "attacks": len(ATTACKS),
        "families": len(every),
        "adversarial_families": len(set(every) - NON_ADVERSARIAL_FAMILIES),
        "non_adversarial_families": len(NON_ADVERSARIAL_FAMILIES),
        "policies": len(POLICIES),
        "policies_scaffolding": len(SCAFFOLDING_POLICIES),
        "suites": len(SUITES),
        "suites_fixture": len(FIXTURE_SUITES),
        "suites_gated": len(REQUIRES_LEROBOT),
        "suites_scaffolding": len(SCAFFOLDING_SUITES),
    }


def rendered() -> dict[str, str]:
    """The trailing comment each ``provael list-<thing>`` line must carry, keyed by ``<thing>``."""
    n = _counts()
    return {
        # The full enumeration. This is the line that had eighteen of nineteen names in it.
        "attacks": (
            f"{n['attacks']} attacks across {n['families']} families "
            f"({n['adversarial_families']} adversarial + {n['non_adversarial_families']} benign "
            f"control): " + "/".join(families())
        ),
        "policies": (
            f"{n['policies']} policies — 1 CPU (stub), {n['policies'] - 1} need a GPU extra, "
            f"of which {n['policies_scaffolding']} are registered scaffolding"
        ),
        # REGISTERED, not runnable, and the difference is stated rather than rounded away. The docs
        # said "5 suites" because five are runnable; watch/registry.json publishes 6 because six are
        # registered. Both were defensible and they contradicted each other in public, which is the
        # thing this generator exists to stop. registry.json's own note already draws this line:
        # "Registered is not validated."
        "suites": (
            f"{n['suites']} suites registered — {n['suites_fixture']} CPU fixtures, "
            f"{n['suites_gated']} gated real simulators, {n['suites_scaffolding']} scaffolding "
            f"(never run)"
        ),
    }


#: Every file that annotates a ``provael list-<thing>`` line. Not an allow-list of what to check —
#: :func:`main` walks these and rewrites whatever it finds, and the sweep in
#: ``tests/test_counted_claims.py`` is what catches an inventory in a file nobody listed here.
TARGETS = ("README.md", "docs/quickstart.md")

#: `provael list-attacks   # anything`, capturing the command and the comment separately. Requires
#: the comment: a bare command line states no count and is not this generator's business.
_LINE = re.compile(r"^(?P<lead>.*\bprovael list-(?P<thing>[a-z-]+)\s+)#\s*(?P<comment>.*)$", re.M)


def rewrite(text: str) -> tuple[str, list[str]]:
    """Return the text with generated comments applied, plus a note per line changed."""
    wanted = rendered()
    changes: list[str] = []

    def sub(match: re.Match[str]) -> str:
        thing = match.group("thing")
        if thing not in wanted:
            return match.group(0)  # list-recipes, list-reproductions: prose, not inventory
        # OWN COUNTED CLAIMS ONLY. `README.md` annotates list-policies with "stub (CPU); smolvla
        # (needs the [lerobot] extra)" — an illustration, not an inventory, and rewriting it into a
        # tally would replace prose that was never wrong. A comment with no digit in it is making
        # no counted claim and is none of this generator's business. The sweep in
        # tests/test_counted_claims.py is what catches a counted claim that DROPPED its digits.
        if not any(char.isdigit() for char in match.group("comment")):
            return match.group(0)
        new = f"{match.group('lead')}# {wanted[thing]}"
        if new != match.group(0):
            changes.append(f"list-{thing}: {match.group('comment')!r} -> {wanted[thing]!r}")
        return new

    return _LINE.sub(sub, text), changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail instead of writing")
    args = parser.parse_args(argv)

    drift = 0
    for relpath in TARGETS:
        path = ROOT / relpath
        before = path.read_text(encoding="utf-8")
        after, changes = rewrite(before)
        if not changes:
            print(f"ok       {relpath}")
            continue
        drift += len(changes)
        for change in changes:
            print(f"{'DRIFT   ' if args.check else 'rewrote '}{relpath}  {change}")
        if not args.check:
            path.write_text(after, encoding="utf-8")

    if args.check and drift:
        print(
            f"\n{drift} inventory line(s) disagree with the registry.\n"
            f"Run `python scripts/gen_doc_counts.py` — do not edit them by hand; they are "
            f"generated precisely because the hand-maintained versions fell behind.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
