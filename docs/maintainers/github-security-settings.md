# GitHub security settings (admin-only — NOT enforceable from code)

These controls live in GitHub's admin UI/API, not in the repo, so this file **documents** them and
records who verified each. **Do not tick a box you have not actually confirmed** through authorized
access — an unverified checklist is worse than none.

> Status legend: `[ ]` not verified · `[x] (verified <handle> <date>)` confirmed in the admin UI.

## Branch protection — `main`

- [ ] Require a pull request before merging (no direct pushes)
- [ ] Require the CI status check (ruff + mypy + pytest) to pass
- [ ] Require the docs-strict + evidence-integrity checks to pass
- [ ] Require branches to be up to date before merging
- [ ] Require conversation resolution before merging
- [ ] Require review from CODEOWNERS (when a second qualified maintainer exists)
- [ ] Block force pushes
- [ ] Block branch deletion
- [ ] Include administrators in the above

## Tags & releases

- [ ] Protect release tags (`v*`) from deletion / re-pointing
- [ ] Require signed commits/tags (if adopted)
- [ ] PyPI environment protection: `pypi` environment restricted to the release workflow, with
      required reviewers; Trusted Publishing (OIDC) configured, no long-lived PyPI token

## Scanning & alerts

- [ ] Secret scanning enabled
- [ ] Secret scanning push protection enabled
- [ ] Dependabot alerts enabled (see `.github/dependabot.yml` for update PRs)
- [ ] Dependabot security updates enabled
- [ ] CodeQL / OpenSSF Scorecard reviewed (see `.github/workflows/scorecard.yml`)

## Access & apps

- [ ] Audit installed GitHub Apps and their scopes
- [ ] Least-privilege collaborator/team access

## Why this is a document, not code

The repo can enforce workflow-level permissions, timeouts, `persist-credentials: false`, Dependabot,
and CODEOWNERS — those are checked in. It **cannot** enforce branch protection, environment
reviewers, or secret-scanning from within a workflow. A reviewer must confirm each item above and
sign it off; otherwise the control does not exist.
