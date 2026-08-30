"""Two registry invariants that were held by convention and by nothing else.

Both are the same shape of problem: a derived collection that happens to agree with its source
today, with no assertion that it still will tomorrow. Neither is a live defect — both are correct
as this file is written — which is exactly why they are worth pinning now rather than after a
release has shipped on the wrong side of one.

WHY `FAMILIES`. `attacks/registry.py` declares `FAMILIES` as a hand-written map of family name to
attack names, while every registered attack independently declares its own `family`. Those two
statements of the same fact can disagree in three directions: an attack whose family is missing
from the map, a map entry naming an attack that is not registered, and a map that puts an attack
in a family its own class does not claim. `coverage.py` exists because restated counts drift —
"fourteen families" survived a whole release after the registry moved to fifteen — and a family
count is derived from exactly this pair.

WHY `FIXTURE_SUITES`. `suites/__init__.py` derives it with
``getattr(factory, "is_fixture", False)``, and its own comment says fixtures are "declared by the
suite classes themselves ... rather than name-matched here, so adding a fixture suite cannot
silently earn it a real-evidence label". That intent is right and the mechanism only works because
fixtures happen to be registered as CLASSES (`"stub": StubSuite`) while the real simulators are
registered as factory FUNCTIONS (`"libero": _make_libero`). `getattr` cannot see an attribute
through a function, so a fixture registered behind a factory would be silently classified a real
simulator — the stub-as-real promotion the design claims to prevent, and the one that decides
whether `evidence.classify_run` may call a run ``real-episode``.

The test below asserts the derivation against the suites themselves rather than against a literal,
and states plainly which suites it could not instantiate.
"""

from __future__ import annotations

import inspect

import pytest

from provael.attacks.registry import ATTACKS, FAMILIES
from provael.suites import FIXTURE_SUITES, REQUIRES_LEROBOT, SUITES


def test_families_map_and_attack_declarations_agree() -> None:
    """`FAMILIES` must be exactly the partition the registered attacks declare."""
    declared: dict[str, set[str]] = {}
    for name, cls in ATTACKS.items():
        declared.setdefault(cls().family, set()).add(name)
    mapped = {family: set(names) for family, names in FAMILIES.items()}

    assert mapped.keys() == declared.keys(), (
        "FAMILIES and the attacks' own `family` attributes name different family sets. "
        f"only in FAMILIES: {sorted(mapped.keys() - declared.keys())}; "
        f"only on attacks: {sorted(declared.keys() - mapped.keys())}. "
        "A family count is derived from this pair, so a disagreement here is a wrong number "
        "on every surface that renders coverage."
    )
    for family in sorted(mapped):
        assert mapped[family] == declared[family], (
            f"family {family!r} disagrees: FAMILIES says {sorted(mapped[family])}, "
            f"the attack classes say {sorted(declared[family])}."
        )


def test_every_family_member_is_registered() -> None:
    """No `FAMILIES` entry may name an attack the registry does not hold."""
    for family, names in FAMILIES.items():
        for name in names:
            assert name in ATTACKS, (
                f"FAMILIES[{family!r}] names {name!r}, which is not in ATTACKS. "
                "Either the attack was removed and the map was not, or the name is a typo — "
                "both render a family that cannot be run."
            )


def test_no_attack_is_claimed_by_two_families() -> None:
    """A `FAMILIES` map with a duplicate would double-count in any coverage sum."""
    seen: dict[str, str] = {}
    for family, names in FAMILIES.items():
        for name in names:
            assert name not in seen, (
                f"{name!r} appears in both {seen[name]!r} and {family!r}. "
                "Coverage sums over families, so a duplicate overstates the total."
            )
            seen[name] = family


def test_fixture_suites_is_derived_from_the_suites_not_from_registration_shape() -> None:
    """`FIXTURE_SUITES` must match what each suite says about itself, not how it was registered.

    Instantiating is the point: reading the class attribute is precisely the mechanism that cannot
    see through a factory function. Suites needing the optional ``[lerobot]`` extra are skipped by
    name and REPORTED, never silently passed — a guard that quietly checks nothing is worse than
    no guard, because it also removes the motivation to build a real one.
    """
    checked: list[str] = []
    skipped: list[str] = []
    for name, factory in SUITES.items():
        if name in REQUIRES_LEROBOT:
            skipped.append(name)
            continue
        suite = factory()
        checked.append(name)
        assert bool(getattr(suite, "is_fixture", False)) == (name in FIXTURE_SUITES), (
            f"suite {name!r} reports is_fixture="
            f"{bool(getattr(suite, 'is_fixture', False))} but FIXTURE_SUITES "
            f"{'contains' if name in FIXTURE_SUITES else 'does not contain'} it. "
            "FIXTURE_SUITES is read by evidence.classify_run to decide whether a run may be "
            "called real-episode, so a disagreement promotes fixture arithmetic to real evidence."
        )

    assert checked, "no suite was instantiable — this test checked nothing."
    if skipped:
        print(f"\n  skipped (need the [lerobot] extra, not instantiable here): {sorted(skipped)}")


def test_a_fixture_registered_behind_a_factory_would_not_be_missed() -> None:
    """Pin the fragility itself: every function-registered suite must be a real simulator.

    `FIXTURE_SUITES` reads a class attribute. That works today only because every fixture is
    registered as a class. This asserts that the coincidence still holds, so the day someone
    registers a fixture behind a factory the failure is loud here rather than silent in the
    evidence classifier.
    """
    for name, factory in SUITES.items():
        if inspect.isclass(factory):
            continue
        assert name in REQUIRES_LEROBOT, (
            f"suite {name!r} is registered behind a factory FUNCTION and is not a known "
            "simulator. getattr(factory, 'is_fixture', False) is False for a function whatever "
            "the suite says about itself, so if this one is a fixture it has just been "
            "classified a real simulator. Register it as a class, or declare it explicitly."
        )


@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_each_family_is_non_empty(family: str) -> None:
    """An empty family is a coverage row that can never be measured."""
    assert FAMILIES[family], f"family {family!r} is declared with no attacks."
