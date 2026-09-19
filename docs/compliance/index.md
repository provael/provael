# Provael & compliance — crosswalk and evidence map

> **Independent project. Not affiliated with or endorsed by ISO, the EU, NIST, IEC, OWASP, or
> MITRE. Not legal advice.** Provael produces **engineering evidence** for the adversarial-
> robustness and security expectations of these frameworks. Running Provael does **not** make a
> system compliant or certified — it generates measurements you can put into a conformity or
> assurance file. Clause/article references are anchored where verifiable and marked
> *indicative* where the precise sub-clause depends on the full standard text.

Robots running **Vision-Language-Action (VLA)** policies sit under *three* regimes at once:
robot-safety standards (**ISO 10218:2025**), product law (the **EU Machinery Regulation
(EU) 2023/1230**), and AI regulation (the **EU AI Act**). All three now expect evidence that the
AI layer is **robust against adversarial manipulation** — exactly the thing a chatbot-era security
review skips and exactly what Provael measures. This document maps Provael's outputs to what each
framework asks for, and specs the report Provael generates from them.

> **Regulatory routing (2026 Digital Omnibus update).** Under the Digital Omnibus on AI
> (Regulation (EU) 2026/1744, OJ L 24 July 2026, in force 27 July 2026), AI-enabled
> **machinery/robots** are routed out of EU AI Act **Chapter III** directly: the AI-specific
> health-and-safety expectations — including **robustness against manipulation** — reach robots
> through **delegated acts to the Machinery Regulation** (the Machinery Regulation applies from
> **2027-01-20**; AI-specific delegated acts expected by **2028-08-02**), alongside the new
> **cybersecurity risk assessment** in **ISO 10218:2025**. The Omnibus also shifts the high-risk
> AI Act deadlines — stand-alone Annex III to **2027-12-02**, embedded Annex I to **2028-08-02**.
> That deferral is **no longer proposed**: Regulation (EU) 2026/1744 was published in the OJ on
> **2026-07-24** and entered into force on **2026-07-27**, so **2028-08-02** is the operative date
> for embedded Annex I and **2027-08-02** is the superseded statutory baseline. (This mirrors
> `attest.REGULATORY_CLOCK`, which is embedded in the payload of every signed attestation — plan
> against the clock, and re-read it rather than trusting a restatement of it.) The EU AI Act
> **Article 15** robustness/cybersecurity language remains the substantive *measurement* anchor
> (and still applies directly to non-machinery high-risk AI systems); for a robot, treat the
> Machinery Regulation + ISO 10218:2025 cyber-risk assessment as the *operative route* and Art. 15
> as the methodology it pulls in. Dates/routing are *indicative* — confirm against the final OJ text.

---

## What Provael measures (the evidence it produces)

A Provael run yields, under whichever predicate it was scored with — the documented default, or
a calibrated one from `provael calibrate` + `provael attack --calib`; every artifact says which:

