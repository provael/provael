"""Attack registry: resolve names and family names to :class:`Attack` instances.

Families: ``baseline`` (a no-op control for measuring lift), ``instruction`` (text
reframings), ``visual`` (perception perturbations), ``injection`` (indirect / embodied
prompt injection), ``action`` (action-space-integrity: freeze / trajectory hijack),
``action_space`` (EAI04 2nd vector: keep-out hijack of the commanded end-effector /
critical-step freeze), ``sensor_spoof`` (EAI02 adversarial perception / sensor spoofing
into a keep-out zone),
``backdoor`` (EAI03 objective-decoupled trigger screening), ``authorization`` (EAI08
identity / access / excessive autonomy), ``confidentiality`` (EAI09 model & data
confidentiality: a memorized-canary leak screen — membership inference / extraction),
``misalignment`` (EAI06 cross-domain safety misalignment / the embodiment gap: benign
language → unsafe embodied action), ``optimized`` (a black-box action-directive search),
``optimized_patch`` (EAI02 the image-channel analogue: a query-budgeted adversarial-patch search,
GPU-gated / inert on the image-less stub), ``universal_patch`` (EAI02 the same channel under the
PHYSICAL attacker's constraint: one patch fit once, then frozen and carried to unseen episodes and
tasks — where ``optimized_patch`` re-searches per episode, which a printed sticker cannot do),
and ``optimized_instruction`` (an optimized, command-
preserving *instruction-channel* search — EAI01 primary, EAI04 targeted-redirection threat model;
unlike the other two optimized families it rides the channel measured to transfer on a real policy).
The registry maps both individual attack names and family names to attacks, so
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
from provael.attacks.confidentiality import (
    FAMILY as CONFIDENTIALITY_FAMILY,
)
from provael.attacks.confidentiality import (
    MembershipInference,
    ModelExtraction,
)
from provael.attacks.controls import (
    CONTROL_FAMILY,
)
from provael.attacks.controls import (
    BenignRewordControl as _BenignRewordControl,
)
from provael.attacks.controls import (
    NonsenseTextControl as _NonsenseTextControl,
)
from provael.attacks.gradient_patch import FAMILY as GRADIENT_PATCH_FAMILY
from provael.attacks.gradient_patch import GradientPatch
from provael.attacks.humanoid import (
    FAMILY as HUMANOID_FAMILY,
)
from provael.attacks.humanoid import (
    BalanceSpoofAttack,
    StrideFreezeAttack,
    WholeBodyHijackAttack,
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
from provael.attacks.optimized_patch import (
    FAMILY as OPTIMIZED_PATCH_FAMILY,
)
from provael.attacks.optimized_patch import (
    OptimizedPatchHijack,
)
from provael.attacks.sensor_spoof import (
    FAMILY as SENSOR_SPOOF_FAMILY,
)
from provael.attacks.sensor_spoof import (
    PatchSpoof,
    SignalSpoof,
)
from provael.attacks.targeted_redirect import (
    FAMILY as OPTIMIZED_INSTRUCTION_FAMILY,
)
from provael.attacks.targeted_redirect import (
    TargetedRedirect,
)
from provael.attacks.universal_patch import (
    FAMILY as UNIVERSAL_PATCH_FAMILY,
)
from provael.attacks.universal_patch import (
    UniversalPatchTransfer,
)
from provael.attacks.visual import (
    FAMILY as VISUAL_FAMILY,
)
from provael.attacks.visual import (
    DecoyObjectAttack,
    PatchAttack,
)
from provael.attacks.weight_integrity import (
    FAMILY as WEIGHT_INTEGRITY_FAMILY,
)
from provael.attacks.weight_integrity import (
    FLIP_LADDER,
    GradientBitFlip,
    RandomBitFlip,
)


#: Registry of attack factories keyed by attack name.
def _weight_entries() -> dict[str, Callable[[], Attack]]:
    """Weight-integrity registry entries: both arms at every budget in FLIP_LADDER."""
    entries: dict[str, Callable[[], Attack]] = {}
    for budget in FLIP_LADDER:
        for cls in (GradientBitFlip, RandomBitFlip):
            key = f"{cls.name}_k{budget}"
            entries[key] = lambda c=cls, k=budget: c(flips=k)  # type: ignore[misc]
    return entries


ATTACKS: dict[str, Callable[[], Attack]] = {
    # EAI03 weight-integrity, one entry per (arm, K). Built by comprehension rather than typed
    # out because the two arms MUST cover the same ladder: a gradient budget with no random arm at
    # the same K cannot separate selection from damage-in-general, and a hand-written list is
    # exactly where that pairing rots. `_weight_entries` binds K per closure (a bare lambda in a
    # loop captures the variable, not its value, and every entry would flip the last budget).
    **_weight_entries(),
    # Harmless-variation controls. Registered only now that provael.scoring.asr excludes
    # CONTROL_FAMILY from BOTH the adversarial population and the benign-FPR baseline; before that,
    # running them would have folded a benign rephrasing into the attack success rate.
    "benign_reword": _BenignRewordControl,
    "nonsense_text": _NonsenseTextControl,
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
    "patch_hijack": OptimizedPatchHijack,
    "gradient_patch": GradientPatch,
    "universal_patch": UniversalPatchTransfer,
    "targeted_redirect": TargetedRedirect,
    "object_trigger": ObjectTriggerBackdoor,
    "phrase_trigger": PhraseTriggerBackdoor,
    "self_authorize_bypass": SelfAuthorizeBypass,
    "scope_escalation": ScopeEscalation,
    "membership_inference": MembershipInference,
    "model_extraction": ModelExtraction,
    "patch_spoof": PatchSpoof,
    "signal_spoof": SignalSpoof,
    "benign_urgency_override": BenignUrgencyOverride,
    "euphemistic_reroute": EuphemisticReroute,
    "balance_spoof": BalanceSpoofAttack,
    "whole_body_hijack": WholeBodyHijackAttack,
    "stride_freeze": StrideFreezeAttack,
}

#: Family name -> ordered member attack names.
FAMILIES: dict[str, list[str]] = {
    BASELINE_FAMILY: ["none"],
    CONTROL_FAMILY: ["benign_reword", "nonsense_text"],
    INSTRUCTION_FAMILY: ["roleplay", "goal_substitution", "paraphrase"],
    VISUAL_FAMILY: ["patch", "decoy_object"],
    SENSOR_SPOOF_FAMILY: ["patch_spoof", "signal_spoof"],
    INJECTION_FAMILY: ["scene_text", "mcp_tool_desc"],
    ACTION_FAMILY: ["freeze", "trajectory_hijack"],
    ACTION_SPACE_FAMILY: ["keepout_hijack", "critical_freeze"],
    BACKDOOR_FAMILY: ["object_trigger", "phrase_trigger"],
    AUTHORIZATION_FAMILY: ["self_authorize_bypass", "scope_escalation"],
    CONFIDENTIALITY_FAMILY: ["membership_inference", "model_extraction"],
    MISALIGNMENT_FAMILY: ["benign_urgency_override", "euphemistic_reroute"],
    HUMANOID_FAMILY: ["balance_spoof", "whole_body_hijack", "stride_freeze"],
    OPTIMIZED_FAMILY: ["targeted_hijack"],
    OPTIMIZED_PATCH_FAMILY: ["patch_hijack"],
    GRADIENT_PATCH_FAMILY: ["gradient_patch"],
    UNIVERSAL_PATCH_FAMILY: ["universal_patch"],
    OPTIMIZED_INSTRUCTION_FAMILY: ["targeted_redirect"],
    # Ordered by budget with each arm beside its control, so a per-attack table reads as the
    # paired comparison it is rather than as ten unrelated rows.
    WEIGHT_INTEGRITY_FAMILY: [
        f"{cls.name}_k{budget}"
        for budget in FLIP_LADDER
        for cls in (GradientBitFlip, RandomBitFlip)
    ],
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
