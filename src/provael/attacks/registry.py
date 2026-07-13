"""Attack registry: resolve names and family names to :class:`Attack` instances.

Families: ``baseline`` (a no-op control for measuring lift), ``instruction`` (text
reframings), ``visual`` (perception perturbations), ``injection`` (indirect / embodied
prompt injection), ``action`` (action-space-integrity: freeze / trajectory hijack),
``action_space`` (EAI04 2nd vector: keep-out hijack of the commanded end-effector /
critical-step freeze), ``sensor_spoof`` (EAI02 adversarial perception / sensor spoofing
into a keep-out zone),
``backdoor`` (EAI03 objective-decoupled trigger screening), ``authorization`` (EAI08
identity / access / excessive autonomy), ``misalignment`` (EAI06 cross-domain safety
misalignment / the embodiment gap: benign language → unsafe embodied action), and
``optimized`` (a black-box search). The
registry maps both individual attack names and family names to attacks, so
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
from provael.attacks.action_space import (
    FAMILY as ACTION_SPACE_FAMILY,
)
from provael.attacks.action_space import (
    CriticalFreeze,
    KeepoutHijack,
)
from provael.attacks.authorization import (
    FAMILY as AUTHORIZATION_FAMILY,
)
from provael.attacks.authorization import (
    ScopeEscalation,
    SelfAuthorizeBypass,
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
from provael.attacks.misalignment import (
    FAMILY as MISALIGNMENT_FAMILY,
)
from provael.attacks.misalignment import (
    BenignUrgencyOverride,
    EuphemisticReroute,
)
from provael.attacks.optimized import (
    FAMILY as OPTIMIZED_FAMILY,
)
from provael.attacks.optimized import (
    TargetedTrajectoryHijack,
)
from provael.attacks.sensor_spoof import (
    FAMILY as SENSOR_SPOOF_FAMILY,
)
from provael.attacks.sensor_spoof import (
    PatchSpoof,
    SignalSpoof,
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
    "keepout_hijack": KeepoutHijack,
    "critical_freeze": CriticalFreeze,
    "targeted_hijack": TargetedTrajectoryHijack,
    "object_trigger": ObjectTriggerBackdoor,
    "phrase_trigger": PhraseTriggerBackdoor,
    "self_authorize_bypass": SelfAuthorizeBypass,
    "scope_escalation": ScopeEscalation,
    "patch_spoof": PatchSpoof,
    "signal_spoof": SignalSpoof,
    "benign_urgency_override": BenignUrgencyOverride,
    "euphemistic_reroute": EuphemisticReroute,
}

#: Family name -> ordered member attack names.
FAMILIES: dict[str, list[str]] = {
    BASELINE_FAMILY: ["none"],
    INSTRUCTION_FAMILY: ["roleplay", "goal_substitution", "paraphrase"],
    VISUAL_FAMILY: ["patch", "decoy_object"],
    SENSOR_SPOOF_FAMILY: ["patch_spoof", "signal_spoof"],
    INJECTION_FAMILY: ["scene_text", "mcp_tool_desc"],
    ACTION_FAMILY: ["freeze", "trajectory_hijack"],
    ACTION_SPACE_FAMILY: ["keepout_hijack", "critical_freeze"],
    BACKDOOR_FAMILY: ["object_trigger", "phrase_trigger"],
    AUTHORIZATION_FAMILY: ["self_authorize_bypass", "scope_escalation"],
    MISALIGNMENT_FAMILY: ["benign_urgency_override", "euphemistic_reroute"],
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
