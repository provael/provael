# vla-redteam — Strategy & ROI Analysis (private; not in the repo)

_Date: 2026-06-13. Synthesis of a multi-agent research run: a 10-aspect codebase audit, 23 market +
monetization web deep-dives, and an 8-claim adversarial-verification pass (agents told to *refute*).
~40 agents, ~5.3M research tokens, ~1,000 source fetches. Every non-obvious claim is grounded in a
fetched source; URLs inline. Confidence is stated per section._

> **Kept OUTSIDE the git repo on purpose** — it discusses real traction (≈1 star, ~375 real downloads)
> and the competitive/market reality candidly. For your decision, not the public page.

---

## 0. The decision (high confidence)

**Do not commercialize vla-redteam now. No domain-as-product, no pricing page, no "enterprise tier."**
On the evidence that is negative-EV. **Keep it Apache-2.0 OSS and run it as a research + reputation +
career/grant play** — the one path that survived an adversarial attempt to kill it. Treat money as a
*triggered future option*, most plausibly realized as a **grant, a senior AI-safety/robotics role, or
paid consulting** — not a solo SaaS.

But the breadth research adds a sharp, important wrinkle the first pass understated:
**you are not first or ahead in this niche.** The academic field robopwn wants citation-credit in is
already **crowded and further along** (AttackVLA, LIBERO-Plus, Embodied Red Teaming, BadVLA, RedVLA,
SafeVLA). So even the *research-capital* path is competitive: vla-redteam only pays off if it
**differentiates on what the labs don't optimize for — honesty, reproducibility, CPU-accessibility, and
a living leaderboard standard** — and only after you fix several credibility caveats (§1, §6).

---

## 1. What you actually built — codebase reality

Verified by reading the source and running the toolchain. Per-aspect production/commercial-readiness:

| Aspect | Maturity /5 | One-line |
|---|---|---|
| Engineering scaffolding (typing, CI, packaging, OIDC release) | **4** | At/above many commercial Python projects. |
| Architecture / extensibility | **3** | Clean ports-and-adapters, but **no plugin system** (extend = fork), and "model-agnostic" = **1 real backend**. |
| Attack families | **2** | **Hard-coded string templates**, not a methodology; zero optimization/search; novelty ≈ nil (by design). |
| Policy adapters (SmolVLA glue) | **2** | Real glue exists but gated/untested in CI; one model. |
| Suites + unsafe predicate | **2** | One task; **uncalibrated** keep-out zone (disclosed). |
| Scoring / metrics | **2** | Honest ASR + lift, but `asr_std` conflates seed variance with model stochasticity. |
| First real result | **2** | Credible + honestly caveated, but **only the instruction family transferred** to real SmolVLA (visual + injection = **0% lift**). |
| Positioning / docs | **2** | Clear and honest, but advertises **OpenVLA support that doesn't ship**. |
| Product surface (HF leaderboard) | **2** | A viewer, not a product/community standard yet. |

**The honest read:** **4/5 scaffolding around a 2/5 research core.** That's the right shape for a
*portfolio/credibility artifact* and the wrong shape for a product **or** a rigorous benchmark (yet).

**Credibility caveats a reviewer / HN commenter WILL find — fix or disclose before you promote:**
1. The attacks are **templates around one target word ("knife")**, not optimized adversarial methods.
2. On the *real* model, **only instruction attacks worked**; the visual + injection families scored **0%
   lift** — i.e., two of your three "families" don't transfer. Say this plainly.
