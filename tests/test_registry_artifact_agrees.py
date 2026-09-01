"""`watch/registry.json` must agree with the registry it claims to count.

THE GAP THIS CLOSES. The artifact's own note says it exists so that "no human types these
numbers" — provael.com fetches it rather than restating counts in prose, because four site
surfaces once disagreed simultaneously. But nothing in this repo checked that the GENERATED file
still matched the registry that generated it, so it could fall silently behind and only the
downstream website would notice.

It did. `gradient_patch` moved the registry to 17 adversarial families and 39 adversarial attacks;
`watch/registry.json` still said 16 and 38 when v0.39.0 was tagged, so the released tag shipped a
counts artifact that contradicted its own code. The full suite passed at that tag. The website's
three-way agreement check caught it afterwards, from another repository.

A generated artifact needs a guard that it was regenerated. Otherwise "generated" only means
"nobody typed it recently".
"""

from __future__ import annotations

import json
from pathlib import Path

from provael.attacks.registry import ATTACKS, FAMILIES
from provael.coverage import NON_ADVERSARIAL_FAMILIES

_ARTIFACT = Path(__file__).resolve().parent.parent / "watch" / "registry.json"

#: Regenerate with: `python scripts/gen_registry_artifact.py`
_REGEN = "python scripts/gen_registry_artifact.py"


def _live() -> dict[str, int]:
    adversarial_families = [f for f in FAMILIES if f not in NON_ADVERSARIAL_FAMILIES]
    adversarial_attacks = [a for f in adversarial_families for a in FAMILIES[f]]
    return {
        "familiesTotal": len(FAMILIES),
        "adversarialFamilies": len(adversarial_families),
        "attacksTotal": len(ATTACKS),
        "adversarialAttacks": len(adversarial_attacks),
    }


def test_the_artifact_exists_and_parses() -> None:
    assert _ARTIFACT.is_file(), f"{_ARTIFACT} is missing — regenerate with `{_REGEN}`"
    json.loads(_ARTIFACT.read_text(encoding="utf-8"))


def test_the_generated_counts_match_the_live_registry() -> None:
    """The one assertion that matters: a stale generated file is indistinguishable from a fresh
    one by inspection, so it has to be compared against the thing it describes."""
    art = json.loads(_ARTIFACT.read_text(encoding="utf-8"))
    live = _live()
    stale = {k: (art.get(k), v) for k, v in live.items() if art.get(k) != v}
    assert not stale, (
        "watch/registry.json disagrees with the registry it counts:\n  "
        + "\n  ".join(f"{k}: artifact says {a}, registry has {v}" for k, (a, v) in stale.items())
        + f"\n\nIt is GENERATED — do not hand-edit. Regenerate with `{_REGEN}`."
    )


def test_the_two_conventions_stay_distinct() -> None:
    """`adversarial*` excludes baseline and control; `*Total` includes them. The artifact's own
    note warns that mixing the two is how a coverage claim inflates by a family, so pin the gap."""
    art = json.loads(_ARTIFACT.read_text(encoding="utf-8"))
    assert art["familiesTotal"] > art["adversarialFamilies"]
    assert art["attacksTotal"] > art["adversarialAttacks"]
    assert art["familiesTotal"] - art["adversarialFamilies"] == len(NON_ADVERSARIAL_FAMILIES)


def test_the_validation_split_partitions_the_registry() -> None:
    """realPolicyTested + stubValidatedOnly must exhaust the adversarial families — the same
    invariant provael.com enforces, checked here so it fails at the source instead of downstream."""
    art = json.loads(_ARTIFACT.read_text(encoding="utf-8"))
    assert art["realPolicyTested"] + art["stubValidatedOnly"] == art["adversarialFamilies"], (
        f"{art['realPolicyTested']} + {art['stubValidatedOnly']} != {art['adversarialFamilies']}"
    )
