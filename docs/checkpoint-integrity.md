# Checkpoint supply-chain integrity

A pre-load control for the CI gate: **are we about to load the weights we think we are, in a format
that is safe to load, and will loading the checkpoint run code nobody reviewed?**

!!! warning "This is not an attack-success rate, and it does not reduce one"
    Checkpoint integrity is a **supply-chain control**. It produces a **verdict**, not a rate. A
    checkpoint that passes every check on this page can still be driven off-task by a reworded
    instruction at exactly the rate the [ASR](measure-2-7.md) reports. The two travel in the same
    evidence pack because an assessor needs both — they are **not the same claim and must never be
    added together**. Nothing here may be reported as, aggregated into, or described as moving an
    ASR.

## Why

Provael's [SECURITY.md](https://github.com/provael/provael/blob/main/SECURITY.md) documents
[**CVE-2026-25874**](https://nvd.nist.gov/vuln/detail/CVE-2026-25874) — LeRobot unauthenticated
pickle-deserialization RCE (CVSS 9.8), affecting `lerobot` through `0.5.1`. The flaw is in LeRobot's
**async-inference `PolicyServer`**, which `pickle.loads` untrusted payloads over an unauthenticated
gRPC endpoint (TCP/50051).

**Provael never starts that PolicyServer or any gRPC endpoint** — it uses LeRobot only for
in-process policy loading and the LIBERO simulator, behind the `[lerobot]` extra and the
`PROVAEL_INTEGRATION=1` gate, so that specific code path is not reachable through Provael. The
proposed upstream fix was LeRobot PR #3048, which replaced pickle with safetensors + JSON. It closed unmerged on 7 October 2026 (see [SECURITY.md](https://github.com/provael/provael/blob/main/SECURITY.md)).

The *class* of risk is broader than the one CVE, though, and it does reach us: **loading a pickle
executes it.** Any tool that fetches a third-party checkpoint and loads it is running the
checkpoint author's code. Provael's own incident tracker names this risk publicly; until 0.27.0 the
reusable Action did not check for it.

## Where it maps

**EAI03 — Model & pipeline poisoning, backdoors & supply chain.** The mapping is in the title.

Deliberately **not** EAI07 (CPS, firmware, comms & teleoperation compromise), whose catalog entry
declares that area out of scope. That scoping is about **attacks Provael does not run**, and filing
a control there would imply this closes some of it. It does not. The PolicyServer RCE that motivates
this has an EAI07 flavour, but what the gate inspects is the **checkpoint artifact**, which is
EAI03.

Note EAI03 already ships attacks (the `backdoor` family screens objective-decoupled triggers). This
control sits *alongside* that, not inside it: the backdoor family produces a rate, this produces a
verdict.

## What it checks

| Check | Default | Why |
| --- | --- | --- |
| Digest matches a pinned SHA-256 | **fail closed** | "We did not check" and "we checked and it matched" must not produce the same verdict |
| Refuses pickle-format weights | **fail closed** | Loading a pickle executes it |
| Prefers safetensors | advisory | Where both are present the checkpoint is loadable safely — load the safetensors and do not fall back |
| Refuses a checkpoint whose JSON chooses code that runs on load | **fail closed** | lerobot loads whatever the checkpoint's files name; see [the next section](#what-loading-would-run) |

The digest is computed over the checkpoint's weight files, **order- and layout-independent** (per-file
SHA-256, sorted, then hashed), so a pin taken once re-checks anywhere.

Every fail-closed behaviour has an **explicit opt-out**, matching how the rest of the gate handles
defaults (`fail-on-regression` defaults true). An opt-out is recorded in the evidence — never
silent.

## What loading would run

Before it loads any weights, lerobot 0.5.1 reads `config.json`, `policy_preprocessor.json` and
`policy_postprocessor.json` from the checkpoint, then loads what they name: the backbone
in `vlm_model_name`, each tokenizer step's `tokenizer_name`, the policy class its `type` picks
(several load further models named in their own config), and, for a step with no registered name,
whatever its `class` path imports. transformers 5.3.0, which lerobot 0.5.1 pins exactly, adds
**PYSEC-2026-2290**: a repo loaded that way can turn remote code on for itself. Releases up to
0.47.0 do not check any of this, so there, naming a checkpoint with `provael attack --model` can
run code its author chose.

From 0.48.0, `provael attack` reads those three files before it imports
anything from lerobot, and refuses the checkpoint if they:

