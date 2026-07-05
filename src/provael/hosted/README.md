# Provael hosted surface — the open-core boundary

Provael is **open-core**. Everything you need to red-team a policy and produce evidence is free and
Apache-2.0. A small paid surface sits on top for teams that need an *authoritative*, signed,
insurer / Notified-Body-ready attestation.

## Free forever (Apache-2.0, no license, CPU-only)

- The `provael` CLI and every attack family — `instruction`, `visual`, `injection`, `action`,
  **`backdoor` (EAI03)**, and the `optimized` search.
- ASR with a **95% Wilson CI** and the **benign-FPR control**; calibration; the `transfer-test`.
- **SARIF** output, the reusable **GitHub Action**, and the **Embodied AI Security Top 10**.
- **Local `provael attest`** — a digest-bound, dated evidence bundle, optionally **Ed25519-signed
  with your own key** (`provael[attest]`), verifiable offline.
- This **reference server** (`provael serve`, the `[hosted]` extra). Self-host it and you get
  **self-signed** attestations for free.

## Paid (the operated service, not the code)

The code here is open and self-hostable. What is sold is the **operated Provael instance**:

- the **authoritative project-key signature** — one key an insurer or a Notified Body can trust,
  instead of a self-signed key per vendor;
- the **insurer / Notified-Body-ready compliance report** (`POST /insurer-report`), which lines your
  evidence up against the EU Machinery Regulation 2023/1230, the AI Act Annex-I machinery route, and
  ISO 10218:2025 (see [`docs/compliance/machinery-reg-2027.md`](../../../docs/compliance/machinery-reg-2027.md));
- a curated / managed **targeted-backdoor screen** and the hosted dashboard.

The paid endpoints are guarded by `require_entitlement()` (the `PROVAEL_HOSTED_LICENSE` environment
variable). That gate lives **only** on the operated surfaces — it never touches the free core.

## Run the reference server

```bash
pip install 'provael[hosted]'
provael serve                       # uvicorn on 127.0.0.1:8000
# POST a report.json:
curl -s localhost:8000/attest -H 'content-type: application/json' --data @runs/stub/report.json
```

**Evidence, not certification.** This surface documents measured simulation results; it is not a
conformity certificate and is not legal advice. Provael is an independent project, not affiliated
with ISO, the EU, NIST, IEC, OWASP, or MITRE.
