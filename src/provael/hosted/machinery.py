"""EU Machinery Regulation **Annex III** evidence-pack draft (a structured evidence export).

Where the insurer report (:mod:`provael.hosted.report`) is a broad conformity *mapping*, this is a
focused **Annex III essential-health-and-safety-requirement (EHSR)** evidence-pack for the two
cybersecurity-relevant EHSRs of Regulation (EU) 2023/1230 (applies **2027-01-20**):

* **1.1.9 — Protection against corruption:** safety functions must not be corruptible such that a
  hazardous situation results.
* **1.2.1 — Safety and reliability of control systems:** control systems must resist intended and
  unintended influences, **including malicious attempts by third parties** that create a hazard.

As of the ``provael certify`` work this pack is no longer a parallel implementation: it is the
``annex-iii`` **profile** of the shared dossier core (:mod:`provael.certify`). This module keeps its
public API (``build_machinery_annex_pack`` / ``to_machinery_annex_pack_json``) and its exact output
shape — it is now a thin caller so both Machinery packs share one code path.

**Evidence, not certification; not an opinion; not legal advice.** It is a structured draft for a
qualified assessor to evaluate, not a conformity-assessment opinion.
:func:`build_machinery_annex_pack` is a pure function of a :class:`~provael.types.RunReport` and its
issuance metadata (dates are the
factual application dates in :data:`provael.attest.REGULATORY_CLOCK`; confirm against the primary
text). It signs nothing itself; a bound SHA-256 digest ties the draft to its attestation. The
experimental server can gate it behind the :func:`provael.hosted.require_entitlement` feature flag.
"""

from __future__ import annotations

from typing import Any

from provael.certify import CertifyProfile, build_dossier, to_dossier_json
from provael.types import RunReport


def build_machinery_annex_pack(
    report: RunReport,
    *,
    issued_at: str,
    commit: str,
) -> dict[str, Any]:
    """Build the Machinery Regulation Annex III evidence-pack (pure) — wraps the attestation.

    Thin caller of :func:`provael.certify.build_dossier` with the ``annex-iii`` profile.

    Args:
        report: the run under assessment.
        issued_at: UTC ISO-8601 issuance timestamp (passed in — never read here, to preserve the
            report-determinism contract).
        commit: the source commit the ruleset came from.
    """
    return build_dossier(
        report, profile=CertifyProfile.annex_iii, issued_at=issued_at, commit=commit
    )


def to_machinery_annex_pack_json(report: RunReport, *, issued_at: str, commit: str) -> str:
    """Serialise the Annex III pack to stable, indented JSON (keys sorted)."""
    return to_dossier_json(
        build_machinery_annex_pack(report, issued_at=issued_at, commit=commit)
    )


__all__ = ["build_machinery_annex_pack", "to_machinery_annex_pack_json"]
