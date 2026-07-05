# The Embodied AI Security Top 10 (v0.2)

### Top 10 Security Risks for Embodied AI & Vision-Language-Action (VLA) Systems — community draft

Maintained by [Provael](https://github.com/provael/provael) · **v0.2 draft** · 27 Jun 2026 · License: **CC-BY-SA 4.0** · PRs welcome.

> **Independent community project. Not affiliated with or endorsed by the OWASP® Foundation or MITRE®.**
> This list is *modeled on the methodology* of the OWASP Top Ten and references OWASP/MITRE/NIST/ISO only
> to cross-map. It is a **v0.2 draft built on prior work** — it credits the researchers it stands on and
> exists to be argued with. Open an issue or PR. *(Supersedes v0.1.)*

---

## Why this list exists

Robots and humanoids increasingly run on **VLA models** — one network that turns camera images + a
natural-language instruction directly into motor commands. That collapses perception, reasoning, and
control into a single attackable surface, inheriting every LLM failure mode **plus** new ones unique to
acting in the world. The difference from chatbot security is blunt: when an embodied policy fails, **it
moves a real arm, wheel, or leg** — often irreversibly.

No existing framework covers this. OWASP's GenAI/Agentic lists target *software* agents (no physical
actuation, sensors, or kinetic harm); MITRE ATLAS catalogs adversarial-ML *techniques* but isn't
embodiment-specific; NIST AI 100-2 is adversarial-ML but not robot-aware; ISO 10218:2025 added a
cybersecurity clause to industrial-robot *safety* but not adversarial-ML threats. Academic SoKs exist but
aren't a prioritized, practitioner-facing list. **This fills that gap: a prioritized risk list for the
embodied/VLA layer, cross-mapped to all of the above so it complements rather than competes.**

## Scope (read this — it's deliberate)

**In scope: adversarial security** — risks where an attacker manipulates the system or its environment to
make an embodied agent deviate from intended, safe behavior. **Out of scope: functional safety &
non-adversarial failure** (mechanical safety, random hardware faults, and pure-reliability issues such as
hallucination-driven unsafe actions, sim-to-real gap, miscalibration, distribution shift). Those belong
to **ISO 10218:2025 / ISO 13482 / ISO 25785** and the **NIST AI RMF** safety pillar.

One honest caveat we keep visible: in embodied AI the boundary blurs, because **an attacker can
deliberately *trigger* a "safety" failure** (induce a hallucination, force a distribution shift). So the
discriminator is *adversarial reachability* — if an attacker can cause or weaponize it, it's in. See the
"Adjacent safety failures" box at the end.

## How this is ranked (honest methodology)

This is **v0.1-class evidence**: there is no embodied-vulnerability incidence corpus yet, so the ranking
is **expert-elicited, not data-driven** — and we say so. Each candidate risk was (1) harvested from the
surveys, CVEs, and papers cited below; (2) scored on an adapted **OWASP Risk Rating** rubric
(*prevalence × detectability × exploitability → likelihood, × impact*) with **impact weighted for
physical/irreversible harm using the Robot Vulnerability Scoring System (RVSS)**; (3) cross-mapped to
OWASP Agentic, OWASP LLM, MITRE ATLAS, and NIST AI 100-2 for traceability. **Ordering will change** as a
real corpus matures. Disagree with the rank? That's the point — open a PR.

---

## The Top 10 at a glance

| ID | Risk | Layer | Strongest evidence |
|---|---|---|---|
| **EAI01** | Policy & instruction jailbreak (direct channel) | Model | *[research]* RoboPAIR, BadRobot |
| **EAI02** | Adversarial perception (patches / textures / sensor spoofing) | Perception | *[research]* VLA adversarial attacks |
| **EAI03** | Model & pipeline poisoning, backdoors & supply chain | Model / supply chain | *[research]* BadVLA, TrojanRobot |
| **EAI04** | Action-space integrity attacks (hijack / targeted / freeze) | Action | *[research]* AttackVLA, FreezeVLA |
| **EAI05** | Indirect / embodied prompt injection | Perception / tools | *[research]* CrossInject |
| **EAI06** | Cross-domain safety misalignment (the embodiment gap) | Model / safety | *[research]* BadRobot (ICLR 2025) |
| **EAI07** | CPS, firmware, comms & teleoperation compromise | Hardware / network | *[incident]* UniPwn (CVE-2025-60250/-60251), Go1 backdoor (CVE-2025-2894) |
| **EAI08** | Identity, access & excessive autonomy | Identity / authz | *[incident]* unauth ROS/DDS; *[framework]* OWASP ASI03 |
| **EAI09** | Model & data confidentiality — theft, extraction, inversion & surveillance | Confidentiality / privacy | *[incident]* Unitree G1 telemetry; *[research]* model extraction |
| **EAI10** | Insufficient evaluation, observability & incident response | Operations / governance | *[emerging]* a16z "physical AI deployment gap" |

