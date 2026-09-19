# Paid-run dependency licences — the register for the supported pilot

Before a paid assessment ships on the one supported configuration (SmolVLA on LIBERO-Object
through LeRobot), every dependency that run redistributes, loads or executes has an identified
licence or permission status. This page is that register. It records what is **checked** and against
what, and marks what is **unverified** rather than assuming it; an unverified row is a task before
the engagement, not a risk accepted in silence.

Two things this page is not. It is not legal advice, and it is not a record of the maintainer's
employment or IP provenance — that is recorded privately, outside the repository, as a contract
matter; a public page is the wrong place for an employment contract and this register does not carry
one.

## How to read a row

- **Status `checked (metadata)`** — read from the installed distribution's metadata in this
  environment at the version named. Re-verify at the pinned version in the engagement's environment,
  since a pin can move.
- **Status `stated by project`** — the licence the upstream project states in its repository at the
  time of writing; not read from an installed artifact here (the GPU extras are not installed on the
  CPU build). Re-verify against the pinned release's `LICENSE` file before the run.
- **Status `unverified`** — nobody has read the terms at the exact revision the run will load.
  Resolve before the engagement; record the revision and the terms you read.

## The register (19 September 2026)

| dependency | role in the run | pinned as | licence / permission | status |
| --- | --- | --- | --- | --- |
| `provael` | the tool | the release the engagement pins | Apache-2.0 (`LICENSE`); the Top 10 document carries its own licence (`docs/top10.md`) | checked (this repository) |
| `lerobot[smolvla,libero]` | policy loader and the LIBERO simulator glue | `==0.5.1` (`pyproject.toml`) | Apache-2.0 | stated by project — re-verify at 0.5.1 |
| `hf-libero` (LIBERO) | the simulator and its task assets | pulled by `lerobot[libero]` (Linux only) | MIT (LIBERO); assets carry the benchmark's own terms | stated by project — re-verify the asset terms at the installed version |
| MuJoCo | physics engine under LIBERO | pulled by the simulator | Apache-2.0 | stated by project |
| `torch`, `transformers` | inference stack for SmolVLA | pulled by `lerobot[smolvla]` | BSD-3-Clause (torch), Apache-2.0 (transformers) | stated by project |
| `HuggingFaceVLA/smolvla_libero` | the checkpoint the published body measured | the revision the run resolves (`deployed_policy.checkpoint_revision` when recorded) | model-card licence at that revision | **unverified** — read the model card at the resolved revision and record it |
| `lerobot/pi05_libero_finetuned_v044` | the preliminary second-architecture checkpoint | the revision the 18 September run resolved | model-card licence at that revision | **unverified** — same |
| the LIBERO-Object task suite and its object meshes | what the policy acts in | as shipped by `hf-libero` | the benchmark's terms | **unverified** at asset level |
| `numpy`, `pydantic`, `typer`, `rich`, `pyyaml` | the CPU core | `uv.lock` | BSD-3-Clause / MIT / MIT / MIT / MIT | checked (metadata, this environment) |
| `cryptography` | Ed25519 signing (`[attest]`) | `uv.lock` | Apache-2.0 OR BSD-3-Clause | checked (metadata, this environment) |
| a customer's own checkpoint and data | the assessed system | per engagement | the customer's permission, in the contract | recorded per engagement |

## Public attribution

Attribution is added to a delivery pack only where a licence requires it, in the form it requires
(a notice file for Apache-2.0 redistribution; a citation where a benchmark asks for one). Nothing
about the maintainer's employment history is published, here or in a pack.

## What closes the unverified rows

Before the first engagement: open each model card at the revision the run will load, record the
licence text and the revision in the engagement log, and change the row to `checked (model card,
revision …)`. Do the same for the LIBERO asset terms. If a term forbids the use, the configuration
is not supported for that engagement and the customer is told before anything runs.
