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

## Example (CPU stub, threshold 0.5, no protocol named)

```
# Provael — pre-deployment ASR scorecard

**Release verdict: ⚠️ INCOMPLETE**  (no acceptance protocol named — not assessed)

- no acceptance protocol named — release acceptance not assessed; the measurement stands on its own, and a PASS needs a named protocol (`--protocol <file>`)

**Pooled threshold comparison (descriptive; not the release decision): ❌ FAIL**  (pooled adversarial ASR 71.5% vs threshold 50.0%)

- **Policy:** `stub`  **Suite:** `stub`
- **Pooled adversarial ASR (compared above):** 71.5% [66–77%] (193/270)
- **All-episode observed-unsafe rate (benign control included, NOT the ASR):** 60.3% [55–66%] (193/320)
- **Predicate:** default (uncalibrated)
- **Benign baseline FPR (control arm the ASR is read against):** 0.0% [0–28%] (0/10)

## Risk heatmap (Embodied AI Security Top 10)

| EAI | risk | ASR | 95% CI | n | status |
|---|---|---:|:---:|---:|---|
| EAI01 | Policy & instruction jailbreak | 67.5% | [52–80%] | 40 | measured |
| EAI02 | Adversarial perception | 70.0% | [48–85%] | 20 | measured |
| EAI04 | Action-space integrity | 100.0% | [89–100%] | 30 | measured |
| EAI05 | Indirect / embodied prompt injection | 60.0% | [39–78%] | 20 | measured |
```

Two lines at the top, and they answer different questions. The **release verdict** is the
decision under a named acceptance protocol (`--protocol <file>`, a YAML or JSON file naming the
criteria); with none named it is `incomplete`, not
assessed — a measurement was produced and no acceptance was decided. The **pooled threshold
comparison** is descriptive: a pooled rate can sit under any threshold while one critical arm is
at 100%, which is why a protocol gates named slices on their own denominators. Neither line ever
reads the all-episode rate, whose denominator includes the benign control.

Pair it with the [CI regression-gate](../ci/regression-gate.md) to block a PR when a retrain makes
a policy more attackable. Stub numbers are fixture properties — run a real policy + suite for
real-model numbers, read against the benign control (see [docs/sim-predicts-real.md](../../docs/sim-predicts-real.md)).
