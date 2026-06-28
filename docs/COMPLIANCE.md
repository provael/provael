# Provael & compliance — crosswalk and evidence map

> **Independent project. Not affiliated with or endorsed by ISO, the EU, NIST, IEC, OWASP, or
> MITRE. Not legal advice.** Provael produces **engineering evidence** for the adversarial-
> robustness and security expectations of these frameworks. Running Provael does **not** make a
> system compliant or certified — it generates measurements you can put into a conformity or
> assurance file. Clause/article references are anchored where verifiable and marked
> *indicative* where the precise sub-clause depends on the full standard text.

Robots running **Vision-Language-Action (VLA)** policies sit under *two* regimes at once:
robot-safety standards (**ISO 10218:2025**) and AI regulation (**EU AI Act**). Both now expect
evidence that the AI layer is **robust against adversarial manipulation** — exactly the thing a
chatbot-era security review skips and exactly what Provael measures. This document maps Provael's
outputs to what each framework asks for, and specs the report Provael will generate from them.

---

## What Provael measures (the evidence it produces)

A calibrated Provael run (`provael calibrate` + `provael attack --calib`) yields:

- **Calibrated redirection rate** per attack and per **EAI** risk — the rate at which an attack
  drove the policy out of its *calibrated* safe envelope — with a **95% Wilson CI**.
- **Benign baseline FPR** — the control: the `none` (un-attacked) rate under the *same*
  predicate, plus the held-out benign false-positive rate the calibration was tuned to
  (`<= target-fpr`).
- **Per-risk tagging** — each attack carries its `EAIxx` id (see
  [The Embodied AI Security Top 10](TOP10.md)).
- **Provenance** — per-task calibration artifact (predicate, target/achieved FPR, `n`, seed
  split) and a deterministic, reproducible config.
- **Machine-readable outputs** — `report.json`, **SARIF 2.1.0** (GitHub code scanning), and the
  ASR leaderboard.

