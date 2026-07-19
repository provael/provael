"""Conformity-assessment evidence **dossier** for an ML safety component (``provael certify``).

The EU Machinery Regulation (EU) 2023/1230 **applies from 20 January 2027** (CELEX 32023R1230,
Article 54). It routes ML "self-evolving behaviour" safety components into **Annex I Part A**, whose
categories are subject to the third-party conformity-assessment procedure of **Article 25(2)** (via
Article 6(1)). A notified body reviewing such a component needs the adversarial-robustness evidence
in a form it can read. This module builds that dossier.

**Evidence, not certification.** A dossier is an *input* to a conformity assessment; it is **not** a
conformity assessment, and Provael is **not** a notified body. Nothing here confers a presumption of
conformity, and an operator must not represent it as certification. See
``docs/compliance/machinery-annex-i-part-a.md``.

Design: this is the single code path behind BOTH the Annex I Part A dossier and the existing
Machinery **Annex III** pack (``provael.hosted.machinery`` is now a thin caller —
``--profile annex-iii``). It **reuses** every statistic — nothing here reimplements ASR, the Wilson
or anytime-valid intervals, the matched benign control, Succ-But-Unsafe, or the BH-FDR correction;
they are imported from :mod:`provael.scoring.asr` and :mod:`provael.calibration` (the 0.17.0
cross-arch precedent). It re-runs nothing and wraps the same digest-bound attestation the free
``provael attest`` produces.

Determinism: :func:`build_dossier` is a pure function of the ``RunReport`` and the issuance metadata
(``issued_at`` / ``commit`` / operator ``component``) handed to it — no wall-clock, no random — so a
deterministic run yields a byte-identical dossier (``sort_keys``-stable), exactly like the other
exporters.
"""

from __future__ import annotations

import html
import json
from enum import StrEnum
from pathlib import Path
from typing import Any

from provael.attacks.baseline import FAMILY as BASELINE_FAMILY
from provael.attacks.optimized import FAMILY as OPTIMIZED_FAMILY
from provael.attacks.registry import FAMILIES
from provael.attest import ATTESTATION_JSON, build_statement
from provael.calibration import anytime_ci, wilson_ci
from provael.compliance import CAVEATS, REQUIREMENTS
from provael.hosted.report import DISCLAIMERS
from provael.mlbom import ML_BOM_JSON
from provael.oscal import to_oscal
from provael.scoring.asr import (
    attack_success_rate,
    benjamini_hochberg,
    binom_test_greater,
    by_family,
    matched_benign_fpr,
    succ_but_unsafe,
)
from provael.types import (
    MEASURED_REAL_TRANSFER,
    STUB_VALIDATED_SCAFFOLDING,
    ASRStat,
    ComponentProfile,
    RunReport,
)

#: Dossier bundle filenames written into the output directory.
CERTIFY_JSON = "dossier.json"
CERTIFY_OSCAL_JSON = "dossier.oscal.json"
CERTIFY_HTML = "dossier.html"

#: Machine-readable format ids.
DOSSIER_FORMAT = "provael-machinery-annex-i-part-a-dossier/v1"
ANNEX_III_PACK_FORMAT = "provael-machinery-annex-iii-pack/v1"

#: Factual application date of the Machinery Regulation (CELEX 32023R1230, Article 54).
MACHINERY_APPLIES_FROM = "2027-01-20"
MACHINERY_MANDATORY_NOTE = (
    "Regulation (EU) 2023/1230 applies from 20 January 2027 (CELEX 32023R1230, Article 54). "
    "Machinery / safety components with fully or partially self-evolving behaviour using machine "
    "learning are listed in Annex I Part A and are subject to the third-party conformity "
    "assessment of Article 25(2) (via Article 6(1)). Confirm every clause against the primary text."
)

#: The prominent, non-negotiable framing carried at the top of every dossier.
NOT_A_CONFORMITY_ASSESSMENT = (
    "This document is EVIDENCE INPUT to a conformity assessment. It is NOT a conformity "
    "assessment and NOT a certificate, it confers no presumption of conformity, and Provael is "
    "NOT a notified body. The operator must not represent this document as certification."
)

#: Distinct seeds below which a headline number is preliminary (mirrors runner.py's rule).
SEEDS_PRELIMINARY_THRESHOLD = 5

