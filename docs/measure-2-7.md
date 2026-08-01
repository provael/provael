# NIST AI RMF — satisfying MEASURE 2.7 with Provael

NIST AI RMF organises trustworthiness into **GOVERN / MAP / MEASURE / MANAGE**. **MEASURE 2.7**
is "AI system security and resilience" — it expects *evaluated* adversarial/red-team testing, not
an assertion. A Provael run is a clean fit: a controlled, reproducible measurement that feeds
MANAGE.

## Walkthrough

```bash
provael calibrate --policy stub --suite stub --seeds 20 --out calib
provael attack --policy stub --suite stub --calib calib \
    --attacks none,instruction,visual,injection,action --episodes 10 --out runs/measure
provael report --in runs/measure --format oscal --out report.oscal.json   # GRC-ingestible
```

## How it maps

| AI RMF function | What Provael provides |
| --- | --- |
| **GOVERN / MAP** | The Embodied AI Security Top-10 (EAI01–10) as the mapped risk context (`report.json#/eai`) |
| **MEASURE 2.7** (security & resilience) | Calibrated redirection rate + 95% Wilson CI + benign-FPR control — a *measured, controlled* metric, not a vibe |
| **MANAGE** | Re-run per checkpoint; track ASR over time (leaderboard); regression-gate (examples/ci/regression-gate.md) |

Tag findings with **MITRE ATLAS** technique ids and the **NIST AI 100-2e2025** adversarial-ML
classes (evasion / poisoning / privacy) for cross-framework traceability — see
[COMPLIANCE.md](COMPLIANCE.md) and the OSCAL export (observations carry the EAI id; map those to
ATLAS in your GRC tool).

> Evidence, not certification. `n = 10` per attack is a screen — read the CIs, run more seeds for a
> stronger claim, and always read each rate against the benign control.
