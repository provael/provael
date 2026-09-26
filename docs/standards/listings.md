# Directory listings & awesome-list PRs (ready to submit)

> **Status, 26 September 2026: sixteen listing PRs opened since 9 August — three merged, three
> closed unmerged, ten open — plus two issues on one list (ledger in §2).** The OECD.AI catalogue
> submission (§1) is not recorded here. Each item remains an external action (a submission or a PR
> to another repo) and a **manual step that requires explicit sign-off**; Provael™ does not submit
> these automatically.

Getting Provael into the recognised discovery layer is how a scanner goes from a repo to a standard.
Each entry below is drafted to paste directly into the target's form / PR, followed by the exact
steps to submit it.

## 1. OECD.AI Catalogue of Tools & Metrics for Trustworthy AI

The OECD.AI Catalogue lists trustworthy-AI tools (AVID is listed there). **Submit at:**
<https://oecd.ai/en/catalogue/tools/submit> · FAQ: <https://oecd.ai/en/catalogue/faq> · contribute
overview: <https://oecd.ai/en/catalogue/contribute>.

**Final entry copy (paste into the form fields):**

| Field | Value |
| --- | --- |
| **Name** | Provael |
| **One-liner** | Open, model-agnostic red-team scanner for Vision-Language-Action (VLA) robot policies in simulation; reports an Attack Success Rate with 95% Wilson confidence intervals, a benign false-positive control, and a clean-task-success (competence) control. |
| **Objective / description** | Provael perturbs the instructions and observations a VLA policy receives inside a simulator and measures how often those perturbations drive the policy into an unsafe state (ASR). Findings map to the Embodied AI Security Top 10 and export as SARIF / OSCAL / AVID / CycloneDX ML-BOM for a conformity or assurance file. CPU-first and deterministic; real-model runs are clearly labelled `measured-real-transfer` vs `stub-validated`. |
| **Type** | Technical → Process → testing / red-teaming / robustness evaluation |
| **Lifecycle stage** | Verify & validate; Deploy (pre-deployment scanning) |
| **Approach / usage** | Software / library + CLI (open source) |
| **Licence** | Apache-2.0 |
| **Link / repository** | <https://github.com/provael/provael> |
| **Documentation** | <https://docs.provael.com> |
| **Maintainer / contact** | Provael maintainers (from the repository) |
| **Related standards** | ISO 10218-2:2025, IEC 62443, EU Machinery Regulation 2023/1230, EU AI Act, NIST AI RMF (crosswalked in-repo) |

**Submission checklist (manual, on sign-off):**

1. Confirm the tool is public and `docs.provael.com` resolves (listings must point at something live).
2. Open <https://oecd.ai/en/catalogue/tools/submit> and sign in / create the submitter account.
3. Paste each field above; select the closest OECD taxonomy values offered by the form.
4. Note the current submission deadline shown on the form before sending; screenshot the confirmation.
5. Record the resulting catalogue URL back in this file once approved.

## 2. Awesome-list PRs (embodied-AI-safety / red-teaming discovery lists)