| Refused | Why |
| --- | --- |
| turn `trust_remote_code` on anywhere, or carry `auto_map` in `config.json` | both ask transformers to run code shipped in a repo |
| name a `vlm_model_name` or tokenizer repo outside the three below | lerobot loads it with `from_pretrained` |
| use a policy `type` other than `smolvla`, `pi0` or `pi05` | other types load models their own config names, and for `pi0_fast` and `groot` lerobot passes `trust_remote_code=True` itself |
| use a processor step this project has not read in lerobot 0.5.1, or a step with no registered name | lerobot builds an unknown step from its config, and imports a nameless step's `class` and calls it |
| name a step `class` outside lerobot | the same import, of code from anywhere |
| build `action_tokenizer_processor` without `trust_remote_code: false` | lerobot 0.5.1 defaults it to true |
| set `use_peft` | lerobot then loads a second checkpoint, named in `adapter_config.json`, that this check never reads |

The three repos were read off known-good checkpoints on the Hub on 10 November 2026:
`HuggingFaceTB/SmolVLM2-500M-Instruct` from `HuggingFaceVLA/smolvla_libero`,
`HuggingFaceTB/SmolVLM2-500M-Video-Instruct` from `lerobot/smolvla_base`, and
`google/paligemma-3b-pt-224` from `lerobot/pi05_libero_finetuned_v044`. All three checkpoints
pass. A missing file is not a problem by itself; a Hub checkpoint with no `config.json` is not
loaded, since lerobot has nothing to build.

For a Hub checkpoint the three files are read at one commit, and lerobot is handed that snapshot
instead of the repo id, so an owner who changes the repo during the load does not change what
loads. `provael verify-checkpoint --path` makes the same check on every checkpoint directory under
the path, each `snapshots/<commit>/` of a Hugging Face cache included, and fails closed the same
way. A path holding no `config.json` or processor file is recorded as not checked.

To load a refused checkpoint anyway, set `PROVAEL_TRUST_CHECKPOINT_CODE=1` in the environment of
the command that loads it. `provael attack` then warns, naming every problem, and goes on;
`verify-checkpoint` passes and records each problem as accepted. The execution manifest records
the variable. Setting it accepts code the checkpoint's author chose, so set it only for a
checkpoint you trust, on a machine with no secrets to lose.

## Use it

```bash
# Print the digest to pin (run once, against a checkpoint you trust)
provael verify-checkpoint --checkpoint HuggingFaceVLA/smolvla_libero \
    --path ~/.cache/huggingface/hub/models--HuggingFaceVLA--smolvla_libero \
    --no-require-digest

# Then pin it. A mismatch exits non-zero and the policy is never loaded.
provael verify-checkpoint --checkpoint HuggingFaceVLA/smolvla_libero \
    --path ~/.cache/... --digest <sha256> --out runs/gate
```

In the Action, the step runs **before** the policy is instantiated — the check is worthless after
the load:

```yaml
- uses: provael/provael@v0.48.0
  with:
    policy: smolvla
    suite: libero
    checkpoint-path: ~/.cache/huggingface/hub/models--HuggingFaceVLA--smolvla_libero
    checkpoint-digest: ${{ vars.SMOLVLA_LIBERO_DIGEST }}
    # require-checkpoint-digest: true    # default — omit it
    # allow-pickle-checkpoint: false     # default — omit it
```

## What lands in the evidence pack

`checkpoint-integrity.json` in the run directory, and a `checkpointIntegrity` block in the SARIF
run properties — **nested under its own key**, never flattened beside `adversarialAsr`, so nothing
in it can be read as a rate:

```json
{
  "verdict": "pass",
  "eaiId": "EAI03",
  "format": "safetensors",
  "digestSha256": "…",
  "digestMatch": true,
  "pickleAllowed": false,
  "note": "Supply-chain control, not an adversarial-robustness result. This verdict is not an attack-success rate and does not reduce one."
}
```

The `note` travels with the record so the distinction survives being pasted into a slide.

## Honest scope

- It verifies **bytes and format**, not the model's behaviour. A digest match tells you the weights
  are the ones you pinned; it says nothing about whether those weights are backdoored.
- Pinning a digest of a checkpoint you never audited pins *that* checkpoint, faithfully. Integrity
  is not provenance.
- `allow-pickle-checkpoint: true` **accepts** code execution from the checkpoint author. It does not
  make it safe, and the evidence says so. `PROVAEL_TRUST_CHECKPOINT_CODE=1` is the same kind of
  acceptance, for the code a checkpoint's JSON makes lerobot load.
- The code check reads JSON and trusts the three backbone repos it allows as their owners publish
  them. The weights still load by repo id, so they are not pinned to the commit the check read;
  they are safetensors, which hold no code, and `--digest` pins them.
- This is not a certificate and not a notified-body opinion — the same scope that applies to every
  other artifact Provael emits.
