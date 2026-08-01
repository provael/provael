# Hosted service — production requirements (NOT yet implemented)

`src/provael/hosted/` is an **experimental reference surface**, disabled by default
(`PROVAEL_ENABLE_EXPERIMENTAL_HOSTED=1` to run locally). It is **not** a production signing service
and must not be operated as one. This document records what a *real* operated service would require,
so the gap is explicit and nobody mistakes the reference for the product.

> Status: **specification only.** None of the controls below are implemented. `PROVAEL_HOSTED_LICENSE`
> is a local feature flag, not authentication. Every signature the reference server produces is the
> operator's own key and is untrusted until a verifier adds it to their trust store.

## Identity, ownership, authorization

- [ ] Authenticated caller identity (OIDC / API keys with rotation), not an environment variable.
- [ ] Organisation and tenant boundaries; strict tenant isolation.
- [ ] Project and artifact **ownership**: a caller may only attest reports they own.
- [ ] Object-level authorization on every endpoint (no IDOR).

## Job model and execution

- [ ] Job creation with **immutable input binding** (report digest, config, code commit).
- [ ] Isolated execution; evidence ingested from a trusted job, not arbitrary client-supplied JSON.
- [ ] Malware / archive-bomb handling on any uploaded artifact.
- [ ] Anti-replay (nonce / job-id binding) so a signature cannot be replayed onto another subject.

## Signing

- [ ] **KMS/HSM-backed** signing key — never a PEM in an environment variable.
- [ ] An explicit signing policy (what may be signed, by whom, under which key).
- [ ] Key rotation and **revocation**, surfaced to verifiers (trust-store status / a revocation feed).
- [ ] A published trust anchor so a relying party can independently verify signer identity.

## Operations, safety, and legal

- [ ] Tamper-evident audit log of every signing and report request.
- [ ] Rate limits and abuse controls.
- [ ] Retention / deletion policy; data-processing terms; a customer contract.
- [ ] Incident-response runbook; an independent security review and penetration test **before** any
      "authoritative" or "insurer / Notified-Body" language is used anywhere.

Until every box above is checked and independently reviewed, the hosted output is a **structured
evidence draft**, and any signature is the **operator's own untrusted key** — never a Provael or
project authority, and never an insurer or conformity-assessment opinion.