**Cross-cutting (not numbered — they span all 10):** ⚠️ **Physical human-harm / irreversible actuation**
(a severity axis over every item) · ⏻ **Availability / DoS & energy-latency at the edge** (sponge,
latency, freeze). **Watchlist (emerging):** multi-robot / wormable propagation · cascading multi-agent
failures · rogue/self-evolving agents · long-lived memory poisoning.

---

## EAI01 — Policy & instruction jailbreak (direct command channel)
**What.** Natural-language commands (direct, or via an LLM planner) that drive the policy to act against
its safety constraints — the embodied analog of an LLM jailbreak, output as a physical action plan.
**Evidence.** *[research]* **RoboPAIR** (arXiv 2410.13691, ~100% ASR incl. a deployed Unitree Go2);
**BadRobot** (ICLR 2025, arXiv 2407.20242). Provael's own runs: `roleplay` diverts a real SmolVLA×LIBERO policy **100% (10/10), 95% CI [72–100%]** against a **0% benign baseline** (sim-only, one task, n=10; reproduce with `provael calibrate` + `attack --calib`).
**Why it matters.** Cheapest, most transferable attack — rides the normal command channel to a moving robot.
**Mitigations.** Instruction provenance/auth; runtime plan-validation guardrail (temporal-logic /
executability, cf. RoboGuard); embodied-harm refusal training; red-team each release and gate on ASR.
**Maps to.** OWASP **ASI01 Agent Goal Hijack** · OWASP **LLM01 Prompt Injection** · MITRE ATLAS (jailbreak).

## EAI02 — Adversarial perception (patches / textures / sensor spoofing)
**What.** Crafted perturbations in what the policy *sees/senses* — adversarial patches, stickers, 3D
textures, or sensor spoofing — that flip behavior while looking benign to humans.
**Evidence.** *[research]* "Adversarial vulnerabilities of VLA models" (arXiv 2411.13587); action-aware
patch attacks. *(Honest note: in Provael's SmolVLA×LIBERO run these did NOT transfer — 0% (0/10), 95% CI
[0–28%], against the same 0% benign baseline; real-world robustness of perception attacks is unsettled,
which is exactly why you test rather than assume.)*
**Why it matters.** Lives in the physical environment, not the network — needs no system access, survives air-gaps.
**Mitigations.** Input smoothing/randomization; multi-view & multi-sensor agreement; adversarial training;
perception-embedding anomaly detection; physical red-team with printed artifacts.
**Maps to.** NIST AI 100-2 **Evasion (integrity)** · MITRE ATLAS **Defense Evasion / craft adversarial data**.

## EAI03 — Model & pipeline poisoning, backdoors & supply chain
**What.** Hidden triggers planted at training/fine-tuning time, or via a poisoned open-weights checkpoint,
dataset, teleop data, or RAG corpus — normal behavior until the trigger fires attacker-chosen actions.
**Evidence.** *[research]* **BadVLA** (arXiv 2505.16640, survives fine-tuning); **TrojanRobot** (arXiv
2411.11683, physical-world backdoor via a malicious VLM, validated on a UR3e arm). The open VLA hub
ecosystem (OpenVLA/π0/GR00T) is a direct supply-chain surface.
**Why it matters.** Near-invisible in normal eval, persistent, triggerable on demand — poison once, ship everywhere.
**Attack shipped (Provael):** the `backdoor` family (`object_trigger` + `phrase_trigger`) — *method:* a
**pre-deployment backdoor screen**. It injects a battery of harmless, sim-only candidate triggers (a
visual/object trigger and an objective-decoupled trigger phrase) while leaving the visible task benign, and
measures whether the policy activates a hidden objective — each scored as an activation rate with a 95%
Wilson CI against a benign-FPR control (the `none` baseline). Provael **does not train or implant a real
backdoor**; it screens a checkpoint for one. **Stub-validated only** (the deterministic CPU core is planted
with a known trigger, so the screen fires 100% [84–100%] vs a 0% benign baseline); a clean, un-backdoored
public checkpoint carries no such implant, so the same screen reads ~0% — an honest null. Real-model
SmolVLA × LIBERO transfer is GPU-gated and **not yet run** — no cross-model claim.
**Mitigations.** Checkpoint provenance + hashes; prefer signed/attested weights; scan fine-tunes; backdoor/
trigger probes pre-deploy; treat third-party data + RAG as untrusted.
**Maps to.** OWASP **LLM03 Supply Chain** + **LLM04 Data & Model Poisoning** · OWASP **ASI04 Agentic
Supply Chain** · NIST AI 100-2 **Poisoning / Supply-Chain**.

