# Glossary

Precise definitions for the terms Provael reports. The whole point of the tool is that these do not
blur into each other.

## Metrics

**Adversarial ASR (Attack Success Rate)** — successes / attempts over the **adversarial** episodes
only. The benign `none` control is excluded *by semantic role*, so adding benign episodes never
moves it. This is the headline number.

**All-episode observed-unsafe rate** — the unsafe rate over **all** applicable episodes, benign
control *included*. On a benign-heavy run it is *diluted below* the adversarial ASR. It is **not**
the attack rate, and is always labelled distinctly.

**Benign unsafe rate (benign FPR)** — the fraction of the benign `none` control episodes flagged
unsafe. The false-positive control an ASR must be read against. Distinct population from the attacks.

**Applicability / N/A** — an attack with no surface in a suite (e.g. `mcp_tool_desc` on a direct
LIBERO loop) is **not-applicable**: excluded from the denominator entirely. A 0-attempt slice is
**N/A**, never a measured `0%`.

**Clean-task-success** — the policy's benign task-completion rate, unattacked. "Is the policy even
competent on this task?" — the credibility control a headline ASR is read against.

## Evidence & verdicts

**Evidence state** — the [`EvidenceState`](https://github.com/provael/provael) ladder recording how
far a result has actually been verified: `legacy-unverified < stub < adapter-smoke < real-forward <
real-episode < measured-real-policy-effect < hil-corroborated < hardware-corroborated <
externally-reproduced < customer-release-gated`. A run is never awarded a rung it has not earned; a
report predating the ladder is `legacy-unverified` (the bottom).

**Real policy** — a real VLA checkpoint (e.g. SmolVLA, OpenVLA), as opposed to the deterministic CPU
**stub** fixture. A real *policy on a real suite* running episodes is `real-episode` — **not**
automatically a "measured effect".

**Simulation** — every Provael result is measured in simulation. A redirection/activation in sim is a
robustness signal, **not** a real-world exploit. **HIL** (hardware-in-the-loop) and **hardware**
corroboration are separate, higher rungs that require their own evidence references.

**External reproduction** — an independent party reproduced the run. A rung Provael never
self-awards.

**Release verdict** — a four-state gate, not binary: `incomplete` (a required input is missing —
never a silent pass), `fail` (a threshold or integrity/protocol was violated), `conditional` (a
bounded exception with a named approver, expiry, and remediation), `pass` (all required conditions
met).

## Attestation

**Integrity** — the payload/report bytes were not altered (a digest recomputes). Proves nothing
about *who* produced them.

**Signature validity** — a signature verifies cryptographically under some key. Still says nothing
about whether that key is *trusted*.

**Signer trust** — the signing key is in the verifier's own **trust store** (active, not revoked, in
its validity window). Only this turns a valid signature into a *trusted* one. `attest --verify` is
**fail-closed**: unsigned or untrusted is never "verified".

**Calibration** — a predicate whose threshold was fit on held-out benign data to a target
false-positive rate. Uncalibrated evidence cannot satisfy a calibration-required gate. Missing/invalid
calibration is *uncalibrated*, never "calibrated-with-a-warning".

## Standing caveat

**Certification** — Provael produces **evidence, not certification**. It is not a conformity
assessment body, an accredited lab, or an insurer/Notified-Body opinion. Its assurance/insurer
exports are **structured evidence drafts** for a qualified assessor to evaluate. Provael is an
independent project, not affiliated with ISO, the EU, NIST, IEC, OWASP, or MITRE.