#: The machinery-relevant crosswalk rows (keys into :data:`provael.compliance.REQUIREMENTS`).
MACHINERY_CROSSWALK_KEYS: tuple[str, ...] = (
    "eu-machinery:annex-i-part-a",
    "eu-machinery:cyber",
    "iso-10218-1:cyber",
    "iso-10218-2:cyber",
    "iec-62443:slv",
    "nist-ai-100-2:taxonomy",
)

#: OSCAL profile identifier per certify profile (populates ``import-ap.href``).
_PROFILE_HREF: dict[str, str] = {
    "annex-i-part-a": "urn:provael:profile:machinery-annex-i-part-a",
    "annex-iii": "urn:provael:profile:machinery-annex-iii",
}

#: Honest-scope caveat ids carried on the dossier (the three universal Provael caveats).
_SCOPE_CAVEAT_IDS: tuple[str, ...] = (
    "adversarial-only",
    "evidence-not-certification",
    "behavioural-not-worst-case",
)

#: Residual-risk statements sourced from SAFETY.md (deferred + permanently out of scope).
_DEFERRED_ATTACK_CLASSES: tuple[str, ...] = (
    "Optimized adversarial suffixes / GCG — deferred (SAFETY.md); sim-only when added.",
    "Transferable pixel-level perturbations — deliberately deferred (SAFETY.md); sim-only when "
    "added.",
)
_OUT_OF_SCOPE: tuple[str, ...] = (
    "Code that controls real robots or hardware (SAFETY.md — will not be added).",
    "Attacks tailored to cause physical injury or property damage (SAFETY.md — out of scope).",
    "Detection-evasion tooling (SAFETY.md — out of scope).",
)

#: Attack name -> family (e.g. ``"roleplay" -> "instruction"``), from the registry.
_NAME_TO_FAMILY: dict[str, str] = {
    name: family for family, names in FAMILIES.items() for name in names
}

#: The Annex III EHSRs the pack maps (moved here from hosted/machinery.py, which now calls us).
_ANNEX_III_EHSRS: tuple[dict[str, str], ...] = (
    {
        "ehsr_id": "Annex III, 1.1.9",
        "ehsr_title": "Protection against corruption",
        "obligation": "Machinery must be designed and constructed so that connection to it, or any "
        "corruption of software/data critical for safety, does not lead to a hazardous situation.",
        "provael_evidence": "Measured ASR per EAI risk — with the EAI04 action-space-integrity "
        "family (keepout_hijack / critical_freeze) as the on-point evidence that the policy's "
        "action output can be corrupted into a hazardous command — each with a 95% Wilson CI and "
        "the benign-FPR control; bound by the dated, digest-verified attestation.",
    },
    {
        "ehsr_id": "Annex III, 1.2.1",
        "ehsr_title": "Safety and reliability of control systems",
        "obligation": "Control systems must be safe and reliable and withstand intended and "
        "unintended influences, including malicious attempts by third parties creating a hazard.",
        "provael_evidence": "Per-family transfer-test (rate + 95% Wilson CI + benign control) "
        "quantifying how often adversarial perturbation (EAI01/02/05/06) redirects the control "
        "policy out of its benign envelope — the third-party-malicious-influence evidence.",
    },
)


class CertifyProfile(StrEnum):
    """Which conformity pack ``certify`` emits — both share this one code path."""

    annex_i_part_a = "annex-i-part-a"
    annex_iii = "annex-iii"


# --------------------------------------------------------------------------------------------
# Shared helpers.
# --------------------------------------------------------------------------------------------

def _run_transfer_tier(report: RunReport) -> str:
    """Run-level honesty tier — the same derivation the attestation and every exporter use."""
    real = report.policy != "stub" and report.suite != "stub"
    return MEASURED_REAL_TRANSFER if real else STUB_VALIDATED_SCAFFOLDING


def _family_transfer_tier(family: str, report: RunReport) -> str:
    """Per-family tier: the optimized family is always stub-validated even on a real run."""
    if family == OPTIMIZED_FAMILY:
        return STUB_VALIDATED_SCAFFOLDING
    return _run_transfer_tier(report)


def _slug(key: str) -> str:
    """A stable OSCAL control-id token from a requirement key (no spaces/colons)."""
    return key.replace(":", "-").replace(" ", "-")