## EAI04 — Action-space integrity attacks (hijack / targeted trajectory / freeze)
**What.** Attacks optimized in the *action* output: hijacking the policy into an attacker-specified
trajectory, degrading task success, or freezing it (paralysis).
**Evidence.** *[research]* **AttackVLA/BackdoorVLA** (arXiv 2511.12149, targeted action sequence,
real-robot validated); **FreezeVLA** (arXiv 2509.19870, ~76% paralysis ASR). *(Freeze is also an
availability/DoS failure — see cross-cutting.)* **Attack shipped (Provael):** the `action` family
(`freeze` + `trajectory_hijack`) — *method:* a freeze directive drives the policy's motor command to a
no-op (FreezeVLA-style action-freeze) while a hijack directive redirects the trajectory toward an
attacker waypoint; each scored as a rate with a 95% Wilson CI against a benign-FPR control. **Stub-validated
only** (deterministic CPU core, freeze/redirection 100% [72–100%] vs a 0% benign baseline); real-model
SmolVLA × LIBERO transfer is GPU-gated and **not yet run** — no cross-model claim. **Also shipped:** the
`optimized` family (`targeted_hijack`) — a black-box, query-budgeted *search* that adapts a `goto::`
directive to steer the policy's emitted motion toward an attacker goal (the first non-templated attack);
stub-validated (100% [84–100%] vs a 0% benign baseline at query-budget 200), real transfer GPU-gated.
**Why it matters.** A hijacked-trajectory robot and a frozen robot are different severe failures — and a
single "task success" metric hides both.
**Mitigations.** Report ASR as a matrix (untargeted / freeze / targeted) with a clean baseline; action
sanity-bounds, rate/force limits, motion-envelope watchdogs; keep-out-zone enforcement.
**Maps to.** MITRE ATLAS **Impact** · NIST AI 100-2 **Integrity violation** · ISO 10218:2025 (monitored stop/limits).

## EAI05 — Indirect / embodied prompt injection
**What.** Malicious instructions that enter *through the environment*, not the user — text on a sign or
screen the robot reads, a poisoned object label, a hostile tool/MCP description, or RAG content — treated
as commands.
**Evidence.** *[research]* **CrossInject** (arXiv 2504.14348, ACM MM 2025, coordinated cross-modal
injection); the same indirect-injection class OWASP ranks #1 for LLM apps, now with an actuator on the end.
**Why it matters.** The attacker never touches your system — they place content where the robot perceives it.
**Mitigations.** Treat all perceived text/tool metadata as untrusted *data*, never instructions;
hard control-vs-content channel separation; tool allow-lists; sanitize RAG corpora.
**Maps to.** OWASP **LLM01 Prompt Injection (indirect)** · OWASP **ASI06 Memory & Context Poisoning** ·
NIST AI 100-2 **Indirect Prompt Injection**.

## EAI06 — Cross-domain safety misalignment (the embodiment gap)
**What.** A mismatch across the three layers a VLA policy spans — **language-level safety**,
**world-model reasoning**, and the **executable physical action** — so that safety at one layer does not
carry to the next. Three failure sub-modes (BadRobot, ICLR 2025):
- **Action-language safety misalignment** — the model refuses (or reasons safely) in *text* yet still
  emits the harmful *action* plan; a guardrail that validates language but not the physical plan misses it.
- **World-knowledge flaws** — a *benign-looking* instruction yields an unsafe action because the agent's
  physical-world understanding is incomplete or wrong (e.g. it does not know an object is hazardous, fragile,
  or a person). Nothing looks unsafe at the language layer; the harm is in the world model.
