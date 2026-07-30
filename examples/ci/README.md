# CI integrations

Drop-in continuous-integration examples that run a Provael red-team gate and publish findings.

| File | Platform | What it does |
| --- | --- | --- |
| [`github-actions.yml`](github-actions.yml) | GitHub Actions | Gate on push/PR, upload SARIF to code scanning, fail past an ASR threshold (reusable `provael/provael` Action). |
| [`gitlab-provael.yml`](gitlab-provael.yml) | GitLab CI | Native `artifacts:reports:sarif` → GitLab Vulnerability Management + scorecard artifact. |
| [`azure-pipelines-provael.yml`](azure-pipelines-provael.yml) | Azure Pipelines | Publishes SARIF to the `CodeAnalysisLogs` artifact for the SARIF Scans Tab. |
| [`regression-gate.md`](regression-gate.md) | any | Block a PR when a retrain raises ASR vs the baseline checkpoint. |

Copy the file for your platform into the consumer repo. The default `stub` policy + suite run on a
**CPU** runner (a fast smoke test of the gate wiring); a real policy needs a GPU + the `[lerobot]`
extra (see the `redteam-real` job in `github-actions.yml`). SARIF also lands in DefectDojo /
SonarQube — see [../integrations/sarif-aggregators.md](../integrations/sarif-aggregators.md).

## Measuring a defense in CI (opt-in)

Set the Action's `defense` input to a registered defense name (`provael list-defenses`) and a
**second, defended arm** runs with byte-identical `policy`/`suite`/`attacks`/`episodes`/`seed`, then
`provael mitigation` compares the two. Empty by default, so existing pipelines are unaffected.

**Cost: this roughly doubles CI time.** It is commented out in `github-actions.yml` for that reason.

New outputs: `residual-asr`, `mitigation-verdict`, `mitigation-report`, `defense-log`. Both arms are
uploaded as artifacts.

**The gating rule.** `asr-threshold` keeps gating the **UNDEFENDED** adversarial ASR. A filter of
unproven real-model efficacy must not lower the number a release gate reads — that is exactly how a
team ships an unmitigated policy behind a text-and-clamp wrapper. `residual-asr` is published beside
it, never substituted for it.

The job fails on:

* **`rejected-benign-cost`** — mirroring `provael mitigation`'s own non-zero exit. A measure that
  degrades the benign task is rejected regardless of what it did to the attack-success rate.
* **`insufficient`** — the benign control is missing from an arm, so nothing can be concluded. The
  error names it. Nothing measured is not a pass, the same rule the empty-ASR branch of the gate
  already enforces.

`not-credited` does **not** fail the job: it is a real measured result and is reported as one.
