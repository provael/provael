# GitHub security settings (admin-only — NOT enforceable from code)

These controls live in GitHub's admin UI/API, not in the repo, so this file **documents** them and
records who verified each. **Do not tick a box you have not actually confirmed** through authorized
access — an unverified checklist is worse than none.

> Status legend: `[ ]` not verified · `[x] (verified <handle> <date>)` confirmed in the admin UI.

## The bot App — how automation writes to a protected `main`

Six scheduled or dispatched workflows commit to `main` (`freshness.yml`, `coverage-badge.yml`,
`leaderboard-restamp.yml`, `leaderboard-rebuild.yml`, `gpu-scheduled.yml`, `gpu-arm.yml`). A
ruleset that requires a pull request and passing checks blocks a direct push from `GITHUB_TOKEN`,
and `GITHUB_TOKEN` cannot be a bypass actor. Since 20 September 2026 those six jobs mint a
short-lived installation token of the repository's own GitHub App
(`actions/create-github-app-token`, SHA-pinned) and check out and push with it; the App is the
ruleset's **only** bypass actor — no human role is on the list, so the maintainer goes through a
pull request like anyone else. The jobs fail loudly when the two secrets are absent; there is no
fallback to `GITHUB_TOKEN`, because a fallback that pushes nothing and exits green is how a badge
goes stale unnoticed.

Set up once, by an org owner (UI only — none of this can be done from a workflow):

1. Settings → Developer settings → GitHub Apps → **New GitHub App**. Name it after the repository
   (the bot's commits keep `github-actions[bot]` as author; the App is the pusher). Webhook off.
   Repository permissions: **Contents: read and write**, **Metadata: read**. Nothing else — no
   workflows, no administration, no secrets.
2. Generate a private key; note the **App ID**.
3. Install the App on **`provael/provael` only**.
4. Repository secrets: `PROVAEL_BOT_APP_ID` (the App ID) and `PROVAEL_BOT_PRIVATE_KEY` (the PEM,
   whole file).
5. Add the App as a bypass actor on the `main` ruleset (actor type *Integration*, bypass mode
   *always*).

An App push **does** trigger `push` workflows, unlike a `GITHUB_TOKEN` push. The four commits
that land in `watch/**` or `results/` carry `[skip ci]` (each would otherwise re-trigger the
freshness refresh); the two leaderboard commits deliberately do not, so CI checks the board that
was just rebuilt or re-stamped. The comment beside each `git commit` says which and why.

- [ ] App created, installed on this repository only, secrets set
- [ ] App is the ruleset's only bypass actor

## Branch protection — `main`

- [ ] Require a pull request before merging (no direct pushes) — *waits for the bot App below; the
      six pushing workflows fail on a protected main until its secrets exist*
- [ ] Require **every** CI status check to pass. The `check` job is a matrix over the interpreters
      `pyproject.toml` claims, so it reports one context per leg — `ruff + mypy + pytest (CPU, no
      lerobot, Python 3.12)` and the same for 3.13. Requiring one leaves the other advisory, and
      a leg added later is not required until someone comes back here.
- [ ] Require the docs-strict + evidence-integrity checks to pass
- [x] Require linear history (verified sattyamjjain 2026-09-20 — ruleset `main`, `required_linear_history`, active;
      merge commits are not accepted, rebase/squash only)
- [ ] Require branches to be up to date before merging — *with the required checks, once the App exists*
- [ ] Require conversation resolution before merging
- [ ] Require review from CODEOWNERS (when a second qualified maintainer exists)
- [x] Block force pushes (verified sattyamjjain 2026-09-20 — ruleset `main` id 19765152, `non_fast_forward`, active)
- [x] Block branch deletion (verified sattyamjjain 2026-09-20 — ruleset `main`, `deletion`, active)
- [x] Include administrators in the above (verified sattyamjjain 2026-09-20 — the ruleset has no bypass actor;
      the bot App becomes the only one when it is created)

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
- [x] CodeQL default setup enabled for this repository (verified sattyamjjain 2026-09-20 —
      `code-scanning/default-setup` state `configured`, default suite); Scorecard runs weekly
      (`.github/workflows/scorecard.yml`) — re-read after the ruleset gains the PR and checks rules

## Repository presentation (UI only)

Moved here from a reader-facing comment block in `docs/community.md` on 20 September 2026; the
topics and labels are set by API in the same pass, the two items below cannot be.

- [ ] Social preview image uploaded (`docs/assets/social_preview.png`, 1280×640): Settings →
      General → Social preview → Edit → Upload
- [ ] Discussions categories **Top-10 RFC** and **Results** created beside the default six
      (Discussions → categories → New category); the RFC page and the community page link to them
- [x] Repository topics include `eu-ai-act` and `machinery-regulation` beside the existing set
      (verified sattyamjjain 2026-09-20 via `gh repo edit --add-topic`; 20 topics)
- [x] Labels `attack-family` and `assessment` exist for the issue forms (verified sattyamjjain
      2026-09-20, `gh label list`)
- [x] Merged head branches are deleted automatically (`delete_branch_on_merge`, verified sattyamjjain
      2026-09-20); the 22 merged branches that predated it were deleted the same day

## Access & apps

- [ ] Audit installed GitHub Apps and their scopes
- [ ] Least-privilege collaborator/team access

## Why this is a document, not code

The repo can enforce workflow-level permissions, timeouts, `persist-credentials: false`, Dependabot,
and CODEOWNERS — those are checked in. It **cannot** enforce branch protection, environment
reviewers, or secret-scanning from within a workflow. A reviewer must confirm each item above and
sign it off; otherwise the control does not exist.
