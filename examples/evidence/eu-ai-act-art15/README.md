# EU AI Act Article 15 — robustness evidence pack (worked example)

A worked example of turning one Provael run into the **adversarial-robustness testing evidence**
Article 15 expects, mapped clause-by-clause. Read [docs/COMPLIANCE.md](../../../docs/COMPLIANCE.md)
first for the regulatory routing (post-Digital-Omnibus, robots route via the Machinery Regulation
+ ISO 10218:2025; Art. 15 remains the measurement anchor).

## Generate it

```bash
# 1. Calibrate a per-task predicate (benign-FPR controlled), then run with the control.
provael calibrate --policy stub --suite stub --seeds 20 --out calib
provael attack --policy stub --suite stub --calib calib \
    --attacks none,instruction,visual,injection,action --episodes 10 --out runs/art15

# 2. Emit the evidence artifacts.
provael report --in runs/art15 --format compliance --out report.compliance.md  # auditor-readable
provael report --in runs/art15 --format oscal       --out report.oscal.json    # GRC-ingestible
provael report --in runs/art15 --format scorecard   --out scorecard.md         # one-page summary
```

## Article 15(5) ↔ Provael evidence

| Art. 15 names… | Provael evidence |
| --- | --- |
| **adversarial examples / model evasion** | visual (`patch`, `decoy_object`) + instruction families, ASR + 95% CI |
| **data poisoning / model poisoning** | backdoor-trigger reproduction (`reproduce badvla`) — the threat-class run |
| **resilience / fail-safe under manipulation** | EAI04 action-integrity (`freeze`, `trajectory_hijack`) ASR |
| **consistent performance / accuracy declared** | benign-FPR control (the `none` baseline) + calibrated predicate |
| **measurement methodology (no harmonised standard yet)** | calibrated redirection rate + Wilson CI, following **ISO/IEC TR 24029** empirical robustness |

> **No harmonised robustness standard exists yet** (CEN-CENELEC JTC 21 targets Q4 2026), so this
> methodology follows ISO/IEC TR 24029 (statistical/empirical neural-network robustness). It is
> **evidence, not certification** — see the honest-scope caveats in the generated report.
