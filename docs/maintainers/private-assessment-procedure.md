# Private assessment procedure — one engagement, small and controlled

This is the operating procedure for the first paid assessments: who authorises what, where the
customer's inputs may go, where the run executes, what leaves, and how everything is deleted. It is
deliberately narrow. There is no upload portal, no multi-tenant service, no authentication layer and
no billing system behind it, and none is planned until repeated buyers require hosted operation and
will pay for its controls ([roadmap](../roadmap.md)). Until then an assessment runs in the customer's
own environment, or in an isolated environment both parties have agreed in writing.

The website's data-handling statement and this page must say the same thing; when they differ, this
page is corrected to the contract, not the other way round.

## 1. Authorization, before any input moves

| item | recorded where | who |
| --- | --- | --- |
| Signed engagement (scope, price, the [protocol](https://github.com/provael/provael/blob/main/examples/assessment/README.md) as an annex) | the contract, outside this repository | customer signatory · Provael |
| Named **access owner** on the customer side — the one person who grants and revokes access | the contract | customer |
| Named **operator** on the Provael side (one person; Provael is a solo project and says so) | the contract | Provael |
| Written authorisation to run attacks against the named checkpoint in the named simulator | the contract | customer |
| The allowed-inputs list (below), agreed | the contract | both |

No input is accepted and no environment is provisioned before every row is filled.

## 2. Allowed inputs, and nothing else

Accepted: the checkpoint (or a pointer to it inside the customer's environment), the simulator and
task set already named in the protocol, the agreed acceptance protocol file, and a contact. Refused:
credentials of any kind, customer traces or recordings beyond what the simulator produces during the
run, production data, personal data, and anything not named in the protocol. An input that arrives
outside the list is not opened; the access owner is told and it is deleted.

**Never through public GitHub.** Not as an issue attachment, not as a pull request, not in a
discussion, not in a gist. The issue templates say so in their own words; the monitored private
contact is **hello@provael.com**. A private artifact that reaches a public commit is treated as a
disclosure incident, not a mistake to quietly revert (a public commit is indexed within minutes).

## 3. Execution location

**Preferred: customer-controlled.** The customer provisions a GPU host inside their own boundary,
installs the pinned release (`pip install 'provael[lerobot]==<version>'`), and the operator works
through access the access owner grants and can revoke. Inputs never leave the customer; only the
deliverables in section 4 do, by the customer's own channel.

**Second: an agreed isolated environment.** One ephemeral host or container per engagement, no
shared volumes with any other work, network egress limited to the model-loader host the protocol
names (a checkpoint pull) and nothing else, `PROVAEL_REPOSITORY` / `PROVAEL_COMMIT` set so the
execution manifests carry provenance, and the host destroyed at the end of the engagement — not
reused. The in-repo `provael serve` reference server is **not** this environment and is not used for
commercial private workloads: it has no authentication, no tenant ownership and no job binding, and
its README says so.

In both cases the execution manifest's environment block is an allow-list
(`provael.execution.ENV_ALLOWLIST`); secrets present in the process environment do not reach the
artifact, and the dry run below checked that the block came out empty.

## 4. Output sharing

What leaves is the delivery pack and nothing under it: `report.json`, `report.md`,
`report.decision.json` (the verdict under the agreed protocol), the scorecard, the evidence
manifest, the execution manifest(s), the attestation bundle (signed with the operator's key when
asked, digest-only otherwise), and the reproduction notes — the shape in
[`examples/delivery-pack/`](https://github.com/provael/provael/blob/main/examples/delivery-pack/smolvla-libero-object-2026-09-14/README.md).
Every file is listed with its sha256 in a manifest sent alongside, so the customer can tell a
complete pack from a truncated one. The trial ledger (`ledger.jsonl`) and any video clips are shared
only if the protocol says so; they contain the customer's rendered frames.

Findings are the customer's. Nothing from an engagement is published, cited, aggregated into a
leaderboard or used as an example without written permission naming the artifact; the public
delivery pack in this repository is built from the project's own committed run for that reason.

## 5. Retention and deletion

- Inputs: deleted from every Provael-side location at the end of the engagement, or within 7 days of
  delivery, whichever is sooner; sooner on request.
- Deliverables: one copy retained by Provael for 90 days for questions, then deleted, unless the
  contract says otherwise.
- Deletion is **verified**, not assumed: list the paths before, delete, list after, and send the
  access owner the after-listing with the date. An ephemeral host is destroyed, not wiped.
- Access granted by the access owner is revoked by the access owner; the operator asks for the
  revocation in writing at delivery.

## 6. Dry run — 19 September 2026, dummy data

Run once before the first engagement, with dummy inputs, to check that every transfer and access
grant above is real and recorded. Executed on the maintainer's workstation in a scratch directory;
the customer's checkpoint was 4 KiB of random bytes and the CPU `stub` policy stood in for it.

| step | what happened | evidence |
| --- | --- | --- |
| receive | `dummy-checkpoint.safetensors` and `protocol.yml` placed in `inbound/`, digested | `inbound.sha256`: `61c9ded4…`, `c66d2a8b…` (11:57:06Z) |
| run | `provael attack --policy stub --suite stub --attacks none,instruction,visual --episodes 5 --seed 0 --protocol inbound/protocol.yml --out work/run`, then `report --format scorecard`, `evidence-manifest --commit dryrun0000`, `attest --no-sign` | decision under `smolvla-libero-object-pilot`: `fail` (the stub is not a real policy, and its roleplay arm exceeds the gate) |
| hand back | seven deliverables copied to `outbound/` and digested; no inbound file name appears in any deliverable; the execution manifest's `env` block is `{}` | `outbound.sha256` (11:57:08Z) |
| delete | `inbound/`, `work/`, `outbound/` removed; after-listing shows only the two digest manifests | 11:57:20Z |

What the dry run does not show: the customer-side access grant and revocation (no customer), and
the destruction of an ephemeral host (none was provisioned). Both are recorded per engagement in the
contract's log, not here.

## What this procedure is not

Not a security programme, not a data-processing agreement template, not legal advice. It is the
operating checklist for one solo operator running one assessment at a time, written down so it can
be followed and audited rather than remembered.
