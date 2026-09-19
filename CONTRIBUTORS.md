# Contributors

Who has contributed to this repository, in what capacity, and under which terms. Kept because
the question "who wrote this, and for whom" is asked of every project that changes hands, and the
answer should not have to be reconstructed from `git log`. Contribution terms are the
[Developer Certificate of Origin](https://developercertificate.org/) (DCO 1.1), stated in
[CONTRIBUTING.md](CONTRIBUTING.md); there is no CLA and no copyright assignment.

| Name | GitHub | Employer at the time of contribution | Contribution | Terms |
| --- | --- | --- | --- | --- |
| Sattyam Jain | [@sattyamjjain](https://github.com/sattyamjjain) | Contributes in a personal capacity as founder and maintainer; employed at Attri during 2026. Commits authored through 19 August 2026 carry a work e-mail address that was set in the local git configuration by mistake — [`.mailmap`](.mailmap) maps them to the personal identity for display and no commit was rewritten (attestations bind the source SHAs). | All code, documentation, results and infrastructure unless listed below | DCO; copyright retained |
| Hangtao Zhang | — | University of Pennsylvania | Co-author of the [Embodied AI Security Top 10](docs/top10.md) (EAI01 and the EAI06 cross-domain framing, from the BadRobot work). Documentation only; no code commits. | CC-BY-SA 4.0 (the Top 10 is a separate document) |
| dependabot[bot] | [@dependabot](https://github.com/dependabot) | GitHub | Dependency version bumps, each merged after CI | Automated; no copyrightable authorship claimed |
| github-actions[bot] | — | GitHub | Scheduled refreshes of committed artifacts (`watch/`, coverage badge, leaderboard re-stamps, results pushed by the GPU lanes), and — with an empty identity — the pre-2026-09 `mkdocs gh-deploy` commits on `gh-pages` | Automated; the workflows that produce them are in `.github/workflows/` |

## The DCO statement

Every human commit is expected to carry a `Signed-off-by:` trailer, which certifies the DCO 1.1
text: that the contributor wrote the change or has the right to submit it under the project's
licence (Apache-2.0), and understands that the contribution is public and retained indefinitely.
CI checks the trailer on every pull request (`dco` job in `.github/workflows/ci.yml`);
`make hooks` installs a local `prepare-commit-msg` hook that adds it. Commits before 20 September
2026 were made before that check existed, and 69 of the 438 commits up to then carry the trailer; the
rest are the maintainer's own and are covered by the top row of the table above.

## Adding yourself

Open a pull request that adds a row. Employer at the time of contribution is the field future
readers care about most; if you contribute under an employer's open-source policy, say so here and
link the policy if it is public.
