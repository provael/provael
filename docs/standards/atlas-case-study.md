# MITRE ATLAS case-study draft — embodied VLA red-team

> **Disposition, 2 September 2026.** A submission **was sent** — one proposed technique plus one
> case study, emailed to `atlas@mitre.org` on **8 August 2026**, still awaiting a response. The
> exact file is committed at
> [`atlas-submission-2026-08-08.yaml`](atlas-submission-2026-08-08.yaml).
>
> This page is the **human-readable mirror** of that work, and it is still a draft in one specific
> sense: the *pull-request* route against `mitre-atlas/atlas-data` has not been taken. That is a
> different artifact, not a resend — ATLAS v6 objects carry `name` / `description` / `references` /
> `platforms` and keep tactic membership in a separate `relationships` table, so the memo fields our
> emailed file uses (`why_not_covered_by_existing_techniques`, `honest_scope_limits`, `detection`)
> would have to be split into a technique object plus an `achieves` edge, and signed off with the
> DCO. The conversion is mechanical and is described in
> [the standards index](index.md#validated-against-the-v6-object-model-12-august-2026); opening the
> PR is gated on sign-off.

ATLAS (https://atlas.mitre.org) is the adversarial-ML ATT&CK analog. Its embodied coverage is thin —
`robot`, `embodied`, `vision-language-action`, `actuator` and `drone` each return zero matches across
the whole `dist/v6/ATLAS-2026.07.yaml` corpus (178 techniques, 68 case studies, 16 tactics, fetched
8 August 2026) — which is the opening this proposes to fill.

## Case study: instruction-jailbreak of a VLA policy in simulation

- **Summary.** A templated instruction reframe (RoboPAIR-style) redirects a Vision-Language-Action
  policy's end-effector out of its benign envelope in simulation, measured by Provael as an Attack
  Success Rate with a benign-FPR control.
- **Target.** Open VLA policy (e.g. SmolVLA) on the LIBERO benchmark.
- **Procedure.** `provael reproduce robopair --policy smolvla --suite libero` (gated, GPU).
- **Typed `exercise`, not `incident`.** No fielded system was attacked and no robot moved.

## ATLAS technique mapping (proposed)

**This table is a mirror, not a source.** The mapping lives on `provael.eai.CATALOG` as
`atlas_techniques` and reaches consumers two ways: SARIF rules carry it as
`properties.atlasTechniques` (`src/provael/sarif.py`), and
`provael crosswalk --target atlas` emits the machine-readable version. Regenerate rather than
hand-edit, and see the note under the table on what keeps the two in agreement.

Phrasings are descriptive `tactic → technique`. **No `AML.TXXXX` identifiers are cited**: quoting a
technique id we have not verified against the live matrix would manufacture false precision.

`mapping_status` values, all three of which are used below:

| value | meaning |
| --- | --- |
| `proposed-mapped` | an on-point ATLAS technique exists; the wording here is ours, and neither reviewed nor endorsed by MITRE |
| `proposed-gap` | no on-point ATLAS technique exists; the row proposes an extension, and says so |
| `none-yet` | nothing is mapped and nothing is proposed — see the reason under the table |

| EAI | Risk | ATLAS tactic → technique | `mapping_status` |
| --- | --- | --- | --- |
| EAI01 | Policy & instruction jailbreak | ML Attack Staging → prompt-injection / jailbreak of an ML-driven agent | `proposed-mapped` |
| EAI02 | Adversarial perception | Evasion → adversarial example in the perception channel (craft adversarial data) | `proposed-mapped` |
| EAI03 | Model & pipeline poisoning, backdoors & supply chain | Persistence → backdoor the ML model; ML Supply Chain Compromise → poison an open-weights checkpoint | `proposed-mapped` |
| EAI04 | Action-space integrity | Impact → manipulate / deny the agent's actuation | `proposed-gap` |
| EAI05 | Indirect / embodied prompt injection | Execution → indirect prompt injection via the environment | `proposed-mapped` |
| EAI06 | Cross-domain safety misalignment (the embodiment gap) | Impact → unsafe embodied action under a language-benign instruction | `proposed-gap` |
| EAI07 | CPS, firmware, comms & teleoperation compromise | — none proposed — | `none-yet` |
| EAI08 | Identity, access & excessive autonomy | Privilege Escalation → excessive agency / self-authorized guarded action | `proposed-gap` |
| EAI09 | Model & data confidentiality | Exfiltration → model extraction / membership inference via the inference interface | `proposed-mapped` |
| EAI10 | Insufficient evaluation, observability & incident response | — none proposed — | `none-yet` |

**All ten rows appear, including the two that map to nothing.** An absent row reads as an oversight;
an explicit `none-yet` reads as an answer. The two are not a backlog:

- **EAI07 — CPS, firmware, comms & teleoperation compromise.** Out of scope for simulation by design,
  and a boundary rather than a gap. Faithful coverage means real firmware, real radio / ROS-DDS
  traffic and real teleoperation sessions — CVE-class work against physical infrastructure, and
  Provael ships no exploit tooling (see `SAFETY.md`). ATLAS is the wrong taxonomy for it too: that
  layer is assessed with IEC 62443 and ATT&CK-for-ICS. **A clean Provael run says nothing about this
  risk.**
- **EAI10 — Insufficient evaluation, observability & incident response.** Not attackable: there is no
  policy input that attacks the absence of a process. Provael sits on the mitigation side, and only
  partly — a signed run report, its scorecard and the per-checkpoint regression gate evidence the
  *evaluation* limb, not the observability or incident-response limbs, which are runtime and
  organisational. This category never carries an ASR; a number here would be a category error.

`tests/test_atlas_case_study_mapping.py` pins this table to the catalog: every EAI id appears
exactly once, each row's `mapping_status` is the one the catalog implies, and no status outside the
three defined above is used. The test exists because this page duplicates data that has a generator
— a hand-maintained mirror with no guard is how it lost EAI07 and EAI10 in the first place.

## Evidence

The Provael run emits an AVID record (`provael export --format avid`) and OSCAL
assessment-results; ATLAS case-study fields (summary, target, procedure, references) are drawn from
those plus [docs/top10.md](../top10.md). RoboPAIR (arXiv:2410.13691) and BadRobot
(arXiv:2407.20242) are the canonical robot-jailbreak references to align to.
