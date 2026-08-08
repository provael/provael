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
| [MITRE ATLAS case study](atlas-case-study.md) | Draft (the human-readable version) |
| [MITRE ATLAS submission YAML](atlas-submission-2026-08-08.yaml) | **Prepared 8 August 2026** — one technique + one case study, emailed to atlas@mitre.org. Pending review. |
| [OWASP Agentic Top-10 — embodied annex](owasp-asi-embodied.md) | Draft |
| [Directory listings & awesome-list PRs](listings.md) | Prepared |

### What was submitted to MITRE ATLAS, and when

**Prepared 8 August 2026**, for email to `atlas@mitre.org`: one proposed technique (*Embodied Action
Redirection via Instruction Reframing*) and one case study, typed **exercise** rather than incident —
ATLAS scope admits a red-team exercise, and no fielded system was attacked and no robot moved.

The exact file submitted is committed at
[`atlas-submission-2026-08-08.yaml`](atlas-submission-2026-08-08.yaml) so the submission is
reproducible and its date is on the record rather than in someone's sent folder.

The argument, verified against **`dist/v6/ATLAS-2026.07.yaml`** — the current data release
(collection version **2026.07**), `mitre-atlas/atlas-data`, fetched 8 August 2026: the strings
`robot`, `embodied`, `vision-language-action`, `actuator` and `drone` each return **zero** matches
across the entire corpus — **178 techniques, 68 case studies, 16 tactics**.

The file matters, and this was checked against the wrong one first. `dist/ATLAS.yaml` still
self-reports version `5.6.0` and holds 170 techniques and 57 case studies; it is a smaller legacy
distribution, not the current release. Citing it at a reviewer would have understated their own
corpus by 8 techniques and 11 case studies — the fastest way to have a submission dismissed is to
be visibly working from a stale snapshot of the thing you are proposing to extend. The three physical-world entries that do exist concern physical *access* to a system or
physical modification of an *input*, not corruption of a policy's *action output*. Meanwhile the
corpus already carries AI-agent tool-poisoning material, and a VLA policy is the same tool-call
boundary with a gripper on the end.

No proposed `AML.T` identifier is included. Assigning one is MITRE's to do, and inventing an id in a
submission undermines the rest of the file.

Status is **submitted-and-pending**, which is a state a reader can check. It will be updated here
when ATLAS responds, including if the answer is no.

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
