# Pre-deployment ASR scorecard

The one-page artifact to attach to a release ticket or fleet-OTA approval: a pass/fail verdict, an
EAI risk heatmap, per-attack ASR with 95% CIs, and the benign-FPR control.

```bash
# Generate it as part of a run...
provael attack --recipe full-sweep --format scorecard --out runs/scan
# ...or from an existing report, with your own pass/fail threshold:
provael report --in runs/scan --format scorecard --threshold 0.5 --out scorecard.md
```

Either path writes a self-contained Markdown page (`runs/scan/report.scorecard.md` from `attack`).
With no `--out` on `report`, the Markdown is printed to stdout — handy in CI logs.

## Example (CPU stub, threshold 0.5)

```
# Provael — pre-deployment ASR scorecard

**Verdict: ❌ FAIL**  (overall ASR 74.4% vs threshold 50.0%)

- Policy: `stub`  Suite: `stub`
- Overall ASR: 74.4% [65–82%] (67/90)
- Predicate: default (uncalibrated)

## Risk heatmap (Embodied AI Security Top 10)
| EAI | risk | ASR | 95% CI |
|---|---|---:|:---:|
| EAI01 | Policy & instruction jailbreak | 70.0% | [52–83%] |
| EAI02 | Adversarial perception | 70.0% | [48–85%] |
| EAI04 | Action-space integrity | 100.0% | [84–100%] |
| EAI05 | Indirect / embodied prompt injection | 60.0% | [39–78%] |
```

Pair it with the [CI regression-gate](../ci/regression-gate.md) to block a PR when a retrain makes
a policy more attackable. Stub numbers are fixture properties — run a real policy + suite for
real-model numbers, read against the benign control (see [docs/SIM_PREDICTS_REAL.md](../../docs/SIM_PREDICTS_REAL.md)).