def _statement(family: str, stat: ASRStat, transfer_tier: str) -> str:
    """The honesty sentence: ASR AND the real-policy transfer label, in ONE sentence.

    A family with no real-policy transfer evidence is labelled "not demonstrated on a real policy"
    in the same sentence as its ASR — the non-negotiable transfer-honesty discipline.
    """
    demonstrated = transfer_tier == MEASURED_REAL_TRANSFER
    clause = (
        "demonstrated on a real policy" if demonstrated
        else "not demonstrated on a real policy"
    )
    return (
        f"Family '{family}': ASR {100.0 * stat.asr:.1f}% "
        f"({stat.successes}/{stat.attempts} applicable episodes); {clause}."
    )


def _family_evidence_rows(report: RunReport) -> list[dict[str, Any]]:
    """Per-family adversarial evidence, composed entirely from the reused scoring primitives.

    Each row carries ASR + its n, the fixed-n Wilson 95% interval AND the anytime-valid Robbins
    Beta-mixture interval, the matched benign FPR, Succ-But-Unsafe, the BH-FDR-corrected
    significance across families, and the honest per-family transfer statement.
    """
    fam_stats = by_family(report.results)
    families = [f for f in fam_stats if f != BASELINE_FAMILY]
    benign = report.benign_fpr

    # One-sided exact binomial p per family vs the benign control, BH-corrected across families.
    pvalues: list[float | None] = [
        None if benign is None else binom_test_greater(
            fam_stats[fam].successes, fam_stats[fam].attempts, benign
        )
        for fam in families
    ]
    present = [p for p in pvalues if p is not None]
    bh: dict[str, tuple[float, bool]] = {}
    if present:
        qvalues, reject = benjamini_hochberg(present)
        cursor = iter(zip(qvalues, reject, strict=True))
        for fam, p in zip(families, pvalues, strict=True):
            if p is not None:
                q, sig = next(cursor)
                bh[fam] = (q, sig)

    rows: list[dict[str, Any]] = []
    for family in families:
        stat = fam_stats[family]
        subset = [r for r in report.results if r.family == family]
        with_baseline = [r for r in report.results if r.family in (family, BASELINE_FAMILY)]
        lo, hi = wilson_ci(stat.successes, stat.attempts)
        alo, ahi = anytime_ci(stat.successes, stat.attempts)
        tier = _family_transfer_tier(family, report)
        q_sig = bh.get(family)
        rows.append({
            "family": family,
            "n": stat.attempts,
            "successes": stat.successes,
            "asr": stat.asr,
            "wilson_ci95": [lo, hi],
            "anytime_ci": [alo, ahi],
            "matched_benign_fpr": matched_benign_fpr(with_baseline),
            "succ_but_unsafe": succ_but_unsafe(subset),
            "bh_qvalue": None if q_sig is None else q_sig[0],
            "bh_significant": None if q_sig is None else q_sig[1],
            "transfer_status": tier,
            "transfer_demonstrated": tier == MEASURED_REAL_TRANSFER,
            "statement": _statement(family, stat, tier),
        })
    return rows


def _headline(report: RunReport) -> dict[str, Any]:
    """Overall adversarial evidence: ASR (recomputed from raw episodes) with both intervals."""
    lo, hi = wilson_ci(report.successes, report.attempts) if report.attempts else (0.0, 0.0)
    alo, ahi = anytime_ci(report.successes, report.attempts) if report.attempts else (0.0, 1.0)
    return {
        "asr": attack_success_rate(report.results) if report.results else report.asr,
        "attempts": report.attempts,
        "successes": report.successes,
        "wilson_ci95": [lo, hi],
        "anytime_ci": [alo, ahi],
        "benign_fpr": report.benign_fpr,
        "matched_benign_fpr": report.matched_benign_fpr,
        "succ_but_unsafe": report.succ_but_unsafe,
        "seeds": report.seeds,
        "preliminary": report.preliminary,
        "preliminary_note": (
            f"Preliminary: fewer than {SEEDS_PRELIMINARY_THRESHOLD} distinct seeds ran "
            f"({report.seeds}); the headline is not yet bankable."
            if report.preliminary else None
        ),
    }


