"""Defenses — measured mitigations, held to the same evidential bar as attacks.

``docs/defenses.md`` is the taxonomy and the spec. Its rule is the one this package exists to
implement: a mitigation "earns a row in a results table only after a study measures its pre/post
ASR under the controls below" — pre/post ASR per family with 95% Wilson intervals, a benign-FPR
control, and a benign-task-success acceptance gate.

Exactly **two** defenses ship today: ``instruction_canonicalization`` (input side) and
``action_envelope`` (action side). The other four rows of the taxonomy remain *specified and
unproven*, and are deliberately absent from the registry: a stub registered to make the table look
complete would be a coverage claim we have not measured.

Two is the number because of :meth:`provael.defenses.base.Defense.filter_action`. Four of the six
taxonomy rows act on what leaves the policy, and with only a pre-processing hook they were not
merely
unmeasured but **unimplementable** — the taxonomy was a spec its own interface could not satisfy.
``action_envelope`` is the first row that hook made writable; the remaining three output-side rows
(trajectory anomaly detection, rate limiting / scope enforcement, output / memory screening) are now
expressible and still unwritten.

:mod:`provael.defenses.measure` builds the mitigation report a buyer files. It binds both the
defended and undefended runs by their report digests, so the pair is tamper-evident and
re-derivable — and note what it does *not* do: no field is added to
:class:`~provael.types.RunReport`, so the attestation subject digest is unmoved and attestations
issued by earlier versions still verify.
"""

from __future__ import annotations

from provael.defenses.base import Defense
from provael.defenses.canonicalize import InstructionCanonicalization
from provael.defenses.envelope import ActionEnvelopeClamp
from provael.defenses.registry import (
    DEFENSES,
    available_defenses,
    make_defense,
    resolve_defenses,
)

__all__ = [
    "Defense",
    "InstructionCanonicalization",
    "ActionEnvelopeClamp",
    "DEFENSES",
    "available_defenses",
    "make_defense",
    "resolve_defenses",
]
