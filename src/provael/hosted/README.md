# Provael hosted surface — an EXPERIMENTAL reference, not a production service

Provael is **open-core**. Everything you need to red-team a policy and produce evidence is free and
Apache-2.0. This directory is an **experimental reference** for a hosted attestation flow — it is
**not** a production signing service and does **not** confer any authority.

## Free forever (Apache-2.0, no license, CPU-only)

- The `provael` CLI and every attack family — `instruction`, `visual`, `injection`, `action`,
  **`backdoor` (EAI03)**, and the `optimized` search.
- ASR with a **95% Wilson CI** and the **benign-FPR control**; calibration; the `transfer-test`.
- **SARIF** output, the reusable **GitHub Action**, and the **Embodied AI Security Top 10**.
- **Local `provael attest`** — a digest-bound, dated evidence bundle, optionally **Ed25519-signed
  with your own key** (`provael[attest]`), verifiable offline with a **trust store** you control.

## The experimental reference server (not authoritative)

This server is a reference surface for experimenting with a hosted flow. It is **disabled by
default** and must be enabled explicitly (`PROVAEL_ENABLE_EXPERIMENTAL_HOSTED=1`). It deliberately
does **not**:

- authenticate callers, or establish tenant / project / artifact **ownership**;
- bind a job or its inputs;
- hold any *authoritative* or *project* signing key.

Every signature it produces is the **operator's own key** (`PROVAEL_SIGNING_KEY`) and is **untrusted
by default** — a verifier trusts a key only by adding it to their own trust store
(`provael attest --verify --trust-store`), never because this server served it. `POST /attest`
refuses to mint a throwaway ephemeral key whose public half would be discarded.

`POST /assurance-report` produces a **structured assurance-report draft** — an evidence export for a
qualified assessor to evaluate, **not** an insurer or conformity-assessment opinion. It is behind
`PROVAEL_HOSTED_LICENSE`, which is a **local feature flag, not authentication or a paid license**.

The requirements for a *real* operated service (authenticated identity, tenant/artifact ownership,
job binding, KMS/HSM-backed signing, key rotation and revocation, audit logging, abuse controls) are
documented under [`docs/maintainers/`](../../../docs/maintainers/) and are intentionally **not
implemented here**.

## Run the reference server

```bash
pip install 'provael[hosted]'
PROVAEL_ENABLE_EXPERIMENTAL_HOSTED=1 provael serve   # uvicorn on 127.0.0.1:8000
# POST a report.json (digest-only bundle):
curl -s localhost:8000/attest -H 'content-type: application/json' --data @runs/stub/report.json
```

**Evidence, not certification.** This surface documents measured simulation results; it is not a
conformity certificate and is not legal advice. Provael is an independent project, not affiliated
with ISO, the EU, NIST, IEC, OWASP, or MITRE.