def _crosswalk() -> list[dict[str, Any]]:
    """Map each evidence item to its standard clause; mark unverifiable clauses pending."""
    by_key = {req.key: req for req in REQUIREMENTS}
    rows: list[dict[str, Any]] = []
    for key in MACHINERY_CROSSWALK_KEYS:
        req = by_key[key]
        pending = "pending verification" in req.control_id.lower()
        rows.append({
            "key": req.key,
            "framework": req.framework,
            "framework_id": req.framework_id,
            "clause": req.control_id,
            "control_title": req.control_title,
            "evidence_item": req.provael_signal,
            "evidence_refs": list(req.evidence_refs),
            "indicative": req.indicative,
            "clause_verification": "pending-verification" if pending else "verified",
        })
    return rows


def _residual_risk(report: RunReport) -> dict[str, Any]:
    """State plainly what was NOT tested — deferred classes, families not run, embodiments."""
    ran = sorted({_NAME_TO_FAMILY.get(a, a) for a in report.attacks})
    not_run = [f for f in sorted(FAMILIES) if f != BASELINE_FAMILY and f not in ran]
    no_real_transfer = [
        f for f in ran
        if f != BASELINE_FAMILY and _family_transfer_tier(f, report) != MEASURED_REAL_TRANSFER
    ]
    return {
        "deferred_attack_classes": list(_DEFERRED_ATTACK_CLASSES),
        "out_of_scope": list(_OUT_OF_SCOPE),
        "families_not_exercised_this_run": not_run,
        "families_without_real_policy_transfer": no_real_transfer,
        "suite_scope": (
            f"Only the '{report.suite}' suite was exercised; other suites and embodiments are not "
            "covered by this evidence."
        ),
        "statement": (
            "This dossier is bounded by the attacks and the suite actually run. The classes and "
            "families listed here were NOT tested — deferred per SAFETY.md, not run this run, or "
            "GPU-gated so no real-policy transfer was measured — and carry no evidence here."
        ),
    }


def _component_identification(
    report: RunReport, component: ComponentProfile | None
) -> dict[str, Any]:
    """Component identity + intended use + operating envelope.

    Run-derived fields come from the ``RunReport``; operator-declared fields come from the
    ``--component-metadata`` overlay (``None`` where the operator has not completed them).
    """
    declared = component if component is not None else ComponentProfile()
    return {
        "run_derived": {
            "policy": report.policy,
            "suite": report.suite,
            "tool_version": report.tool_version,
            "accelerator": report.accelerator,
            "precision": report.precision,
            "seeds": report.seeds,
            "episodes": report.episodes,
            "horizon": report.horizon,
            "attacks": list(report.attacks),
            "tasks": list(report.tasks),
        },
        "operator_declared": json.loads(declared.model_dump_json()),
    }


def _referenced_artifacts(subject: dict[str, Any]) -> dict[str, Any]:
    """Reference (not duplicate) the ML-BOM and PEP 740 attestation, bound by the run digest."""
    return {
        "note": "Referenced, not duplicated. Generate alongside the run; verify via the digest.",
        "run_report_digest": subject.get("digest", {}),
        "ml_bom": {"file": ML_BOM_JSON, "format": "CycloneDX ML-BOM"},
        "attestation": {"file": ATTESTATION_JSON, "format": "provael-attestation/v1 (PEP 740)"},
    }


# --------------------------------------------------------------------------------------------
# Builders — the two profile shapes, one shared code path.
# --------------------------------------------------------------------------------------------

def _annex_iii_pack(report: RunReport, *, issued_at: str, commit: str) -> dict[str, Any]:
    """The Machinery Annex III EHSR pack (legacy shape — hosted/machinery.py's public contract)."""
    stmt_dict: dict[str, Any] = json.loads(
        build_statement(report, issued_at=issued_at, commit=commit).model_dump_json()
    )
    tier = _run_transfer_tier(report)
    return {
        "format": ANNEX_III_PACK_FORMAT,
        "tool_version": report.tool_version,
        "issued_at": issued_at,
        "instrument": "Regulation (EU) 2023/1230 (Machinery Regulation), Annex III",
        "applies_from": MACHINERY_APPLIES_FROM,
        "subject": stmt_dict["subject"],
        "transfer_status": tier,
        "annex_iii_evidence": [{**ehsr, "transfer_status": tier} for ehsr in _ANNEX_III_EHSRS],
        "attestation_statement": stmt_dict,
        "disclaimers": list(DISCLAIMERS),
    }


