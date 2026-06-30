# Provael SARIF in AppSec aggregators

Provael emits **SARIF 2.1.0** (`provael attack --format sarif` / `--sarif-out`), so it lands in
any tool that ingests SARIF — not just GitHub code scanning. Each finding is tagged with its
`EAIxx` rule id.

## DefectDojo

DefectDojo has a built-in SARIF parser, making Provael a first-class finding source in your AppSec
aggregator. Import `provael.sarif` with scan type **"SARIF"** (UI: *Findings → Import Scan
Results*, or the API):

```bash
curl -X POST "https://<dojo>/api/v2/import-scan/" \
  -H "Authorization: Token $DOJO_TOKEN" \
  -F "scan_type=SARIF" -F "engagement=<id>" -F "file=@provael.sarif"
```

DefectDojo reads `runs[].tool.driver.name` (→ "Provael") and honours `partialFingerprints` for
dedup across runs. Docs: https://docs.defectdojo.com/supported_tools/parsers/file/sarif/

## SonarQube

SonarQube imports SARIF 2.1.0 as external issues — add to `sonar-project.properties`:

```
sonar.sarifReportPaths=provael.sarif
```

Docs: https://docs.sonarsource.com/sonarqube-server/latest/analyzing-source-code/importing-external-issues/importing-issues-from-sarif-reports/

## GitLab / Azure DevOps

See [`gitlab-provael.yml`](../ci/gitlab-provael.yml) (native `artifacts:reports:sarif`) and
[`azure-pipelines-provael.yml`](../ci/azure-pipelines-provael.yml) (SARIF Scans Tab extension).
