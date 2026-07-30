"""Defense registry: resolve names to :class:`~provael.defenses.base.Defense` instances.

Shaped deliberately like :mod:`provael.attacks.registry` — same dict-of-factories, same
``available_* / make_* / resolve_*`` trio, same error phrasing — so the two read the same at a
glance and neither needs its own mental model.

**Exactly two entries ship today.** ``docs/DEFENSES.md`` lists six mitigation rows; the remaining
four are each "a **specified, unproven** mitigation — the honest status for every row in the
taxonomy
above", and they are absent here on purpose.

The second entry is what the action-side hook bought. Four of the six rows act on the policy's
*output*, and until :meth:`provael.defenses.base.Defense.filter_action` existed none of them could
be
written against the interface at all — so "unproven" was overstating it: they were unimplementable.
``action_envelope`` implements row 3 and is measured; the other three output-side rows remain
unwritten and unregistered. Registering placeholders so the table looks complete would let
``provael list-defenses`` imply coverage that has never been measured, which is the precise failure
mode this project's methodology exists to prevent. A row joins this registry when a study reports
its pre/post ASR under the controls, not before.
"""

from __future__ import annotations

from collections.abc import Callable

from provael.defenses.base import Defense
from provael.defenses.canonicalize import InstructionCanonicalization
from provael.defenses.envelope import ActionEnvelopeClamp

#: Registry of defense factories keyed by defense name.
#:
#: Each factory takes NO arguments, so a registered defense always runs with its committed defaults.
#: For ``action_envelope`` that matters: its bounds are derived from a measured benign envelope, and
#: a factory that accepted a tighter bound would let `--defense action_envelope` quietly mean
#: something other than what the study measured.
DEFENSES: dict[str, Callable[[], Defense]] = {
    "instruction_canonicalization": InstructionCanonicalization,
    "action_envelope": ActionEnvelopeClamp,
}


def available_defenses() -> list[str]:
    """All registered defense names."""
    return list(DEFENSES)


def make_defense(name: str) -> Defense:
    """Instantiate a single defense by name.

    Raises:
        KeyError: if ``name`` is not a registered defense.
    """
    try:
        factory = DEFENSES[name]
    except KeyError:
        raise KeyError(f"unknown defense {name!r}; available: {available_defenses()}") from None
    return factory()


def resolve_defenses(tokens: list[str]) -> list[Defense]:
    """Resolve a list of defense names into instances, preserving order and dropping duplicates.

    Raises:
        KeyError: if a token is not a registered defense.
    """
    resolved: list[Defense] = []
    seen: set[str] = set()
    for token in tokens:
        if token not in DEFENSES:
            raise KeyError(f"unknown defense {token!r}; available: {available_defenses()}")
        if token not in seen:
            seen.add(token)
            resolved.append(make_defense(token))
    return resolved


__all__ = ["DEFENSES", "available_defenses", "make_defense", "resolve_defenses"]