def _annex_i_dossier(
    report: RunReport, *, issued_at: str, commit: str, component: ComponentProfile | None
) -> dict[str, Any]:
    """The Annex I Part A conformity-assessment evidence dossier (the rich shape)."""
    stmt_dict: dict[str, Any] = json.loads(
        build_statement(report, issued_at=issued_at, commit=commit).model_dump_json()
    )
    tier = _run_transfer_tier(report)
    family_rows = _family_evidence_rows(report)
    return {
        "format": DOSSIER_FORMAT,
        "profile": CertifyProfile.annex_i_part_a.value,
        "tool_version": report.tool_version,
        "issued_at": issued_at,
        "instrument": "Regulation (EU) 2023/1230 (Machinery Regulation), Annex I Part A",
        "applies_from": MACHINERY_APPLIES_FROM,
        "mandatory_date_note": MACHINERY_MANDATORY_NOTE,
        "not_a_conformity_assessment": NOT_A_CONFORMITY_ASSESSMENT,
        "subject": stmt_dict["subject"],
        "transfer_status": tier,
        "component_identification": _component_identification(report, component),
        "adversarial_evidence": {
            "headline": _headline(report),
            "per_family": family_rows,
        },
        "transfer_statement": {
            "note": "Each family is labelled measured-real-transfer or stub-validated-scaffolding; "
            "a family with no real-policy transfer is stated as such alongside its ASR.",
            "run_tier": tier,
            "per_family": [
                {"family": row["family"], "statement": row["statement"],
                 "transfer_status": row["transfer_status"]}
                for row in family_rows
            ],
        },
        "residual_risk": _residual_risk(report),
        "standards_crosswalk": _crosswalk(),
        "referenced_artifacts": _referenced_artifacts(stmt_dict["subject"]),
        "regulatory_clock": stmt_dict["regulatory_clock"],
        "attestation_statement": stmt_dict,
        "scope_caveats": [{"id": cid, "text": CAVEATS[cid]} for cid in _SCOPE_CAVEAT_IDS],
        "disclaimers": list(DISCLAIMERS),
    }


def build_dossier(
    report: RunReport,
    *,
    profile: CertifyProfile,
    issued_at: str,
    commit: str,
    component: ComponentProfile | None = None,
) -> dict[str, Any]:
    """Build the conformity-evidence dossier for ``profile`` (pure — no clock, no random).

    Args:
        report: the run under assessment.
        profile: which pack shape to emit (Annex I Part A dossier or the Annex III EHSR pack).
        issued_at: UTC ISO-8601 issuance timestamp (passed in, never read from a clock here).
        commit: the source commit the ruleset came from.
        component: operator-declared identity/intended-use/envelope overlay (Annex I only).
    """
    if profile is CertifyProfile.annex_iii:
        return _annex_iii_pack(report, issued_at=issued_at, commit=commit)
    return _annex_i_dossier(report, issued_at=issued_at, commit=commit, component=component)


def to_dossier_json(dossier: dict[str, Any]) -> str:
    """Serialise a dossier to stable, indented JSON (keys sorted)."""
    return json.dumps(dossier, indent=2, sort_keys=True)


def to_dossier_oscal_json(report: RunReport, *, profile: CertifyProfile) -> str:
    """The dossier's OSCAL twin — assessment-results bound to the crosswalk clauses under review."""
    doc = to_oscal(
        report,
        profile_href=_PROFILE_HREF[profile.value],
        reviewed_control_ids=[_slug(key) for key in MACHINERY_CROSSWALK_KEYS],
    )
    return json.dumps(doc, indent=2, sort_keys=True)


# --------------------------------------------------------------------------------------------
# Human-readable HTML (the artifact a safety engineer reads; print-to-PDF).
# --------------------------------------------------------------------------------------------

def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _opt(value: Any) -> str:
    return "[operator to complete]" if value in (None, "") else _esc(value)


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{100.0 * value:.1f}%"


def _ci(pair: Any) -> str:
    if not isinstance(pair, list) or len(pair) != 2:
        return "n/a"
    return f"[{100.0 * pair[0]:.0f}–{100.0 * pair[1]:.0f}%]"


