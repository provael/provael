"""Defenses — measured mitigations, held to the same evidential bar as attacks.

``docs/DEFENSES.md`` is the taxonomy and the spec. Its rule is the one this package exists to
implement: a mitigation "earns a row in a results table only after a study measures its pre/post
ASR under the controls below" — pre/post ASR per family with 95% Wilson intervals, a benign-FPR
control, and a benign-task-success acceptance gate.

Exactly **one** defense ships today (``instruction_canonicalization``). The other five rows of the
taxonomy remain *specified and unproven*, and are deliberately absent from the registry: a stub
registered to make the table look complete would be a coverage claim we have not measured.

:mod:`provael.defenses.measure` builds the mitigation report a buyer files. It binds both the
defended and undefended runs by their report digests, so the pair is tamper-evident and
re-derivable — and note what it does *not* do: no field is added to
:class:`~provael.types.RunReport`, so the attestation subject digest is unmoved and attestations
issued by earlier versions still verify.
"""

from __future__ import annotations

from provael.defenses.base import Defense
from provael.defenses.canonicalize import InstructionCanonicalization
from provael.defenses.registry import (
    DEFENSES,
    available_defenses,
    make_defense,
    resolve_defenses,
)

__all__ = [
    "Defense",
    "InstructionCanonicalization",
    "DEFENSES",
    "available_defenses",
    "make_defense",
    "resolve_defenses",
]
