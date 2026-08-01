# Standards & external mappings

Pages that place Provael next to something outside it — a published benchmark, a standards body's
taxonomy, someone else's numbers. They exist so a reader can check the claim against a source
rather than take it on trust.

Every row on every page here carries a globally resolvable identifier — an arXiv ID, a CVE, or a
URL. That is enforced, not aspirational: `tests/test_citations_resolvable.py` fails the build on a
row that cites nothing. A figure whose source cannot be checked is **withheld**, and the
withholding is documented where the row would have gone.

## Drafts submitted or prepared for external bodies

| Page | Status |
| --- | --- |
| [MITRE ATLAS case study](atlas-case-study.md) | Draft |
| [OWASP Agentic Top-10 — embodied annex](owasp-asi-embodied.md) | Draft |
| [Directory listings & awesome-list PRs](listings.md) | Prepared |

## Comparison against the published record

| Page | What it answers |
| --- | --- |
| [Published attack results on VLA policies](published-asr-baselines.md) | Which published figures are comparable to a Provael ASR — and which are not |

The comparability column on that page is the page. Most published VLA attack figures measure
**task-success degradation** ("the policy stopped completing the task"), while a Provael ASR
measures **envelope breach**. A policy that fails safely scores near-100% on the first and 0% on
the second, so printing the two in one column would be a lie regardless of which looked better.

## Crosswalks

Mappings onto an external frame live in [crosswalk/](../crosswalk/README.md) — per-persona cards,
plus the RoboJailBench and ForesightSafety-VLA crosswalks. A crosswalk states comparability as a
field rather than letting adjacency imply it.