#: Inline stylesheet (each rule on its own short line to satisfy the 100-col limit).
_STYLE_RULES: tuple[str, ...] = (
    ":root { color-scheme: light; }",
    "* { box-sizing: border-box; }",
    "body { font: 15px/1.55 -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;",
    "  color: #16202a; margin: 0 auto; padding: 2rem; max-width: 60rem; }",
    "h1 { font-size: 1.7rem; margin: 0 0 .25rem; }",
    "h2 { font-size: 1.15rem; margin: 2rem 0 .5rem; padding-bottom: .2rem;",
    "  border-bottom: 2px solid #0891b2; }",
    "h3 { font-size: 1rem; margin: 1.2rem 0 .4rem; }",
    ".banner { background: #fff7ed; border: 1px solid #fdba74; border-radius: 8px;",
    "  padding: .8rem 1rem; margin: 1rem 0; font-weight: 600; }",
    ".sub { color: #52606d; margin: 0 0 .2rem; }",
    "table { border-collapse: collapse; width: 100%; margin: .6rem 0; font-size: .9rem; }",
    "th, td { border: 1px solid #d5dbe1; padding: .4rem .55rem; text-align: left;",
    "  vertical-align: top; }",
    "th { background: #f1f5f9; }",
    "code { background: #f1f5f9; padding: .05rem .3rem; border-radius: 4px; font-size: .85em; }",
    ".pending { color: #b45309; font-weight: 600; }",
    ".stub { color: #b45309; } .real { color: #047857; }",
    "ul { margin: .3rem 0 .3rem 1.2rem; padding: 0; }",
    "footer { margin-top: 2.5rem; border-top: 1px solid #d5dbe1; padding-top: .8rem;",
    "  color: #52606d; font-size: .82rem; }",
    "@page { size: A4; margin: 16mm; }",
    "@media print { body { padding: 0; max-width: none; } h2 { break-after: avoid; }",
    "  table, tr { break-inside: avoid; } .banner { border-color: #999; } }",
)


def _doc_open(title: str) -> list[str]:
    """The shared HTML head (doctype, meta, inline style)."""
    return [
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_esc(title)}</title>",
        "<style>",
        "\n".join(_STYLE_RULES),
        "</style></head><body>",
    ]


def _html_annex_iii(dossier: dict[str, Any]) -> str:
    subject = dossier["subject"]
    p = _doc_open("Provael — Machinery Annex III EHSR pack")
    p.append("<h1>Machinery Regulation Annex III — EHSR evidence pack</h1>")
    p.append(f'<p class="sub">Subject: <code>{_esc(subject.get("name"))}</code>'
             f" · issued {_esc(dossier['issued_at'])}</p>")
    p.append(f'<div class="banner">{_esc(NOT_A_CONFORMITY_ASSESSMENT)}</div>')
    p.append("<h2>Essential health &amp; safety requirements</h2>")
    p.append("<table><thead><tr><th>EHSR</th><th>Title</th><th>Obligation</th>")
    p.append("<th>Provael evidence</th><th>Transfer status</th></tr></thead><tbody>")
    for e in dossier["annex_iii_evidence"]:
        p.append(f"<tr><td><code>{_esc(e['ehsr_id'])}</code></td>"
                 f"<td>{_esc(e['ehsr_title'])}</td><td>{_esc(e['obligation'])}</td>"
                 f"<td>{_esc(e['provael_evidence'])}</td>"
                 f"<td>{_esc(e['transfer_status'])}</td></tr>")
    p.append("</tbody></table>")
    p.append("<footer><strong>Disclaimers.</strong><ul>")
    p.extend(f"<li>{_esc(d)}</li>" for d in dossier["disclaimers"])
    p.append("</ul></footer></body></html>")
    return "".join(p)


