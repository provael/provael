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
| [MITRE ATLAS submission YAML](atlas-submission-2026-08-08.yaml) | **SENT 8 August 2026** to atlas@mitre.org — one technique + one case study. Awaiting a response. |
| [OWASP Agentic Top-10 — embodied annex](owasp-asi-embodied.md) | Draft |
| [Directory listings & awesome-list PRs](listings.md) | Prepared |

### What was submitted to MITRE ATLAS, and when

**Sent 8 August 2026** to `atlas@mitre.org`: one proposed technique (*Embodied Action
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

### Validated against the v6 object model, 12 August 2026

Four days after sending, with no response yet, the artifact was validated rather than left to sit.
Fetched `dist/v6/ATLAS-2026.07.yaml` from `mitre-atlas/atlas-data`: **178 techniques** (77 carrying the
`AML.T####.###` sub-technique form), **68 case studies**, **16 tactics**, 37 mitigations and 284
relationship records.

**The object model is not the shape of our file, and that is a route decision rather than a defect.**
In v6, a technique carries only `name`, `description`, `references`, `created-date`, `modified-date`,
`platforms`, `id`, `maturity`, `uuid` and `object-type` — tactic membership and sub-technique parentage
live in the separate `relationships` table as `achieves` / `specializes` / `mitigates` / `employs`
edges, not as fields on the object. Our file carries submission-memo fields instead
(`why_not_covered_by_existing_techniques`, `honest_scope_limits`, `detection`), which is right for an
**email** to `atlas@mitre.org` and wrong for a **pull request** against `atlas-data`.

If the route becomes a PR, the conversion is mechanical and known: split the memo into a technique
object plus an `achieves` edge to the Impact tactic, move the argument prose into `description`, drop
the fields the schema does not carry, and sign off with the DCO (`git commit -s`, Signed-off-by
matching the commit author) which that repository requires on every contribution.

[`tests/test_atlas_submission.py`](https://github.com/provael/provael/blob/main/tests/test_atlas_submission.py)
now pins the properties that matter: the collection version is named, no `AML.T` id is invented, the
case study stays typed `exercise` rather than `incident`, its scope limits stay present, and this page
keeps recording the disposition. The committed file is what was emailed; the tests exist so a later
edit cannot quietly make that untrue.

### The gap, verified rather than asserted

The Impact tactic (`AML.TA0011`) in collection 2026.07 has **19 techniques and sub-techniques**:
Evade AI Model, Denial of AI Service, Erode AI Model Integrity, Cost Harvesting (+ Excessive Queries,
Resource-Intensive Queries, Agentic Resource Consumption), Spamming AI System with Chaff Data,
External Harms (+ Financial, Reputational, Societal, User Harm, AI Intellectual Property Theft),
Erode Dataset Integrity, Data Destruction via AI Agent Tool Invocation, and Machine Compromise
(+ Local AI Agent, AI Artifacts).

**Every one of them lands on an informational or economic surface.** `User Harm` is defined in their
own words as harms "including financial and reputational"; `Societal Harm` as outcomes reaching "the
general public"; `Machine Compromise` as code execution, credential theft and exfiltration. **None
names an actuator, a trajectory, or physical motion as the impact surface.**

That is the argument for the proposed technique, and it is now a checked claim rather than a
recollection: a policy can pass every text-level evaluation in the corpus and still emit a trajectory
that leaves its safe envelope, because no Impact technique describes the emitted action itself.

No proposed `AML.T` identifier is included. Assigning one is MITRE's to do, and inventing an id in a
submission undermines the rest of the file.

Status is **sent, awaiting a response** — a state a reader can check, and distinct from the two
states either side of it. It is not a standards reference, and it is no longer merely drafted.

This line said "emailed" for several hours before the email was actually sent. That was written ahead
of the fact and is corrected here rather than quietly left to become true. The distinction the whole
page turns on is between what has happened and what is planned, and the page has to hold itself to
it first.

It will be updated again when ATLAS responds, **including if the answer is no**.

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
