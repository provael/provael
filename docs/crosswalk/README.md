# Per-persona compliance crosswalk cards

One card per robot category: **your obligation → the exact instrument & date → the Provael
artifact that evidences it.** Independent project, not legal advice; dates are *indicative* —
confirm against the primary text. See [COMPLIANCE.md](../COMPLIANCE.md) for the full crosswalk and
the 2026 Digital-Omnibus routing.

---

## Industrial / collaborative robot maker

| Obligation | Instrument · date | Provael artifact |
| --- | --- | --- |
| Cybersecurity risk assessment (mandatory) | **ISO 10218-1/-2:2025** (cyber clauses) | Measured ASR per EAI as a risk-assessment input (`report.compliance`) |
| Protection against corruption; AI safety-functions → 3rd-party conformity | **EU Machinery Regulation 2023/1230** · applies **2027-01-20** | `provael certify` Annex I Part A / Annex III dossier (OSCAL + HTML); SARIF + scorecard for the security file |
| Industrial control-system security levels | **IEC 62443** | Per-EAI ASR as control-system security evidence |

## Humanoid maker (the white-space)

| Obligation | Instrument · date | Provael artifact |
| --- | --- | --- |
| Balance / fall hazards of a legged machine | **ISO 25785-1** — ISO/TC 299 WG 12, **Working Draft, not published** (expected 2026–2027) | The humanoid family (`balance_spoof`, `whole_body_hijack`, `stride_freeze`) on the whole-body suite, emitted as an **anticipatory** dossier row (`iso-25785-1:dynamically-stable`) — not a conformity claim, and **stub-validated with no real-model transfer claimed** |
| Functional-safety assessment of your robot software | **IEC 61508**, **ISO 13849-1/-2**, **ISO/IEC TR 5469:2024** | EAI04 action-channel ASR + CI + benign control as an **input**; Provael determines **no SIL and no Performance Level** — see the [Halos / ANAB integrator card](halos-integrator.md) |
| Third-party conformity assessment of the machine you ship | **Machinery Reg. 2023/1230 Annex I Part A point 6** (embedded ML safety system) · applies **2027-01-20** | `provael certify` dossier; point 6 is the integrator's row, point 5 is the standalone component |
| AI robustness against manipulation | **AI Act Art. 15** (via Machinery Reg. delegated acts, by **2028-08-02**) | Calibrated redirection rate + 95% CI + benign FPR |
| Risk-management system | AI Act Art. 9 / ISO 12100 | EAI Top-10 as the threat catalogue + measured rates |

## Surgical / medical-robot maker

| Obligation | Instrument · date | Provael artifact |
| --- | --- | --- |
| AI-enabled device software robustness evidence | **FDA** AI-device guidance (draft **2025-01-07**); TPLC + PCCP | ASR + CIs as performance/robustness evidence in the submission |
| Post-market change control | PCCP | Scheduled re-runs; ASR tracked over time (leaderboard) |

## AV / AMR maker (hardest current deadline)

| Obligation | Instrument · date | Provael artifact |
| --- | --- | --- |
| Cybersecurity management system (type approval) | **UN R155 + R156 + ISO/SAE 21434** · **mandatory since Jul 2024** | ASR per EAI as CSMS test evidence |
| Autonomy safety case | **UL 4600 Ed. 3** | Provael ASR as a safety-case claim with evidence |
