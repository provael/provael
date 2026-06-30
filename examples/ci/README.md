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