- **Redirection rate** per attack and per **EAI** risk — the rate at which an attack drove the
  policy out of its safe envelope under that predicate — with a **95% Wilson CI** (episode-level;
  a task-clustered interval, where a sharded run's aggregate carries one, is named as such).
- **Benign baseline FPR** — the control: the `none` (un-attacked) rate under the *same*
  predicate. A calibrated run adds the benign false-positive rate its threshold was tuned to on a
  benign tuning split (`<= target-fpr`) — tuning data, not an untouched final evaluation.
- **The release decision** — under a named acceptance protocol, or `incomplete` / not assessed
  when none was named. It is a statement about the run, not a property of the measurement.
- **Per-risk tagging** — each attack carries its `EAIxx` id (see
  [The Embodied AI Security Top 10](../top10.md)).
- **Provenance** — per-task calibration artifact (predicate, target/achieved FPR, `n`, seed
  split) and a deterministic, reproducible config.
- **Machine-readable outputs** — `report.json`, **SARIF 2.1.0** (GitHub code scanning), and the
  ASR leaderboard.

These are *behavioural-susceptibility* measurements via templated attacks — not worst-case
certified bounds. See [Honest scope](#honest-scope-what-this-does-not-cover).

---

## Crosswalk — Provael evidence → frameworks

| Provael signal (EAI / metric) | EU AI Act (Reg. 2024/1689) | ISO 10218:2025 | NIST AI 100-2 / AI RMF | IEC 62443 |
|---|---|---|---|---|
| **EAI01** instruction jailbreak | Art. 15 — cybersecurity: resilience to attempts to alter use/outputs/performance | Cybersecurity / unauthorized-manipulation requirements *(indicative)* | Abuse / evasion (integrity) | Access control; use-control *(indicative)* |
| **EAI02** adversarial perception | Art. 15 — resilience to *adversarial examples* (inputs designed to cause mistakes) | Cybersecurity req. *(indicative)* | Evasion (integrity) | — |
| **EAI04** action-space integrity (freeze / trajectory hijack) | Art. 9 — risk management *(indicative)* + Art. 15 — resilience to manipulation of *outputs / performance* | ISO 10218-2:2025 — cyber: monitored-stop / motion-limit & integrity requirements *(indicative)* | Integrity violation (action-space integrity) | Control-system integrity / safety response *(indicative)* |
| **EAI05** indirect / embodied injection | Art. 15 — manipulation via crafted inputs | Cybersecurity req. *(indicative)* | Indirect prompt injection | Data integrity *(indicative)* |
| **Redirection rate + 95% CI under the run's predicate** (every row says which) | Art. 15 — *accuracy metrics declared* + robustness measurement; benchmarking methodology | Evidence for the cyber-risk assessment *(indicative)* | **AI RMF MEASURE** (measure risks) — needs the *calibrated* predicate; a gap under the default | Security level verification *(indicative)* |
| **Benign baseline FPR (control)** | Art. 15 — consistent performance; false-positive characterisation | — | AI RMF MEASURE (validity, reliability) | — |
| **EAI10** eval / observability gaps | Art. 72 — post-market monitoring *(indicative)* | Logging / diagnostics *(indicative)* | **AI RMF MANAGE** | — |
| **Red-team process + EAI taxonomy** | Art. 9 — risk-management system *(indicative)* | Cyber-risk assessment input *(indicative)* | **AI RMF GOVERN / MAP** | Risk assessment (Zone/Conduit) *(indicative)* |

EU AI Act **Article 15** ("Accuracy, robustness and cybersecurity") explicitly names resilience
to *data poisoning, model poisoning, adversarial examples (model evasion), and confidentiality
attacks* — which is the EAI taxonomy in regulatory language. The OWASP / MITRE columns of the
same mapping live in [top10 → Cross-framework crosswalk](../top10.md#cross-framework-crosswalk-corrected-verbatim-source-items).

### Functional safety — an input, never a determination

A robot's ML safety argument is assessed inside the classical functional-safety standards, so
Provael carries rows for them. **What the rows are is as important as that they exist:**

| Standard | What Provael supplies | What Provael does **not** supply |
|---|---|---|
| **IEC 61508** (E/E/PE functional safety) | EAI04 action-channel ASR + 95% Wilson CI + benign-FPR control + the mitigation report — evidence of behaviour under adversarial input, as an **input** to the systematic-capability argument | **No SIL.** No determination, estimate, or implication of one |
| **ISO 13849-1/-2** (safety-related parts of control systems) | The same evidence, filed as fault cases a Part 2 validation plan can cite | **No Performance Level.** No PL, PLr, MTTFd, diagnostic coverage, or CCF |
| **ISO/IEC TR 5469:2024** (AI & functional safety) | ASR + benign-FPR control as one input to the AI-safety lifecycle | No AI-safety lifecycle conclusion |
| **ISO 25785-1** (dynamically stable robots) | The humanoid family — `balance_spoof`, `whole_body_hijack`, `stride_freeze` — on the whole-body suite | **Nothing conformity-shaped: the standard is an ISO/TC 299 Committee Draft (CD registered 8 May 2026) and is not published.** The row is anticipatory positioning, and the suite is stub-validated with no real-model transfer claimed |

A Performance Level is determined from architecture, MTTFd, diagnostic coverage and CCF by the
designer and confirmed by validation. **An attack-success rate is none of those inputs and must
never be presented as one.** These rows exist because an integrator's file already names these
standards — see the [Halos / ANAB integrator card](../crosswalk/halos-integrator.md) — not because
Provael has an opinion about the determination.

### Automotive cybersecurity — a type-approval regime with its own auditor

A road vehicle with a learned component is already inside UN Regulation No. 155, which has applied in
the EU to new vehicle types since 6 July 2022 and to all new registrations since 7 July 2024
(Regulation (EU) 2019/2144, Annex II row D4). Its audit is a cycle rather than a date: the
Certificate of Compliance for a Cyber Security Management System is valid for a maximum of three
years (para. 6.7). ISO/SAE 21434:2021 is the engineering standard those audits lean on. Provael maps
to neither as conformity.

| Instrument | What Provael supplies | What Provael does **not** supply |
|---|---|---|
| **UN R155** para. 7.2.2.2(e), 7.3.3, 7.3.6 | A seeded, manifest-bound run as one record of a CSMS testing process; measured rates per risk, with interval and benign control, for the learned component's rows of the exhaustive risk assessment; one test among the set that verifies mitigations before approval | **No type approval and no CSMS certificate.** Both are granted by an Approval Authority. Nothing here is a vehicle-level test; every episode is a simulation rollout of the policy alone |
| **ISO/SAE 21434:2021** Clause 15, Clause 10 | Attack-feasibility and impact evidence with a denominator for the TARA; verification evidence for a cybersecurity requirement placed on the learned component, re-run on every retrain | **Clause 11 (cybersecurity validation) is not mapped.** It validates an item at the vehicle level, and a simulated, component-level result does not reach it |

Dates verified against the Official Journal text of R155 (CELEX 42021X0387), the consolidated text of
Regulation (EU) 2019/2144 and the ISO catalogue on 18 September 2026. Where the regime and the
Machinery Regulation could both apply, which one binds a given machine is a question for the
manufacturer's regulatory counsel, not for a red-team tool.

---

## Evidence map — requirement → what to attach

| Requirement (paraphrased) | Provael artifact that evidences it |
|---|---|
| EU AI Act Art. 15 — declare accuracy/robustness metrics & methodology | `report.json` + this run's config (deterministic); the calibrated redirection rate + CI per EAI risk |
| EU AI Act Art. 15 — resilience to manipulation/adversarial inputs | Per-attack results across EAI01/02/05 with the benign-FPR control; SARIF for the security review |
| EU AI Act Art. 9 / ISO 10218 cyber-risk assessment | The EAI risk list as the threat catalogue + measured rates per risk |
| EU Machinery Regulation 2023/1230 — "protection against corruption" + safety-function AI (conformity input) | Measured redirection rate per EAI risk as input to the mandatory cyber-risk assessment; SARIF for the security file *(indicative)* |
| EU AI Act Art. 72 — post-market monitoring | Re-run on each model/checkpoint update; track redirection rate over time (leaderboard) |
| NIST AI RMF MEASURE | Calibrated rate + CI + benign FPR (a measured, controlled metric, not a vibe) |
| Auditor wants reproducibility | Seed, config, and per-task calibration artifact (target vs tuning-split FPR, fit/tuning seed split — no untouched evaluation split) |

---

## Honest scope — what this does *not* cover

- **Adversarial security only.** Functional/mechanical safety (ISO 10218 safety clauses, ISO
  13482, ISO/TS 15066) and non-adversarial reliability are **out of scope** — see the
  [TOP10 scope box](../top10.md#scope-read-this-its-deliberate).
- **Evidence, not conformity.** EU AI Act conformity also requires a quality-management system,
  technical documentation, human oversight, logging, and more. Provael covers the **Art. 15
  robustness/cybersecurity *testing-evidence* slice**, not the whole obligation.
- **Behavioural, not worst-case.** Today's attacks are templated/auditable, not gradient/search-
  optimised; one policy (SmolVLA) and one suite (LIBERO) ship. Treat results as a floor on
  susceptibility, not a certified bound. See the README's "Scope and honest limitations."
- **Sub-clause precision is indicative.** Rows marked *(indicative)* name the relevant standard
  area; confirm the exact clause against the full standard text for an audit.

---

## Shipped: `provael report --format compliance` (v0.5.0)

The crosswalk above is the spec for the generator that turns a run into an auditor-ready evidence
report. **Shipped in v0.5.0.**

```bash
provael report --in runs/calib --format compliance --out report.compliance.json  # evidence JSON
provael report --in runs/calib --format compliance --out report.compliance.md    # auditor-readable
provael report --in runs/calib --format compliance                               # JSON to stdout
```

- **Input:** an existing run's `report.json`. Calibrated runs carry the redirection rate + 95% CI
  + benign FPR + per-task calibration metadata; uncalibrated runs are accepted and surface the
  requirements that need a calibrated/controlled metric as **gaps**. No attacks are re-run, so the
  path is CPU/stub-runnable in CI and byte-deterministic.
- **Output:** a per-requirement evidence document (JSON + Markdown): each mapped control → the
  Provael signal, the run's measured result (redirection rate + 95% CI + benign FPR + per-EAI
  breakdown + calibration target), an `evidence-present` / `gap` status with a reason, the
  honest-scope caveats, and references to the underlying artifacts (`report.json` / `report.sarif`).

**Evidence schema** — the measured `result` is carried once at the top; `entries[]` is one object
per mapped control:

```json
{
  "key": "eu-ai-act:art15",
  "framework": "EU AI Act (Regulation (EU) 2024/1689)",
  "framework_id": "eu-ai-act",
  "control_id": "Article 15",
  "control_title": "Accuracy, robustness and cybersecurity",
  "provael_signal": "Redirection rate + 95% CI per EAI risk under the run's predicate (calibrated or the documented default — the row says which), with the benign-FPR control; SARIF for the security review",
  "status": "evidence-present",
  "gap_reason": null,
  "indicative": false,
  "evidence_refs": ["report.json", "report.json#/by_attack", "report.sarif"],
  "caveats": ["adversarial-only", "evidence-not-certification", "behavioural-not-worst-case"],
  "predicate": "default (uncalibrated)"
}
```

`status` is advisory — `evidence-present` means this run produced the artifact a reviewer would
attach for that control; `gap` means it did not (an uncalibrated run where the control needs a
calibrated predicate, a missing benign control, or a longitudinal / observability requirement a
single run can't satisfy, each with a `gap_reason`). It is never an assertion of legal compliance,
and it never means the whole standard or regulation is satisfied. `predicate` travels on every row
so a row cannot describe evidence the run did not produce — an uncalibrated run is described as
uncalibrated in the row, not only in a footer. The report also carries `acceptance`: the release
decision under a named protocol (verdict, protocol name and digest, reasons), or not assessed.

---

## References

Verified anchors (read the full text for clause-level audit use):

- EU AI Act (Regulation (EU) 2024/1689) — **Article 15, Accuracy, robustness and cybersecurity**:
  <https://artificialintelligenceact.eu/article/15/>
- **EU Machinery Regulation (Regulation (EU) 2023/1230)** — applies 2027-01-20; new
  "protection against corruption" cybersecurity requirement; AI safety-functions → high-risk →
  third-party conformity assessment. The 2026 **Digital Omnibus** routes AI-specific robustness
  for machinery here via delegated acts (indicative; confirm against the final OJ text):
  <https://eur-lex.europa.eu/eli/reg/2023/1230/oj>
- **ISO 10218-1:2025** Robotics — Safety requirements — Part 1 (incl. cybersecurity /
  unauthorized-access requirements): <https://www.iso.org/standard/73933.html>
- **ISO 10218-2:2025** — Part 2 (robot applications & cells): <https://www.iso.org/standard/73934.html>
- **NIST AI 100-2e2025** (Adversarial ML taxonomy) and the **NIST AI Risk Management Framework**
  (AI 100-1; GOVERN / MAP / MEASURE / MANAGE).
- **IEC 62443** — industrial automation & control systems security.
- **IEC 61508** — functional safety of E/E/PE safety-related systems. Provael is an input to the
  systematic-capability argument and determines **no SIL**.
- **ISO 13849-1/-2** — safety-related parts of control systems (design; validation). Provael
  determines **no Performance Level**.
- **ISO 25785-1** — industrial mobile robots, dynamically stable robots. **ISO/TC 299 Committee
  Draft (CD registered 8 May 2026); not published.** No publication date is committed by ISO;
  secondary trackers read the schedule as around 2028, not 2026–2027 as this page once said. The
  row is anticipatory and cites no clause, because there is no stable clause to cite.

See also [top10](../top10.md) (the risk taxonomy + OWASP/MITRE crosswalk) and
[SAFETY.md](https://github.com/provael/provael/blob/main/SAFETY.md) (responsible-use scope).

---

*Independent · not legal advice · evidence, not certification. PRs and corrections welcome via
the [Top 10 issue form](https://github.com/provael/provael/issues/new?template=top10-feedback.yml).*