These are *behavioural-susceptibility* measurements via templated attacks — not worst-case
certified bounds. See [Honest scope](#honest-scope--what-this-does-not-cover).

---

## Crosswalk — Provael evidence → frameworks

| Provael signal (EAI / metric) | EU AI Act (Reg. 2024/1689) | ISO 10218:2025 | NIST AI 100-2 / AI RMF | IEC 62443 |
|---|---|---|---|---|
| **EAI01** instruction jailbreak | Art. 15 — cybersecurity: resilience to attempts to alter use/outputs/performance | Cybersecurity / unauthorized-manipulation requirements *(indicative)* | Abuse / evasion (integrity) | Access control; use-control *(indicative)* |
| **EAI02** adversarial perception | Art. 15 — resilience to *adversarial examples* (inputs designed to cause mistakes) | Cybersecurity req. *(indicative)* | Evasion (integrity) | — |
| **EAI05** indirect / embodied injection | Art. 15 — manipulation via crafted inputs | Cybersecurity req. *(indicative)* | Indirect prompt injection | Data integrity *(indicative)* |
| **Calibrated redirection rate + 95% CI** | Art. 15 — *accuracy metrics declared* + robustness measurement; benchmarking methodology | Evidence for the cyber-risk assessment *(indicative)* | **AI RMF MEASURE** (measure risks) | Security level verification *(indicative)* |
| **Benign baseline FPR (control)** | Art. 15 — consistent performance; false-positive characterisation | — | AI RMF MEASURE (validity, reliability) | — |
| **EAI10** eval / observability gaps | Art. 72 — post-market monitoring *(indicative)* | Logging / diagnostics *(indicative)* | **AI RMF MANAGE** | — |
| **Red-team process + EAI taxonomy** | Art. 9 — risk-management system *(indicative)* | Cyber-risk assessment input *(indicative)* | **AI RMF GOVERN / MAP** | Risk assessment (Zone/Conduit) *(indicative)* |

EU AI Act **Article 15** ("Accuracy, robustness and cybersecurity") explicitly names resilience
to *data poisoning, model poisoning, adversarial examples (model evasion), and confidentiality
attacks* — which is the EAI taxonomy in regulatory language. The OWASP / MITRE columns of the
same mapping live in [TOP10.md → Cross-framework crosswalk](TOP10.md#cross-framework-crosswalk-corrected-verbatim-source-items).

---

## Evidence map — requirement → what to attach

| Requirement (paraphrased) | Provael artifact that evidences it |
|---|---|
| EU AI Act Art. 15 — declare accuracy/robustness metrics & methodology | `report.json` + this run's config (deterministic); the calibrated redirection rate + CI per EAI risk |
| EU AI Act Art. 15 — resilience to manipulation/adversarial inputs | Per-attack results across EAI01/02/05 with the benign-FPR control; SARIF for the security review |
| EU AI Act Art. 9 / ISO 10218 cyber-risk assessment | The EAI risk list as the threat catalogue + measured rates per risk |
| EU AI Act Art. 72 — post-market monitoring | Re-run on each model/checkpoint update; track redirection rate over time (leaderboard) |
| NIST AI RMF MEASURE | Calibrated rate + CI + benign FPR (a measured, controlled metric, not a vibe) |
| Auditor wants reproducibility | Seed, config, and per-task calibration artifact (target vs achieved FPR, fit/holdout split) |

---

## Honest scope — what this does *not* cover

- **Adversarial security only.** Functional/mechanical safety (ISO 10218 safety clauses, ISO
  13482, ISO/TS 15066) and non-adversarial reliability are **out of scope** — see the
  [TOP10 scope box](TOP10.md#scope-read-this--its-deliberate).
- **Evidence, not conformity.** EU AI Act conformity also requires a quality-management system,
  technical documentation, human oversight, logging, and more. Provael covers the **Art. 15
  robustness/cybersecurity *testing-evidence* slice**, not the whole obligation.
- **Behavioural, not worst-case.** Today's attacks are templated/auditable, not gradient/search-
  optimised; one policy (SmolVLA) and one suite (LIBERO) ship. Treat results as a floor on
  susceptibility, not a certified bound. See the README's "Scope and honest limitations."
- **Sub-clause precision is indicative.** Rows marked *(indicative)* name the relevant standard
  area; confirm the exact clause against the full standard text for an audit.

---

## Planned: `provael report --format compliance` (v2.x — gated on demand)

The crosswalk above is the spec for a generator that turns a calibrated run into an
auditor-ready evidence report. **Not built yet** — it's pre-specced here so the data model is
right before there's a paying reason to build the hosted version.

- **Input:** a calibrated run's `report.json` (+ its calibration artifacts) and a target
  framework profile (`eu-ai-act` | `iso-10218` | `nist-ai-rmf`).
- **Output:** a per-control evidence document (Markdown/JSON, later PDF): each mapped control →
  the Provael signal, the measured result (redirection rate + CI + benign FPR), a pass/fail vs a
  configurable threshold, and a reference to the underlying artifact (SARIF / `report.json`).

Proposed **evidence schema** (one entry per mapped control):

```json
{
  "framework": "eu-ai-act",
  "control_id": "Article 15",
  "control_title": "Accuracy, robustness and cybersecurity",
  "provael_signal": "EAI01 instruction jailbreak (calibrated)",
  "result": {
    "redirection_rate": 0.60,
    "ci95": [0.31, 0.83],
    "benign_fpr": 0.0,
    "n": 10,
    "calibrated": true,
    "target_fpr": 0.05
  },
  "status": "review",
  "evidence_refs": ["report.json#/by_attack/goal_substitution", "report.sarif"]
}
```

`status` is advisory (`pass` / `review` / `fail` against a user-set threshold), never an
assertion of legal compliance.

---

## References

Verified anchors (read the full text for clause-level audit use):

- EU AI Act (Regulation (EU) 2024/1689) — **Article 15, Accuracy, robustness and cybersecurity**:
  <https://artificialintelligenceact.eu/article/15/>
- **ISO 10218-1:2025** Robotics — Safety requirements — Part 1 (incl. cybersecurity /
  unauthorized-access requirements): <https://www.iso.org/standard/73933.html>
- **ISO 10218-2:2025** — Part 2 (robot applications & cells): <https://www.iso.org/standard/73934.html>
- **NIST AI 100-2e2025** (Adversarial ML taxonomy) and the **NIST AI Risk Management Framework**
  (AI 100-1; GOVERN / MAP / MEASURE / MANAGE).
- **IEC 62443** — industrial automation & control systems security.

See also [TOP10.md](TOP10.md) (the risk taxonomy + OWASP/MITRE crosswalk) and
[SAFETY.md](../SAFETY.md) (responsible-use scope).

---

*Independent · not legal advice · evidence, not certification. PRs and corrections welcome via
the [Top 10 issue form](https://github.com/provael/provael/issues/new?template=top10-feedback.yml).*
