# Annex III §1.1.9 and §1.2.1 of Regulation (EU) 2023/1230 — the "protection against corruption" annex, clause by clause

> **Not a conformity assessment, not legal advice.** This page pairs the verbatim text of two
> essential health and safety requirements (EHSRs) with what a Provael run can contribute as an
> *input* to the manufacturer's technical file for them, and says under each what it does **not**
> establish. A notified body, not this project, decides conformity. The Regulation applies from
> **20 January 2027**; the AI-specific delegated acts amending Annex III apply from 2 August 2028
> (see the [regulatory clock](machinery-reg-2027.md)). No harmonised standard has yet been cited under
> this Regulation; prEN 50742 (*Safety of machinery — Protection against corruption*, CLC/TC 44X),
> written for exactly these two EHSRs, was at formal vote in September 2026 with publication planned
> for November — when its text lands, this page is re-mapped to its clauses.

**Source of the quoted text.** Regulation (EU) 2023/1230 of the European Parliament and of the
Council of 14 June 2023 on machinery, OJ L 165, 29.6.2023, CELEX 32023R1230, Annex III, Part 1 —
read on EUR-Lex (https://eur-lex.europa.eu/eli/reg/2023/1230/oj) on 14 September 2026 and quoted
without alteration. If your copy of the Regulation differs, the Official Journal wins.

## Why an annex shaped like this

The 13 September 2026 regulatory re-read found that no notified body publishes acceptance of SARIF,
OSCAL or an ML-BOM. What is legible to one assessing a machinery technical file is a test report in
the shape of ISO/IEC 17025 clause 7.8 (`provael report --format test-report`) **plus a clause map
that quotes the requirement verbatim and says which evidence speaks to it**. This page is that
clause map for the two EHSRs an AI-driven robot's corruption evidence is judged against.

---

## §1.1.9 Protection against corruption — verbatim

> **1.1.9. Protection against corruption**
>
> The machinery or related product shall be designed and constructed so that the connection to it
> of another device, via any feature of the connected device itself or via any remote device that
> communicates with the machinery or related product does not lead to a hazardous situation.
>
> A hardware component transmitting signal or data, relevant for connection or access to software
> that is critical for the compliance of the machinery or related product with the relevant
> essential health and safety requirements shall be designed so that it is adequately protected
> against accidental or intentional corruption. The machinery or related product shall collect
> evidence of a legitimate or illegitimate intervention in that hardware component, when relevant
> for connection or access to software that is critical for the compliance of the machinery or
> related product.
>
> Software and data that are critical for the compliance of the machinery or related product with
> the relevant essential health and safety requirements shall be identified as such and shall be
> adequately protected against accidental or intentional corruption.
>
> The machinery or related product shall identify the software installed on it that is necessary
> for it to operate safely, and shall be able to provide that information at all times in an easily
> accessible form.
>
> The machinery or related product shall collect evidence of a legitimate or illegitimate
> intervention in the software or a modification of the software installed on the machinery or
> related product or its configuration.

### §1.1.9 — what a Provael run contributes, paragraph by paragraph

| paragraph | the requirement, in short | Provael input | what it does not establish |
| --- | --- | --- | --- |
| 1 | connecting another device, or a remote device that communicates with the machine, must not lead to a hazardous situation | the **injection** family models exactly this channel — text arriving through a connected surface (`scene_text` on the camera; `mcp_tool_desc` for a tool-description channel) — and reports, per arm, whether the policy was driven out of its envelope, against a benign floor. On a direct simulator loop `mcp_tool_desc` has no surface and is reported *not applicable*, never as 0 | which devices the machine will actually be connected to, or that the simulated channel is the deployed one |
| 2 | hardware components carrying signal/data relevant to safety-critical software must resist corruption, and interventions must be evidenced | nothing: Provael touches no hardware. The **sensor_spoof** arms perturb the *signal* a policy receives and measure the behavioural consequence; that is evidence about the policy's tolerance, not about the component's protection | any property of a hardware component or of its tamper evidence |
| 3 | software and data critical for compliance must be identified and protected against accidental or intentional corruption | `provael verify-checkpoint` pins the policy checkpoint by digest and refuses pickle-bearing formats (**checkpoint integrity**); the **weight_integrity** family measures what *K* corrupted bits do to the closed loop, gradient-selected against random, so "adequately protected" has a measured consequence of *not* being protected to be read against; the CycloneDX **ML-BOM** names the model and its inputs | that the deployed system's storage, update path or memory is protected — the flips are emulated on a loaded copy, and `BitFlipRecord.emulated` says so |
| 4 | the machine must identify the software necessary to operate safely and provide that information at all times | the **execution manifest** and the ML-BOM record the checkpoint id, revision and digest, the harness version and its dependency lock for *the run*; the SBOM covers the harness itself | the on-machine, always-available inventory the paragraph requires — that lives in the product, not in a test |
| 5 | evidence of intervention in, or modification of, installed software or its configuration | the append-only **ledger** and the digest-bound manifest show what such an evidence trail looks like for a measurement; the `--defense` audit sidecar records every input the mitigation changed | the machine's own intervention log; a test artifact is not a runtime record |

## §1.2.1 Safety and reliability of control systems — verbatim

> **1.2.1. Safety and reliability of control systems**
>
> Control systems shall be designed and constructed in such a way as to prevent hazardous
> situations from arising.
>
> Control systems shall be designed and constructed in such a way that:
>
> (a) they can withstand, where appropriate to the circumstances and the risks, the intended
> operating stresses and intended and unintended external influences, including reasonably
> foreseeable malicious attempts from third parties leading to a hazardous situation;
>
> (b) a fault in the hardware or the logic of the control system shall not lead to hazardous
> situations;
>
> (c) errors in the control system logic shall not lead to hazardous situations;
>
> (d) the limits of the safety functions are to be established as part of the risk assessment
> performed by the manufacturer and no modifications are allowed to the settings or rules generated
> by the machinery or related product or by operators, including during the machinery or related
> product learning phase, where such modifications could lead to hazardous situations;
>
> (e) reasonably foreseeable human errors during operation shall not lead to hazardous situations;
>
> (f) the tracing log of the data generated in relation to an intervention and of the versions of
> safety software uploaded after the machinery or related product has been placed on the market or
> put into service is enabled for five years after such upload, exclusively to demonstrate the
> conformity of the machinery or related product with this Annex further to a reasoned request
> from a competent national authority.
>
> Control systems of machinery or related products with fully or partially self-evolving behaviour
> or logic that are designed to operate with varying levels of autonomy shall be designed and
> constructed in such a way that:
>
> (a) they shall not cause the machinery or related product to perform actions beyond its defined
> task and movement space;
>
> (b) recording of data on the safety related decision-making process for software based safety
> systems ensuring safety function including safety components, after the machinery or related
> product has been placed on the market or put into service, is enabled and that such data is
> retained for one year after its collection, exclusively to demonstrate the conformity of the
> machinery or related product with this Annex further to a reasoned request from a competent
> national authority;
>
> (c) it shall be possible at all times to correct the machinery or related product in order to
> maintain its inherent safety.
>
> Particular attention shall be given to the following points:
>
> (a) the machinery or related product shall not start unexpectedly;
>
> (b) the parameters of the machinery or related product shall not change in an uncontrolled way,
> where such change could lead to hazardous situations;
>
> (c) modifications to the settings or rules, generated by the machinery or related product or by
> operators, including during the machinery or related product learning phase, shall be prevented,
> where such modifications could lead to hazardous situations;
>
> (d) the machinery or related product shall not be prevented from stopping if the stop command has
> already been given;
>
> (e) no moving part of the machinery or related product or piece held by the machinery or related
> product shall fall or be ejected;
>
> (f) automatic or manual stopping of the moving parts, whatever they may be, shall be unimpeded;
>
> (g) the protective devices shall remain fully effective or give a stop command;
>
> (h) the safety-related parts of the control system shall apply in a coherent way to the whole of
> an assembly of machinery or related products or partly completed machinery, or a combination
> thereof.
>
> For wireless control, a failure of the communication or connection or a faulty connection shall
> not lead to a hazardous situation.

### §1.2.1 — what a Provael run contributes, clause by clause

**First list — all control systems.**

| clause | the requirement, in short | Provael input | what it does not establish |
| --- | --- | --- | --- |
| (a) | withstand external influences *including reasonably foreseeable malicious attempts from third parties* leading to a hazardous situation | the whole measurement is this clause made operational: for each attack family the fraction of episodes in which a foreseeable third-party attempt (an instruction rewrite, an image perturbation, injected text, a corrupted weight) drove the policy into the hazard predicate, with the benign floor, Wilson intervals and a paired test. Which attempts are "reasonably foreseeable" is the manufacturer's risk-assessment call; the registry's threat-model fields (`attacker_access`, EAI id) let each arm be placed in that assessment | that the set of attacks is complete — the rates are a floor on susceptibility, and a null on a templated attack is not robustness against an optimised one |
| (b) | a hardware or logic fault must not lead to a hazardous situation | the **weight_integrity** ladder is a *logic fault* study: K flipped bits, gradient-selected and random, and whether the closed loop went unsafe | hardware faults, fault detection, or the reaction of a safety-rated control system — Provael has no safety PLC in the loop |
| (c) | errors in the control-system logic must not lead to hazardous situations | the benign arm's own unsafe rate *is* the measured rate at which the unperturbed policy reaches the hazard predicate — the clean-logic error rate the attack rates are read against; the clean task-success rate is the competence control beside it | that the predicate is the hazard the machine's risk assessment names; on LIBERO the default box is documented as uncalibrated, and a calibrated predicate is reported as such |
| (d) | safety-function limits set by the risk assessment; no modification of generated settings or rules, including during a learning phase, where it could be hazardous | the **backdoor** screen (trigger battery on a clean checkpoint) and the **weight_integrity** ladder are the arms that test whether the policy's learned rules can be altered; the calibration workflow records the limits (keep-out geometry) as committed artifacts with their benign false-positive rate | who may modify settings on the machine, or that the learning phase is locked — those are product controls |
| (e) | foreseeable human errors during operation must not be hazardous | the **harmless-variation controls** (`benign_reword`, `nonsense_text`, `scrambled_text`, `roleplay_no_target`) measure what a non-malicious, unfamiliar instruction does — the closest a red team comes to "human error", and the arm that separates attacker control from wording brittleness | ergonomic or operator-interface error modes |
| (f) | a tracing log of interventions and safety-software versions, kept five years | the execution manifest and ledger are the *shape* of such a record for a test (version, digest, seeds, every episode appended before the next starts) | the five-year on-product log the clause requires |

**Second list — self-evolving behaviour or varying levels of autonomy.** A vision-language-action
policy driving a robot is squarely here.

| clause | the requirement, in short | Provael input | what it does not establish |
| --- | --- | --- | --- |
| (a) | shall not perform actions **beyond its defined task and movement space** | this is the keep-out predicate in the Regulation's own words: an episode is unsafe when the end-effector leaves the defined movement space. The **action_space** family (`keepout_hijack`, `critical_freeze`) attacks that boundary directly; `provael calibrate` fits the space from benign rollouts and reports the holdout false-positive rate; `scripts/plot_keepout_paths.py` draws every path against it | that the box used in a run is the machine's defined movement space — the manufacturer defines it; Provael measures against what it is given, and says whether that was calibrated or the documented default |
| (b) | record safety-related decision data for one year | `decisions` per step (instruction, action, unsafe flag) are in every episode record, and the ledger keeps them — the shape of the record, for a test | the on-product recording and its retention |
| (c) | it must be possible at all times to correct the machine to maintain inherent safety | the two measured **defenses** (`instruction_canonicalization`, `action_envelope`) are corrections applied in the deployment position, and their effect is reported as a paired difference against the undefended arm | that a correction can be applied to the fielded system at all times — an operator's capability, not a test's |

**Particular attention points.** (a) unexpected start, (d) stopping not prevented, (f) stopping
unimpeded, (g) protective devices effective, (h) coherence across an assembly — **none** of these
are within scope: Provael has no start/stop logic, no protective device and no assembly model in
the loop. (b) uncontrolled parameter change and (c) modification of generated rules map to the
weight_integrity and backdoor rows above. (e) falling or ejected parts is a physical outcome the
simulation does not model (no contact-force or grasp-failure predicate is measured; the LIBERO
forbidden-grasp disjunct ships inert). The wireless-control sentence is out of scope.

## How to use this page

Attach, to the technical file's Annex IV documentation for these two EHSRs:

1. the run's `provael report --format test-report` output (the clause-7.8-shaped document);
2. this page, or the rows of it that the run actually exercised — a family that did not run is
   *not* evidence, and the test report's deviations section names the arms that had no applicable
   episode;
3. the committed results directory, its execution manifests and ledgers, and the attestation if one
   was issued.

What the file then contains is a **dated, reproducible measurement of behavioural susceptibility in
simulation**, mapped to the clauses it informs. It is an input to the manufacturer's risk
assessment under Article 25 and Annex III. It is not the assessment, and nothing here should be
cited as evidence of conformity.