def _html_component_table(comp: dict[str, Any]) -> list[str]:
    dec = comp["operator_declared"]
    run = comp["run_derived"]
    env = dec.get("operating_envelope") or {}
    return [
        "<h2>1 · Component identification, intended use &amp; operating envelope</h2>",
        "<table><tbody>",
        f"<tr><th>Manufacturer</th><td>{_opt(dec.get('manufacturer'))}</td>"
        f"<th>Machine / model</th><td>{_opt(dec.get('machine_model'))}</td></tr>",
        f"<tr><th>Safety component</th><td>{_opt(dec.get('safety_component'))}</td>"
        f"<th>Component version</th><td>{_opt(dec.get('safety_component_version'))}</td></tr>",
        f"<tr><th>Serial / UDI</th><td>{_opt(dec.get('serial_or_udi'))}</td>"
        f"<th>Policy × suite (tested)</th><td><code>{_esc(run['policy'])}</code> × "
        f"<code>{_esc(run['suite'])}</code></td></tr>",
        f'<tr><th>Intended use</th><td colspan="3">{_opt(dec.get("intended_use"))}</td></tr>',
        "<tr><th>Foreseeable misuse</th>"
        f'<td colspan="3">{_opt(dec.get("foreseeable_misuse"))}</td></tr>',
        f'<tr><th>Operating envelope</th><td colspan="3">{_opt(env.get("description"))} — '
        f"max speed {_opt(env.get('max_speed'))}; payload {_opt(env.get('payload'))}; "
        f"workspace {_opt(env.get('workspace'))}; keep-out {_opt(env.get('keepout_zones'))}"
        "</td></tr>",
        "</tbody></table>",
    ]


def _html_family_table(rows: list[dict[str, Any]]) -> list[str]:
    p = [
        "<table><thead><tr><th>Family</th><th>n</th><th>ASR</th><th>Wilson 95%</th>",
        "<th>Anytime</th><th>Matched benign</th><th>Succ-But-Unsafe</th><th>BH q</th>",
        "<th>Transfer statement</th></tr></thead><tbody>",
    ]
    for r in rows:
        q = "n/a" if r["bh_qvalue"] is None else format(r["bh_qvalue"], ".3f")
        cls = "real" if r["transfer_demonstrated"] else "stub"
        p.append(f"<tr><td>{_esc(r['family'])}</td><td>{r['n']}</td><td>{_pct(r['asr'])}</td>"
                 f"<td>{_ci(r['wilson_ci95'])}</td><td>{_ci(r['anytime_ci'])}</td>"
                 f"<td>{_pct(r['matched_benign_fpr'])}</td><td>{_pct(r['succ_but_unsafe'])}</td>"
                 f'<td>{q}</td><td class="{cls}">{_esc(r["statement"])}</td></tr>')
    p.append("</tbody></table>")
    return p


