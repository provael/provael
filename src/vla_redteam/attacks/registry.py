"""Attack registry: resolve names and family names to :class:`Attack` instances.

Part 1 ships the ``instruction`` family only. The registry maps both individual
attack names (``roleplay``, ``goal_substitution``, ``paraphrase``) and family names
(``instruction``) to attacks, so ``--attacks instruction`` expands to the whole
family while ``--attacks roleplay,paraphrase`` selects specific attacks.
"""

from __future__ import annotations

from collections.abc import Callable

from vla_redteam.attacks.base import Attack
from vla_redteam.attacks.instruction import (
    FAMILY as INSTRUCTION_FAMILY,
)
from vla_redteam.attacks.instruction import (
    GoalSubstitutionAttack,
    ParaphraseAttack,
    RolePlayAttack,
)

#: Registry of attack factories keyed by attack name.
ATTACKS: dict[str, Callable[[], Attack]] = {
    "roleplay": RolePlayAttack,
    "goal_substitution": GoalSubstitutionAttack,
    "paraphrase": ParaphraseAttack,
}

#: Family name -> ordered member attack names.
FAMILIES: dict[str, list[str]] = {
    INSTRUCTION_FAMILY: ["roleplay", "goal_substitution", "paraphrase"],
}


def available_attacks() -> list[str]:
    """All individual attack names."""
    return list(ATTACKS)


def available_families() -> list[str]:
    """All attack family names."""
    return sorted(FAMILIES)


def make_attack(name: str) -> Attack:
    """Instantiate a single attack by name.

    Raises:
        KeyError: if ``name`` is not a registered attack.
    """
    try:
        factory = ATTACKS[name]
    except KeyError:
        raise KeyError(f"unknown attack {name!r}; available: {available_attacks()}") from None
    return factory()


def resolve_attacks(tokens: list[str]) -> list[Attack]:
    """Resolve a mixed list of attack names and family names into attack instances.

    Family names expand (in their defined order) to their member attacks. Order is
    preserved and duplicates are removed so the resulting list is stable.

    Raises:
        KeyError: if a token matches neither an attack nor a family.
    """
    resolved_names: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        names = FAMILIES.get(token, [token])
        for name in names:
            if name not in ATTACKS:
                raise KeyError(
                    f"unknown attack or family {token!r}; "
                    f"attacks={available_attacks()} families={available_families()}"
                )
            if name not in seen:
                seen.add(name)
                resolved_names.append(name)
    return [make_attack(name) for name in resolved_names]


__all__ = [
    "ATTACKS",
    "FAMILIES",
    "available_attacks",
    "available_families",
    "make_attack",
    "resolve_attacks",
]
