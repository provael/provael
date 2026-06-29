# CI integrations

Drop-in continuous-integration examples that run a Provael red-team gate and publish findings.

| File | Platform | What it does |
| --- | --- | --- |
| [`github-actions.yml`](github-actions.yml) | GitHub Actions | Runs the gate on push/PR, uploads SARIF to GitHub code scanning, fails the job past an ASR threshold. Uses the reusable `provael/provael` Action. |

Copy `github-actions.yml` into a robot/VLA repo at `.github/workflows/provael.yml`. The default
`stub` policy + suite run on a **CPU** runner (a fast smoke test of the gate wiring); the
commented `redteam-real` job shows the GPU + `[lerobot]` path for a real policy.

> More CI platforms (GitLab CI, Azure Pipelines) and SARIF aggregators (DefectDojo, SonarQube)
> land in a later pass.