**Final one-line entry (paste into the list, alphabetised per the list's convention):**

> **[Provael](https://github.com/provael/provael)** — open, model-agnostic red-team scanner for VLA
> robot policies in simulation; Embodied AI Security Top-10 taxonomy, ASR + 95% CI + benign-FPR
> control, CI-native SARIF, and a public leaderboard. Apache-2.0.

**Candidate target lists:**

- `https://github.com/x-zheng16/Awesome-Embodied-AI-Safety`
- `https://github.com/AI45Lab/Awesome-Trustworthy-Embodied-AI`
- `https://github.com/user1342/Awesome-LLM-Red-Teaming` (embodied section)

**Per-PR checklist (manual, on sign-off — do this for each list):**

1. **Verify the repo is live and unarchived**, and read its `CONTRIBUTING` / format rules — awesome
   lists get renamed or archived, so confirm the URL before relying on it.
2. Fork, add the one-line entry in the section and alphabetical position the list uses; match its
   badge / punctuation style exactly.
3. Keep the description factual — no "first" / "SOTA" claims; the honest transfer caveat lives in the
   linked repo, not the one-liner.
4. Open the PR from a topic branch with a short, neutral title (e.g. `Add Provael (VLA red-team)`).
5. Record the PR URL back in this file.

### Submitted — ledger, states as of 26 September 2026

| Opened | List | PR | State |
| --- | --- | --- | --- |
| 2026-08-09 | x-zheng16/Awesome-Embodied-AI-Safety | [#8](https://github.com/x-zheng16/Awesome-Embodied-AI-Safety/pull/8) | open |
| 2026-08-12 | lfai/lfai-landscape | [#1415](https://github.com/lfai/lfai-landscape/pull/1415) | closed, not merged |
| 2026-08-12 | ottosulin/awesome-ai-security | [#386](https://github.com/ottosulin/awesome-ai-security/pull/386) | open |
| 2026-08-21 | LiQiiiii/Awesome-VLA-Safety | [#7](https://github.com/LiQiiiii/Awesome-VLA-Safety/pull/7) | open |
| 2026-09-01 | DravenALG/awesome-vla-wam | [#8](https://github.com/DravenALG/awesome-vla-wam/pull/8) | closed, not merged |
| 2026-09-01 | LLMSecurity/awesome-agent-skills-security | [#57](https://github.com/LLMSecurity/awesome-agent-skills-security/pull/57) | closed, not merged |
| 2026-09-01 | RiccardoBiosas/awesome-MLSecOps | [#77](https://github.com/RiccardoBiosas/awesome-MLSecOps/pull/77) | merged |
| 2026-09-01 | scadastrangelove/awesome-ai-security-tools | [#78](https://github.com/scadastrangelove/awesome-ai-security-tools/pull/78) | merged |
| 2026-09-01 | ai4s-research/awesome-vision-language-action | [#1](https://github.com/ai4s-research/awesome-vision-language-action/pull/1) | open |
| 2026-09-01 | DelinQu/awesome-vision-language-action-model | [#3](https://github.com/DelinQu/awesome-vision-language-action-model/pull/3) | open |
| 2026-09-01 | iotsrg/awesome-ros-security | [#1](https://github.com/iotsrg/awesome-ros-security/pull/1) | open |
| 2026-09-01 | jonyzhang2023/awesome-embodied-vla-va-vln | [#52](https://github.com/jonyzhang2023/awesome-embodied-vla-va-vln/pull/52) | open |
| 2026-09-01 | LukeLIN-web/Awesome-VLA | [#1](https://github.com/LukeLIN-web/Awesome-VLA/pull/1) | open |
| 2026-09-02 | wadeKeith/Awesome-Embodied-AI | [#7](https://github.com/wadeKeith/Awesome-Embodied-AI/pull/7) | merged |
| 2026-09-03 | keon/awesome-physical-ai | [#42](https://github.com/keon/awesome-physical-ai/pull/42) | open |
| 2026-09-05 | GT-RIPL/Awesome-LLM-Robotics | [#121](https://github.com/GT-RIPL/Awesome-LLM-Robotics/pull/121) | open |

Also open: issues [#1](https://github.com/cst-labs/awesome-embodied-ai-safety/issues/1) and
[#2](https://github.com/cst-labs/awesome-embodied-ai-safety/issues/2) on
`cst-labs/awesome-embodied-ai-safety` (2026-08-08), which ask before proposing an entry, and
[huggingface.js#2492](https://github.com/huggingface/huggingface.js/pull/2492) (2026-09-14), which
registers Provael as an evaluation framework rather than adding a list entry. States move; re-read
each link before quoting one.

## Sequence & gating

1. Land the public leaderboard + docs site so listings point at something live.
2. Submit the OECD.AI entry (§1).
3. Open the awesome-list PRs (§2).
4. Open the MITRE ATLAS case-study and OWASP-ASI embodied-annex contributions (the other drafts in
   this folder).

**All four require explicit approval before sending.** This file is the ready-to-paste source; it is
not a trigger to submit.

## JOSS submission assessment — 2026-08-13

The Journal of Open Source Software is the only route found that converts this artifact directly
into a **DOI and a citable, indexed paper**, which is the metric that currently reads zero. So the
question is not whether to submit but when, and this records the answer with a named trigger rather
than leaving it as an intention.

**Mechanical bars — all met**, verified this run:

| requirement | status |
| --- | --- |
| Public package | PyPI `provael` **0.33.0** |
| OSI licence | Apache-2.0 |
| Test suite | 85 test modules, 986 passing |
| CI | ruff · mypy strict · pytest, on every PR |
| `CITATION.cff` | present, version-guarded by a test |
| `CONTRIBUTING.md` | present |
| Development history | public since **2026-06-02** |

**The bar genuinely at risk: "substantial scholarly effort", and not a "minor utility".**

JOSS rejects packages that are thin wrappers or short scripts. Provael is neither, but the case is
weaker than the registry counts suggest, and the honest reading is what matters here:

- **8 policy backends and 5 suites are registered, but only one backend has a real-model
  measurement.** `provael coverage` reports `real_policy=3 stub_only=12` across attack families —
  the rest is stub-validated scaffolding, and the project says so everywhere. A reviewer counting
  registered backends sees breadth; a reviewer reading the evidence ladder sees one measured
  policy on one suite.
- **`hardware=0`.** No physical result of any kind.
- **5 stars, 0 forks.** Four contributors on paper — two of them are the maintainer's own accounts
  and two are bots (`dependabot`, `github-actions`), so **zero external contributors** is the true
  figure.

None of that is disqualifying on its own. Together they make a "minor utility" desk rejection a real
risk, and a desk rejection **spends the option** — JOSS resubmission after rejection is materially
harder than a first submission.

**Decision: hold.** Submit when either of these lands, whichever is first:

1. **A second policy backend with a real-model measurement** — turning "one measured policy" into a
   cross-architecture claim, which is the substance the paper would actually argue.
2. **The SO-101 hardware result** — turning `hardware=0` into a sim-to-real correlation, which is
   the single most-asked question about this work.

Re-check this assessment when either ships. Waiting costs a few weeks; submitting early and being
desk-rejected costs the route.
