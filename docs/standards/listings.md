# Directory listings & awesome-list PRs (ready to submit)

> **Gated — nothing submitted yet.** Each item below is an external action (a submission or a PR to
> another repo). The **copy is final and ready to send**; the act of submitting is a **manual step
> that requires explicit sign-off**. Provael™ does not submit these automatically.

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