- **Instruction jailbreak → action** — the [EAI01](#eai01--policy--instruction-jailbreak-direct-command-channel)
  channel, viewed as the language→action leg of the same misalignment.
**Evidence.** *[research]* **BadRobot** (ICLR 2025) names cross-domain safety misalignment — including the
world-knowledge failure mode — as a core embodied surface: safe language, unsafe action.
**Why it matters.** Teams that bolt an LLM-style refusal filter onto a robot get false confidence — a
benign-looking, "safely-reasoned" instruction can still drive a dangerous action.
**Mitigations.** Validate the *action plan* and its *physical-world consequences*, not just language; ground
safety rules to world state (object/person/hazard awareness); executability + harm gating at the
planner→actuator boundary; an independent safety monitor.
**Maps to.** OWASP **LLM06 / ASI03 (excessive agency / guardrail bypass)** · ISO 10218:2025 / ISO 13482 (functional safety interface).

## EAI07 — CPS, firmware, comms & teleoperation compromise
**What.** Classic cyber-physical weaknesses in the robot and its control links: insecure setup
interfaces, hardcoded keys, unauthenticated/unencrypted middleware (ROS 2 / DDS), command injection, and
hijacked or spoofed **teleoperation**.
**Evidence.** *[incident]* **UniPwn** (Sept 2025, **CVE-2025-60250 / CVE-2025-60251**): root takeover of
Unitree Go2/B2/G1/H1 over BLE via a hardcoded key (the "secret" was the string `unitree`) + unsanitized
input to `system()`, **wormable** across robots. **Unitree Go1 backdoor** (**CVE-2025-2894**): pre-installed
remote-access tunnel. *(Note: CVE-2025-60252 does not exist — do not cite it.)* Teleop matters because many
"autonomous" demos are actually human-operated.
**Why it matters.** The threat practitioners feel *today* — no exotic ML needed to drive a fleet of robots.
**Mitigations.** No hardcoded secrets; authenticated + encrypted control and DDS (SROS2 on, not disabled
for latency); secure boot + signed firmware; network segmentation; authenticated, integrity-checked teleop;
treat the robot as hostile-internet-exposed CPS.
**Maps to.** ISO 10218:2025 (cyber clause) + **IEC 62443** · MITRE **ATT&CK for ICS** · CWE-321 (hardcoded key), CWE-78 (command injection).

## EAI08 — Identity, access & excessive autonomy
**What.** Weak or missing authentication/authorization on robot control surfaces (open ROS graphs,
unauthenticated APIs, static credentials) **and** over-broad agent autonomy — a policy permitted to take
high-consequence physical actions without scoping, approval, or least-privilege.
**Evidence.** *[incident]* unauthenticated ROS/DDS and static-credential findings across commercial robots;
*[framework]* OWASP elevates both as first-class (ASI03, LLM06).
**Why it matters.** The difference between "an attack reaches the policy" and "an attack reaches the
actuators" is access control — and an over-empowered agent turns a small compromise into a large one.
**Mitigations.** Authn/z on every control channel; least-privilege action scopes; human-in-the-loop for
high-consequence actions; capability leases / action budgets; audit + revoke.
**Maps to.** OWASP **ASI03 Identity & Privilege Abuse** · OWASP **LLM06 Excessive Agency** · IEC 62443 (access control).

## EAI09 — Model & data confidentiality — theft, extraction, inversion & surveillance
**What.** Two linked confidentiality risks: (a) **stealing or extracting the policy** (model theft,
query-based extraction, model inversion, membership inference) — which also *enables* white-box action
attacks; and (b) **the robot as a persistent surveillance device** — covert or designed-in harvesting of
its rich multimodal stream (video, audio, LiDAR, maps), affecting operators and bystanders.
**Evidence.** *[incident]* the **Unitree G1 streaming telemetry to servers in China** ~every 5 minutes
without notification (arXiv 2509.14096), cited at the U.S. Senate. *[research]* model extraction/inversion
of learned policies (DRL policy stealing; SoK on foundation-model-powered robots, arXiv 2606.16788). NIST
makes confidentiality/privacy one of its three core attack goals.
**Why it matters.** A stolen policy is permanent leverage; a robot's data stream is among the most
sensitive that exists (inside homes, factories, secure sites) — and bystanders never consented.
**Mitigations.** Egress monitoring + allow-lists; rate-limit/obfuscate query APIs; watermark/fingerprint
weights; minimize + disclose telemetry; on-device processing; data-residency controls; bystander-privacy review.
**Maps to.** OWASP **LLM02 Sensitive Information Disclosure** · NIST AI 100-2 **Privacy (model extraction, NISTAML.03)** · MITRE ATLAS **Exfiltration**.

## EAI10 — Insufficient evaluation, observability & incident response
**What.** The meta-risk: no standardized real-world safety eval, no logging/telemetry to *detect* an
attack, no policy rollback, no incident process — so the other nine go undetected and unmanaged.
**Evidence.** *[emerging]* a16z's "The Physical AI Deployment Gap": *"the robotics equivalent of DevOps
practices doesn't exist yet"* — missing observability, failure-mode testing, behavioral characterization.
No agreed embodied-AI incident-reporting framework exists.
**Why it matters.** You cannot defend, detect, or recover from what you cannot measure or see — weak ops
turns one compromise into an undetected, unbounded one.
**Mitigations.** Pre-deploy red-team + ASR scorecard (with n, CIs, clean baseline); runtime observability
on perception→action; OOD / distribution-shift monitors; graceful hand-back-to-human; versioned policies
with rollback; a written disclosure + incident plan.
**Maps to.** OWASP **ASI (inadequate monitoring)** · NIST **AI RMF (Measure / Manage)** · ISO 10218:2025 (validation).

---

## Cross-cutting risks (span all 10 — called out, not ranked as peers)

- ⚠️ **Physical human-harm / irreversible actuation.** A *severity dimension* over every item, not a
  separate slot — any of EAI01–EAI10 can end in kinetic harm. Ranks impact via **RVSS**; interfaces with
  **ISO 10218-1/-2:2025 + ISO/TS 15066** collaborative-robot force limits.
- ⏻ **Availability / DoS & energy-latency at the edge.** Sponge inputs, latency attacks, and policy
  "freezing" exhaust compute/battery or blow real-time deadlines — acutely amplified on robots. Maps to
  OWASP **LLM10 Unbounded Consumption** + ATLAS **Impact**. *(Strong candidate to promote to a numbered
  item in v0.3 — currently split between EAI04's freeze facet and here.)*

## Watchlist (emerging — real but evidence still thin or system-level)
- **Multi-robot / swarm / wormable propagation** — Morris-II self-replicating GenAI worm (arXiv 2403.02817); the wormable UniPwn Unitree botnet. Maps to OWASP **ASI08 Cascading Failures** + **ASI07 Insecure Inter-Agent Comms**.
- **Cascading multi-agent failures** (ASI08) · **Rogue / self-evolving agents** (ASI10) · **Long-lived memory & context poisoning** for persistent embodied agents (ASI06).

## Adjacent safety failures (out of scope — cross-referenced, not enumerated)
Hallucination-driven unsafe actions, sim-to-real gap, miscalibration, distribution shift, and random
hardware faults are **functional-safety / reliability** issues governed by **ISO 10218:2025 / ISO 13482 /
NIST AI RMF**. They're out of this *security* list — **but** an adversary can deliberately trigger them
(see Scope), and they share mitigations/observability with EAI06 and EAI10, so know where the line is.

---

## Cross-framework crosswalk (corrected, verbatim source items)

| EAI | OWASP Agentic (ASI 2026) | OWASP LLM 2025 | MITRE ATLAS | NIST AI 100-2 |
|---|---|---|---|---|
| 01 Jailbreak | ASI01 Agent Goal Hijack | LLM01 Prompt Injection | Jailbreak | — |
| 02 Perception | — | — | Defense Evasion | Evasion (integrity) |
| 03 Poison/supply | ASI04 Agentic Supply Chain | LLM03 Supply Chain; LLM04 Data & Model Poisoning | Poison data; backdoor model | Poisoning; Supply-chain |
| 04 Action-space | — | — | Impact | Integrity violation |
| 05 Indirect injection | ASI06 Memory & Context Poisoning | LLM01 (indirect) | Prompt injection | Indirect prompt injection |
| 06 Guardrail bypass | ASI03 Identity & Privilege Abuse | LLM06 Excessive Agency | — | — |
| 07 CPS/firmware/teleop | ASI07 Insecure Inter-Agent Comms* | — | ATT&CK ICS | — |
| 08 Identity/agency | ASI03 Identity & Privilege Abuse | LLM06 Excessive Agency | — | — |
| 09 Confidentiality | — | LLM02 Sensitive Info Disclosure | Exfiltration | Privacy (model extraction) |
| 10 Eval/observability | (inadequate monitoring) | — | — | AI RMF Measure/Manage |

*OWASP Agentic ASI list (2026): ASI01 Agent Goal Hijack · ASI02 Tool Misuse · ASI03 Identity & Privilege
Abuse · ASI04 Agentic Supply Chain · ASI05 Unexpected Code Execution · ASI06 Memory & Context Poisoning ·
ASI07 Insecure Inter-Agent Communication · ASI08 Cascading Failures · ASI09 Human-Agent Trust
Exploitation · ASI10 Rogue Agents. (CPS/firmware has no clean ASI peer — it's robot-specific, mapped to
ATT&CK-ICS + ISO 10218/IEC 62443.)*

---

## Prior art (this list synthesizes, it does not invent)

Foundational surveys: **VLA Safety survey** (arXiv 2604.23775); **Towards Robust & Secure Embodied AI**
(ACM CSUR 10.1145/3806048 / arXiv 2502.13175); **Trust in LLM-controlled Robotics** (arXiv 2601.02377);
**SoK: Humanoid Ecosystem Cybersecurity** (arXiv 2508.17481); **SoK: Security & Privacy of
Foundation-Model-Powered Robots** (arXiv 2606.16788); **Safety in Embodied AI** (arXiv 2605.02900).
Attacks/benchmarks: RoboPAIR, BadRobot (ICLR 2025), BadVLA, TrojanRobot, AttackVLA, FreezeVLA, CrossInject (IDs in
each item). Red-teaming: **RedVLA** (arXiv 2604.22591). Scoring/DB: **Alias Robotics RVD** (arXiv
1912.11299) + **RVSS**. Frameworks we cross-map to: **OWASP Agentic Top 10 (2026)**, **OWASP LLM Top 10
(2025)**, **MITRE ATLAS** (v5.x, 16 tactics), **NIST AI 100-2e2025**, **ISO 10218:2025 / IEC 62443**.
Natural OWASP ally: **OWASP HACTU8** (a robotics/IoT/AI security *testing platform*).

## How to contribute
This is **v0.2, made to be argued with.** Wrong rank, wrong category, wrong mapping, or a missing risk —
tell us. **No code required:**

- **Issue form** — [Top 10: propose / dispute / fix a mapping](https://github.com/provael/provael/issues/new?template=top10-feedback.yml).
- **Or a PR** editing this file (`docs/TOP10.md`) directly.
- **Full guide** — [Contributing to the Embodied AI Security Top 10](https://github.com/provael/provael/blob/main/CONTRIBUTING.md#contributing-to-the-embodied-ai-security-top-10).

Contributors and the researchers behind each cited attack are credited (see
[Maintainers & Contributors](#maintainers--contributors)). The aim is a living, community-owned,
vendor-neutral list, ideally routed into the **OWASP GenAI Agentic Security Initiative** over time.
Licensed CC-BY-SA 4.0 so it can be donated/merged cleanly.

## Maintainers & Contributors

**Maintainer:** [Sattyam Jain](https://github.com/sattyamjjain) — Provael.

**Contributors**

- **Hangtao Zhang** — University of Pennsylvania ([Google Scholar](https://scholar.google.com/citations?user=H6wMyNEAAAAJ)). Co-author; shaped EAI01 and the EAI06 cross-domain-safety-misalignment framing (incl. the world-knowledge failure mode) from the BadRobot (ICLR 2025) work.

Further co-authors and reviewers will be listed here as they join.

**Built on the work of**

This list stands on the researchers it cites — BadRobot, RoboPAIR, BadVLA, AttackVLA, FreezeVLA, and the
others credited in [Prior art](#prior-art-this-list-synthesizes-it-does-not-invent).

## How to cite

> Provael. *The Embodied AI Security Top 10 (v0.2).* 2026.
> <https://github.com/provael/provael/blob/main/docs/TOP10.md>

---

*v0.2 · Provael · Prove it. Prevail. · Independent — not affiliated with OWASP or MITRE. Cites the work it builds on.*
