# Maintainers

Runbooks for operating this project. They are public because nothing in them is secret and because
both exist to prevent a misunderstanding — a document written for that purpose has to be findable.

| Runbook | What it records |
| --- | --- |
| [GitHub security settings](github-security-settings.md) | Controls that live in GitHub's admin UI, not in the repo, and who verified each. An unverified checklist is worse than none — do not tick a box you have not confirmed. |
| [Hosted production requirements](hosted-production-requirements.md) | What a *real* operated signing service would require. `src/provael/hosted/` is an experimental reference surface, disabled by default, and must not be operated as one. |

Neither is a statement that the thing described exists. Both are written the other way round: they
record the gap, so the gap cannot be mistaken for a feature.