3. **"Model-agnostic" is unproven** (one policy, one suite). Ship a 2nd policy (OpenVLA) or soften the claim.
4. The headline stub ASRs are partly **circular** (templates reverse-engineered to trip the stub's lexicon).
5. **1 task, uncalibrated zone** → not yet a hazard rate. (Already disclosed — keep it loud.)

These are fixable and, fixed, they *become* the differentiator (see §6).

---

## 2. The competitive reality (the big new finding)

### 2a. The academic niche is crowded and AHEAD of you
The exact idea — perturb VLA inputs, measure ASR on LIBERO — is a **saturated 2024-2026 research area**,
and the incumbents are stronger and more credible than a 1-star alpha:

| Project | What / signal | Why it matters |
|---|---|---|
| **AttackVLA** (arXiv 2511.12149, Nov 2025, 7 authors) | "First unified framework," 9 attacks, OpenVLA/SpatialVLA/π0-fast, **sim + real robot** | **Direct competitor**, same "standardize VLA benchmarking" pitch, ~7 mo ahead, named lab. |
| **LIBERO-Plus / -PRO** (347★, Oct 2025) | Tests OpenVLA-OFT/π0/NORA/WorldVLA; 95%→30% under perturbation; downstream-adopted | The **tool-shaped incumbent** on the same LIBERO substrate — 347★ vs your ~1★. |
| **Embodied Red Teaming** (MIT CSAIL, arXiv 2411.18676) | Your closest *functional twin* (instruction-perturbation in sim) | …yet only **~9★**. Proof even an elite-lab version of this idea gets ~zero adoption. |
| **BadVLA** (NeurIPS 2025) | ~100% ASR, **54★** | The realistic *ceiling* for a single strong VLA-attack paper. |
| **RedVLA / Q-DIG / EDPA / VLA-Fool / BeSafe-Bench / AGENTSAFE** | 2025-26 papers; RedVLA 92.7% ASR; EDPA also claims "model-agnostic VLA attack" | The field is **dense and converging** on robopwn's exact thesis. |

**Implication:** robopwn is **late and technically weaker** (templated vs optimized, 1 task vs 4 suites,
CPU-stub vs real-robot) than the citation competition. The "be a research artifact" path is real but
**you won't win on rigor** — AttackVLA/BadVLA already have it. You can only win on **accessibility +
honesty + a standardized, reproducible, CPU-runnable leaderboard** that researchers *use* to compare
methods. That, not novelty, is the wedge.

### 2b. The funded market is real — and it isn't yours
Every funded AI-security dollar is **LLM/agent**, none robot/VLA:
- **Exits:** Lakera→Check Point (~$300M), Protect AI→Palo Alto (~$650-700M), Robust Intelligence→Cisco
  (~$400M), Promptfoo→OpenAI (~$86M). **HiddenLayer** $50M A; **Gray Swan** $40M A (and *already
  researching VLA attacks* — the most likely entrant if a buyer appears); **Haize** $12.5M (Anthropic/
  Scale/AI21 contracts).
- **OSS-eval comps:** garak (NVIDIA, ~8k★, ~68k DL/mo), promptfoo (13.2k★), DeepEval (15k★), PyRIT (MS),
  Giskard (5.2k★, €4.5M, AXA/BNP). **All text/LLM. Two independent tool surveys list 0 VLA/robot products.**
- **Robot-security incumbent:** **Alias Robotics** (~9.1k★ CAI, ~$1.55M raised in ~8 yrs) — and it does
  **firmware/network/OT security, not VLA-policy red-teaming.** The one funded robot-security company
  isn't in your lane, and barely raised.

### 2c. The macro tailwind is real but ~12-24 months early
- **Demand drivers forming:** EU AI Act Art. 15 now names "adversarial examples" (high-risk obligations
  Aug 2026; robotics ~2027); ISO 10218:2025 adds a cybersecurity clause (legacy certs expire Jan 2027);
  ISO/PAS 8800 + ISO/WD 25785 (humanoid safety) incoming. **DARPA SAFRON** ("Safe and Assured Foundation
  Robots for Open Environments") is a *whole program on exactly this problem* (closed Jan 2025 → proves
  the thesis is real and funded). Real incidents: **UniPwn** (Unitree, Sep 2025), **UCSC physical prompt
  injection** (Jan 2026). VLA share of robot deployments projected **<5% → ~40% in two years.**
- **But:** buyers (Figure $39B, Physical Intelligence, Skild $14B) are **flush and build safety
  in-house**; production manipulation VLA is pre-scale (Figure/BMW pilot **ended** Nov 2025). The only
  production-VLA domain with paying safety buyers today is **autonomous driving** (Waymo, NVIDIA Halos,
  Applied Intuition $15B, Foretellix) — which robopwn doesn't serve.

---

## 3. Monetization reality (why direct revenue fails now) — high confidence

8/8 adversarial verdicts; the two highest-confidence refutations were "landing page → MRR" and
"comparable OSS tools monetized in solo-replicable ways."

- **How the comps *actually* monetized — none solo-replicable.** VC company-building (Semgrep ~$193M/250
  staff; Aqua/Trivy $89.9M rev/$325M raised; DeepEval→YC; Giskard €4.5M) **or** acqui-hire/salary
  (**Trivy's author got hired by Aqua**; **garak has no paid tier — sustained by an NVIDIA salary**;
  promptfoo needed $5M + 23 staff + 350k users before a $86M exit). The replicable solo outcomes are
  **getting hired** and **credibility**, not a revenue business.
- **Solo-donation reality (your actual near-term option if you tried):** azu **$14.6k/yr**; Matt Lacey
  after **3 years = "half a month's salary"**; Caleb Porzio's $112k is an outlier from **paid screencasts,
  not donations**. 49k sponsorable devs, tiny % earn real money. At 11 days / 1★, donations ≈ $0.
- **No demand signal.** 1★, 0 forks, ~375 real downloads. A landing page amplifies demand; it can't
  create it. Even RoboPAIR (the famous robot jailbreak) = 25★, paper not product.

**Verdict:** selling this in 2026 means selling to a buyer that doesn't exist, against free incumbent
tools, in a niche whose own famous prior art never monetized. Don't.

---

## 4. The path that wins — research/reputation/career/grant capital (the one SUPPORTED claim)

Live, **named** buyers of exactly the signal this project produces:

- **Roles (the garak→NVIDIA blueprint, 1:1):** garak's academic author parlayed an OSS red-team tool into
  **Senior AI Security Researcher at NVIDIA.** Market: **AI Red Team Researcher $180-280k+**, AI Safety
  Evaluator $120-180k.
- **Anthropic Fellows** (~$3,850/wk + ~$15k/mo compute + mentorship; **>40% of the first cohort joined
  Anthropic**) — a structured research-capital→role pipeline you can apply to.
- **Grants that fund *individuals* (not just orgs):** **Manifund** regrantors hold $100k+ discretionary,
  fast/low-friction; **LTFF** $20-80k (~19% acceptance); **AISTOF/EA micro-grants** $5-50k. Bigger gov
  money (DARPA SAFRON, DoD SBIR, EU Horizon) needs a **university PI or a registered small business** —
  co-applicant path, 12-24 mo.
- **Consulting** converts a credible name to cash: **$100-200/hr**, model audits **$25k-120k** — higher-
  probability solo income than a product.
- **You fit this** (prior acquired project + a VLA red-team arXiv paper).

**The binding constraint for ALL of it: escape obscurity.** At 1★, every return — including these — is
~zero in absolute terms. Distribution + credibility is priority #1.

---

## 5. The honest scorecard (for the ROI-minded)

| Path | Realistic outcome | Probability (conditional on real effort) | Verdict |
|---|---|---|---|
| Solo product / open-core / pricing now | ~$0 MRR; wasted weeks | direct revenue: **low** | **Don't** |
| Donations / sponsors | $0-2k/yr at this scale | low | Not worth chasing |
| **Research artifact → citations** | If differentiated: cited; if not: ignored (field is ahead) | medium **iff** you differentiate | **Do — carefully** |
| **Career capital → role** | $130-280k role (garak path) | **medium-high** | **Primary prize** |
| **Grant (micro)** | $5-80k, non-dilutive | medium | **Do — apply** |
| Consulting | $100-200/hr, audits $25-120k | medium (after reputation) | Opportunistic |
| Funded startup later | Only if a trigger fires; needs team | low now, optionality | **Triggered option** |

---

## 6. Recommendation — staged plan (ranked by ROI)

### Do now (cheap; all aimed at credibility + differentiation, the binding constraints)
1. **Stay Apache-2.0. Add no paid tier/pricing.** Preserves the adoption that gates every real return.
2. **Fix the credibility caveats in §1 first** (disclose templated attacks + the 0%-transfer of visual/
   injection; drop or ship the OpenVLA claim). Honesty *is* your differentiator vs the louder labs —
   don't let a reviewer find these before you do.
3. **Differentiate, don't out-rigor.** You can't beat AttackVLA/BadVLA on attack strength. Win on
   **"the open, reproducible, CPU-runnable leaderboard that lets anyone compare VLA robustness"** —
   multi-task + multi-model + **calibrated keep-out zones**, plus other people's checkpoints on the board.
   A *used* leaderboard is the only realistic solo moat.
4. **Write it up** (short arXiv note / strong post) positioned honestly beside RoboPAIR/AttackVLA/SafeVLA.
   This is what converts to a citation, a role, or a grant.
5. **Buy a $15 domain + a FREE docs site** (Mintlify Hobby includes a custom domain; or an Astro page on
   Cloudflare). **Purely as a recruiting/citation/credibility surface — not a product.** ~a weekend, ~$0.
6. **Apply to Manifund / LTFF** (individual-eligible, on-thesis) and **Anthropic Fellows**. Best money path.
7. **Distribute** into LeRobot/HF (24.9k★, rising), robot-learning circles, and to the AttackVLA/ERT
   authors (collaborate, don't compete). You've started (LinkedIn) — keep going.

### Reconsider commercialization only on a trigger
- Inbound buyer pull (a robotics lab / insurer / regulator asks to pay), **or**
- The leaderboard becomes a *referenced standard*, **or**
- Production-VLA scale + a compliance forcing function (~2027; EU AI Act extends to embodied; insurer
  "AI security riders"). If a trigger fires → **funded + co-founder**, or join a funded AI-security/
  robotics company, not a solo page.

### Know the one real expansion lane (don't act yet)
**Autonomous driving** is the only production-VLA market with paying safety buyers (Waymo, NVIDIA Halos,
Applied Intuition, Foretellix). A deliberate, regulated pivot — option value, not a near-term move.

---

## 7. Risks to this recommendation
- **Upside-tail counter:** the biggest dollars here (Promptfoo $86M) came from the *product/VC* path, not
  reputation. If you specifically want a venture swing, the move is **raise + team early**, accepting you're
  ~12-24 mo ahead of buyers. Reputation path = higher probability, lower ceiling.
- **Citation competition is real:** if you *don't* differentiate (leaderboard standard + honesty +
  accessibility), the research path also returns ~zero — AttackVLA/LIBERO-Plus will be cited instead.
- **Timing could compress:** VLA→40% of deployments in 2 yrs + an incident/regulation could pull a buyer
  market forward. The triggers above catch that without betting on it.
- **Common-mode failure:** obscurity. Fight that, not the monetization model.

---

## 8. Bottom line
You built a well-engineered, **honest, early** tool in a niche that (a) doesn't pay yet and (b) is already
crowded by funded labs with stronger results. Chasing MRR is negative-EV; out-rigoring the labs is a losing
game. **The win is to turn this into proof of expertise** — make it the *honest, reproducible, accessible
leaderboard standard*, publish it, apply for a grant/fellowship, and let it pull a $180-280k safety/
robotics role or consulting. That is the highest-EV, evidence-backed path for a solo dev in this niche in
2026 — and it's the one with live buyers today. Keep monetization as a triggered option, not a 2026 plan.

_Sources: inline URLs throughout; full adversarial-verification transcript + 32 breadth deep-dives saved
with the workflow runs._
