"""Emit a Provael run as NIST OSCAL assessment-results JSON (compliance-as-code).

OSCAL (https://pages.nist.gov/OSCAL/) is NIST's machine-readable model for security assessment
results — the format GRC / ATO tooling ingests. Mapping a Provael run to OSCAL assessment-results
lets buyers pipe ASR evidence straight into those workflows, beyond SARIF.

Mapping: each attack -> an **observation** (method TEST); each EAI risk -> a **risk**; the overall
ASR + benign control -> a **finding**.

DETERMINISM: ids are stable ``uuid5`` derived from the run (no random/clock), so a deterministic
run yields a byte-identical document. Timestamps are not available deterministically here, so
``metadata.last-modified`` is a placeholder the emitter/consumer should stamp at emit time — this
is stated in a metadata property.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from provael.calibration import wilson_ci
from provael.eai import CATALOG
from provael.evidence import evidence_state_of, transfer_status_of
from provael.scoring.asr import benign_control
from provael.types import ASRStat, RunReport
from provael.verdict import release_verdict

#: Filename written into a run's output directory.
OSCAL_JSON = "report.oscal.json"

#: Placeholder timestamp (no deterministic clock available); stamp at emit time if required.
_PLACEHOLDER_TS = "1970-01-01T00:00:00+00:00"

_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/provael/provael")


def _uid(report: RunReport, *parts: str) -> str:
    """A stable uuid5 for ``parts`` within this run (deterministic — no random/clock)."""
    name = ":".join((report.policy, report.suite, *parts))
    return str(uuid.uuid5(_NS, name))


#: Sentinel for ``observation.collected`` when the caller supplies no collection time.
#:
#: OSCAL requires ``collected`` on every observation (a DateTimeWithTimezone), but a
#: :class:`~provael.types.RunReport` deliberately carries no wall-clock so that it stays
#: byte-reproducible — the run's real timestamps live in ``execution-manifest.json``. Rather than
#: invent a plausible-looking date (which would put a false fact into a compliance artifact), an
#: unsupplied collection time is emitted as the Unix epoch, which no reader can mistake for a real
#: collection date, and flagged explicitly via the ``collected-precision`` property. Pass
#: ``collected=`` (the CLI and ``certify`` do) to record the actual time.
UNRECORDED_COLLECTED = "1970-01-01T00:00:00Z"


def _observation_props(
    report: RunReport, name: str, stat: ASRStat, *, collected: str | None
) -> list[dict[str, str]]:
    """Props for one attack's observation — self-describing, with no unmeasured rate.

    ``asr`` is emitted ONLY when the attack had applicable episodes. ``ASRStat.asr`` is 0.0 at zero
    attempts purely as a serialisation sentinel (:mod:`provael.types`), so publishing it here would
    give a GRC tool that charts the prop an attack class plotted at 0% success and read as
    tested-and-clean. ``applicable`` and ``attempts`` are emitted unconditionally so a consumer can
    filter on them directly instead of inferring intent from an absent prop or parsing the
    free-text description for ``n``.
    """
    props = [
        {"name": "attack", "value": name},
        {"name": "applicable", "value": "true" if stat.attempts else "false"},
        {"name": "attempts", "value": str(stat.attempts)},
    ]
    if stat.attempts:
        props.append({"name": "asr", "value": f"{stat.asr:.4f}"})
    props.append(
        {"name": "eai", "value": report.eai[name].id} if name in report.eai
        else {"name": "control", "value": "baseline"}
    )
    props.append({
        "name": "collected-precision",
        "value": "unrecorded" if collected is None else "exact",
    })
    return props


def to_oscal(
    report: RunReport,
    *,
    profile_href: str | None = None,
    reviewed_control_ids: list[str] | None = None,
    collected: str | None = None,
) -> dict[str, object]:
    """Build an OSCAL assessment-results object (as a dict).

    With no keyword args the output is byte-identical to the historical exporter (empty
    ``import-ap.href``, no reviewed-controls). The ``certify`` path passes ``profile_href`` (the
    conformity profile the results are assessed against) and ``reviewed_control_ids`` (the crosswalk
    clauses), which populate ``import-ap.href`` and an OSCAL ``reviewed-controls`` block so a GRC
    consumer can bind each finding to the standard clause it informs.
    """
    collected_at = collected or UNRECORDED_COLLECTED
    observations = [
        {
            "uuid": _uid(report, "obs", name),
            "description": f"Provael attack '{name}': {stat.successes}/{stat.attempts} unsafe.",
            "methods": ["TEST"],
            # Required by the OSCAL assessment-results schema (observation requires
            # uuid/description/methods/collected). Omitting it made every observation invalid.
            "collected": collected_at,
            "props": _observation_props(report, name, stat, collected=collected),
        }
        for name, stat in report.by_attack.items()
    ]

    risks = []
    seen: set[str] = set()
    for _attack_name, tag in report.eai.items():
        if tag.id in seen:
            continue
        seen.add(tag.id)
        risk = CATALOG.get(tag.id)
        risks.append({
            "uuid": _uid(report, "risk", tag.id),
            "title": f"{tag.id}: {risk.name if risk is not None else tag.id}",
            "description": f"Embodied AI Security {tag.id} exercised by Provael attacks.",
            # `statement` is required by the schema (risk requires
            # uuid/title/description/statement/status) — an impact summary, distinct from the
            # description of what the risk is.
            "statement": (
                f"If exploited, {tag.id} lets an adversary drive the policy under test outside its "
                "safe operating envelope in simulation. Provael measures how often the shipped "
                f"{tag.id} attacks achieve that, as an attack-success rate with a 95% Wilson "
                "confidence interval read against a benign control."
            ),
            "status": "open",
        })

    adv_rate, adv_s, adv_n = report.adversarial_headline()
    benign = benign_control(report)
    lo, hi = wilson_ci(adv_s, adv_n) if adv_n else (0.0, 0.0)
    # D1: the same run-level honesty tier the compliance export and attestation carry, so an OSCAL
    # consumer cannot misread stub scaffolding as a conformity-relevant real-transfer measurement.
    transfer_status = transfer_status_of(report)
    decision = release_verdict(report)
    # `target` is required by the schema (finding requires uuid/title/description/target), and
    # finding-target itself requires type/target-id/status{state}. The state is DERIVED from the
    # run's own release verdict rather than hardcoded: emitting a fixed "satisfied" would publish a
    # conformity conclusion the measurement does not support. Only an outright `pass` is satisfied —
    # `fail`, `incomplete` and `conditional` are all not-satisfied for the purpose of this finding.
    target_state = "satisfied" if decision.verdict.value == "pass" else "not-satisfied"
    finding = {
        "uuid": _uid(report, "finding", "overall"),
        "title": "Adversarial Attack Success Rate",
        "target": {
            # target-id is a TokenDatatype: no whitespace or colons.
            "type": "objective-id",
            "target-id": "provael.adversarial-attack-success-rate",
            "title": "Adversarial robustness of the policy under test",
            "status": {
                "state": target_state,
                "reason": f"release-verdict:{decision.verdict.value}",
                "remarks": (
                    "Provael measures behavioural susceptibility in simulation. This state "
                    "reflects the run's own release verdict against the configured thresholds; it "
                    "is evidence toward an assessment, not a conformity determination."
                ),
            },
        },
        "description": (
            f"Adversarial ASR {adv_rate:.4f} ({adv_s}/{adv_n}), 95% CI [{lo:.4f}, {hi:.4f}]; "
            f"all-episode observed-unsafe {report.asr:.4f} ({report.successes}/{report.attempts})"
            + (
                ""
                if benign is None
                else (
                    f"; benign FPR {benign.rate:.4f}"
                    + (f" ({benign.successes}/{benign.attempts})" if benign.attempts else "")
                    + (
                        f", 95% CI [{benign.ci95[0]:.4f}, {benign.ci95[1]:.4f}]"
                        if benign.ci95 is not None
                        else ""
                    )
                )
            )
        ),
        "props": [
            {"name": "adversarial-asr", "value": f"{adv_rate:.4f}"},
            {"name": "adversarial-n", "value": str(adv_n)},
            {"name": "all-episode-unsafe-rate", "value": f"{report.asr:.4f}"},
            {"name": "ci95-low", "value": f"{lo:.4f}"},
            {"name": "ci95-high", "value": f"{hi:.4f}"},
            {"name": "calibrated", "value": str(report.calibrated).lower()},
            # The control arm as first-class props, beside the ASR's own. An assessor reading
            # `adversarial-asr` without `benign-fpr` is reading a difference with one term.
            *(
                []
                if benign is None
                else [
                    {"name": "benign-fpr", "value": f"{benign.rate:.4f}"},
                    *(
                        [{"name": "benign-n", "value": str(benign.attempts)}]
                        if benign.attempts
                        else []
                    ),
                    *(
                        [
                            {"name": "benign-ci95-low", "value": f"{benign.ci95[0]:.4f}"},
                            {"name": "benign-ci95-high", "value": f"{benign.ci95[1]:.4f}"},
                        ]
                        if benign.ci95 is not None
                        else []
                    ),
                ]
            ),
            {"name": "transfer-status", "value": transfer_status},
            {"name": "evidence-state", "value": evidence_state_of(report).value},
            {"name": "release-verdict", "value": release_verdict(report).verdict.value},
        ],
    }

    result: dict[str, object] = {
        "uuid": _uid(report, "result"),
        "title": "Provael red-team result",
        "description": "Behavioural-susceptibility measurement via templated attacks.",
        "start": _PLACEHOLDER_TS,
        "observations": observations,
        "risks": risks,
        "findings": [finding],
    }
    # certify path: bind the findings to the conformity clauses under review, so a GRC consumer
    # reads which standard controls this assessment informs. Omitted (and thus byte-identical to the
    # historical output) when no crosswalk is supplied.
    if reviewed_control_ids:
        result["reviewed-controls"] = {
            "control-selections": [
                {"include-controls": [{"control-id": cid} for cid in reviewed_control_ids]}
            ]
        }

    return {
        "assessment-results": {
            "uuid": _uid(report, "assessment-results"),
            "metadata": {
                "title": f"Provael VLA red-team — {report.policy} x {report.suite}",
                "last-modified": _PLACEHOLDER_TS,
                "version": report.tool_version,
                "oscal-version": "1.1.2",
                "props": [
                    {"name": "tool", "value": "Provael"},
                    {"name": "note", "value": "Stamp last-modified at emit time if required."},
                ],
            },
            "import-ap": {"href": profile_href or ""},
            "results": [result],
        }
    }


def to_oscal_json(report: RunReport) -> str:
    """Serialise the OSCAL assessment-results as deterministic JSON."""
    return json.dumps(to_oscal(report), indent=2, sort_keys=True)


def write_oscal(report: RunReport, path: Path) -> Path:
    """Write the OSCAL JSON to ``path`` and return it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_oscal_json(report), encoding="utf-8")
    return path


__all__ = ["OSCAL_JSON", "to_oscal", "to_oscal_json", "write_oscal"]
