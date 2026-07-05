"""Attack registry: resolve names and family names to :class:`Attack` instances.

Families: ``baseline`` (a no-op control for measuring lift), ``instruction`` (text
reframings), ``visual`` (perception perturbations), ``injection`` (indirect / embodied
prompt injection), ``action`` (action-space-integrity: freeze / trajectory hijack),
``backdoor`` (EAI03 objective-decoupled trigger screening), and ``optimized`` (a
black-box search). The registry maps both individual attack names and family names to attacks, so
``--attacks instruction`` expands a whole family while ``--attacks none,patch,scene_text``
selects specific attacks across families.
"""

from __future__ import annotations

from collections.abc import Callable

from provael.attacks.action import (
    FAMILY as ACTION_FAMILY,
)
from provael.attacks.action import (
    FreezeAttack,
    TrajectoryHijackAttack,
)
from provael.attacks.backdoor_vla import (
    FAMILY as BACKDOOR_FAMILY,
)
from provael.attacks.backdoor_vla import (
    ObjectTriggerBackdoor,
    PhraseTriggerBackdoor,
)
from provael.attacks.base import Attack
from provael.attacks.baseline import (
    FAMILY as BASELINE_FAMILY,
)
from provael.attacks.baseline import (
    NoOpAttack,
)
from provael.attacks.injection import (
    FAMILY as INJECTION_FAMILY,
)
from provael.attacks.injection import (
    MCPToolDescInjection,
    SceneTextInjection,
)
from provael.attacks.instruction import (
    FAMILY as INSTRUCTION_FAMILY,
)
from provael.attacks.instruction import (
    GoalSubstitutionAttack,
    ParaphraseAttack,
    RolePlayAttack,
)
from provael.attacks.optimized import (
    FAMILY as OPTIMIZED_FAMILY,
)
from provael.attacks.optimized import (
    TargetedTrajectoryHijack,
)
from provael.attacks.visual import (
    FAMILY as VISUAL_FAMILY,
)
from provael.attacks.visual import (
    DecoyObjectAttack,
    PatchAttack,
)

#: Registry of attack factories keyed by attack name.
ATTACKS: dict[str, Callable[[], Attack]] = {
    "none": NoOpAttack,
    "roleplay": RolePlayAttack,
    "goal_substitution": GoalSubstitutionAttack,
    "paraphrase": ParaphraseAttack,
    "patch": PatchAttack,
    "decoy_object": DecoyObjectAttack,
    "scene_text": SceneTextInjection,
    "mcp_tool_desc": MCPToolDescInjection,
    "freeze": FreezeAttack,
    "trajectory_hijack": TrajectoryHijackAttack,
    "targeted_hijack": TargetedTrajectoryHijack,
    "object_trigger": ObjectTriggerBackdoor,
    "phrase_trigger": PhraseTriggerBackdoor,
}

#: Family name -> ordered member attack names.
FAMILIES: dict[str, list[str]] = {
    BASELINE_FAMILY: ["none"],
    INSTRUCTION_FAMILY: ["roleplay", "goal_substitution", "paraphrase"],
    VISUAL_FAMILY: ["patch", "decoy_object"],
    INJECTION_FAMILY: ["scene_text", "mcp_tool_desc"],
    ACTION_FAMILY: ["freeze", "trajectory_hijack"],
    BACKDOOR_FAMILY: ["object_trigger", "phrase_trigger"],
    OPTIMIZED_FAMILY: ["targeted_hijack"],
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