def _html_annex_i(dossier: dict[str, Any]) -> str:
    subject = dossier["subject"]
    head = dossier["adversarial_evidence"]["headline"]
    rr = dossier["residual_risk"]
    refs = dossier["referenced_artifacts"]

    p = _doc_open("Provael — Machinery Annex I Part A conformity-evidence dossier")
    p.append("<h1>Machinery Regulation Annex I Part A — conformity evidence dossier</h1>")
    p.append(f'<p class="sub">Subject: <code>{_esc(subject.get("name"))}</code>'
             f" · issued {_esc(dossier['issued_at'])}"
             f" · tool <code>{_esc(dossier['tool_version'])}</code></p>")
    p.append(f'<div class="banner">{_esc(NOT_A_CONFORMITY_ASSESSMENT)}</div>')
    p.append(f'<p class="sub">{_esc(dossier["mandatory_date_note"])}</p>')

    p.extend(_html_component_table(dossier["component_identification"]))

    p.append("<h2>2 · Adversarial evidence</h2>")
    p.append(f'<p class="sub">Headline ASR <strong>{_pct(head["asr"])}</strong> '
             f"({head['successes']}/{head['attempts']} applicable episodes); "
             f"Wilson 95% {_ci(head['wilson_ci95'])}; anytime-valid {_ci(head['anytime_ci'])}; "
             f"benign FPR {_pct(head['benign_fpr'])}; matched benign "
             f"{_pct(head['matched_benign_fpr'])}; Succ-But-Unsafe "
             f"{_pct(head['succ_but_unsafe'])}; seeds {head['seeds']}.</p>")
    if head.get("preliminary_note"):
        p.append(f'<p class="stub">{_esc(head["preliminary_note"])}</p>')
    p.extend(_html_family_table(dossier["adversarial_evidence"]["per_family"]))

    p.append("<h2>3 · Residual-risk statement</h2>")
    p.append(f'<p class="sub">{_esc(rr["statement"])}</p>')
    p.append(f'<p class="sub">{_esc(rr["suite_scope"])}</p>')
    for title, items in (
        ("Deferred attack classes", rr["deferred_attack_classes"]),
        ("Permanently out of scope", rr["out_of_scope"]),
        ("Families not exercised this run", rr["families_not_exercised_this_run"]),
        ("Families without real-policy transfer", rr["families_without_real_policy_transfer"]),
    ):
        p.append(f"<h3>{_esc(title)}</h3><ul>")
        p.append("".join(f"<li>{_esc(x)}</li>" for x in items) or "<li>none</li>")
        p.append("</ul>")

    p.append("<h2>4 · Standards crosswalk</h2>")
    p.append('<p class="sub">Article/annex numbers verified against CELEX 32023R1230 where '
             "marked; unverifiable clauses are flagged "
             '<span class="pending">[pending verification]</span> rather than guessed.</p>')
    p.append("<table><thead><tr><th>Framework</th><th>Clause</th><th>Control</th>")
    p.append("<th>Evidence item</th></tr></thead><tbody>")
    for c in dossier["standards_crosswalk"]:
        flag = ("" if c["clause_verification"] == "verified"
                else ' <span class="pending">[pending verification]</span>')
        p.append(f"<tr><td>{_esc(c['framework'])}</td><td>{_esc(c['clause'])}{flag}</td>"
                 f"<td>{_esc(c['control_title'])}</td><td>{_esc(c['evidence_item'])}</td></tr>")
    p.append("</tbody></table>")

    p.append("<h2>5 · Referenced artifacts</h2>")
    p.append(f'<p class="sub">{_esc(refs["note"])} '
             f"ML-BOM: <code>{_esc(refs['ml_bom']['file'])}</code>; "
             f"attestation: <code>{_esc(refs['attestation']['file'])}</code>; "
             f"run digest <code>{_esc(refs['run_report_digest'].get('sha256'))}</code>.</p>")

    p.append("<footer><strong>Evidence, not certification.</strong><ul>")
    p.extend(f"<li>{_esc(d)}</li>" for d in dossier["disclaimers"])
    p.append("</ul></footer></body></html>")
    return "".join(p)


def to_dossier_html(dossier: dict[str, Any]) -> str:
    """Render a dossier as a single self-contained, print-to-PDF HTML document."""
    if dossier.get("format") == ANNEX_III_PACK_FORMAT:
        return _html_annex_iii(dossier)
    return _html_annex_i(dossier)


# --------------------------------------------------------------------------------------------
# Bundle writer (the CLI entry point).
# --------------------------------------------------------------------------------------------

def write_dossier(
    report: RunReport,
    out_dir: Path,
    *,
    profile: CertifyProfile,
    issued_at: str,
    commit: str,
    component: ComponentProfile | None = None,
) -> dict[str, Path]:
    """Write the dossier bundle (JSON + OSCAL + HTML) into ``out_dir``; return the paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    dossier = build_dossier(
        report, profile=profile, issued_at=issued_at, commit=commit, component=component
    )
    json_path = out_dir / CERTIFY_JSON
    json_path.write_text(to_dossier_json(dossier) + "\n", encoding="utf-8")
    oscal_path = out_dir / CERTIFY_OSCAL_JSON
    oscal_path.write_text(to_dossier_oscal_json(report, profile=profile) + "\n", encoding="utf-8")
    html_path = out_dir / CERTIFY_HTML
    html_path.write_text(to_dossier_html(dossier), encoding="utf-8")
    return {"json": json_path, "oscal": oscal_path, "html": html_path}


__all__ = [
    "CERTIFY_JSON",
    "CERTIFY_OSCAL_JSON",
    "CERTIFY_HTML",
    "DOSSIER_FORMAT",
    "ANNEX_III_PACK_FORMAT",
    "MACHINERY_APPLIES_FROM",
    "MACHINERY_CROSSWALK_KEYS",
    "NOT_A_CONFORMITY_ASSESSMENT",
    "CertifyProfile",
    "build_dossier",
    "to_dossier_json",
    "to_dossier_oscal_json",
    "to_dossier_html",
    "write_dossier",
]
