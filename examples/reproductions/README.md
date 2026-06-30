# Reproduce published VLA attacks

The VLA-attack literature is scattered across one-off repos with no common harness. `provael
reproduce` points Provael's templated attack families at the **threat class** each paper
describes, so you can run a paper's idea in one command and read an ASR.

```bash
provael list-reproductions          # the catalogue
provael reproduce freezevla         # run it on the CPU stub (instant)
```

| name | paper | EAI | Provael family |
| --- | --- | --- | --- |
| `freezevla` | FreezeVLA (arXiv:2509.19870) | EAI04 | `freeze` |
| `openvla-patch` | OpenVLA adversarial patch (arXiv:2511.21192) | EAI02 | `patch` |
| `badvla` | BadVLA (arXiv:2505.16640) | EAI02 | `patch`, `decoy_object` |
| `robopair` | RoboPAIR (arXiv:2410.13691) | EAI01 | `roleplay` |

## Honesty (the whole point of this feature)

`reproduce` is built so it can never overclaim:

- The **paper's** reported ASR is **cited**, shown in a separate line from Provael's **measured**
  ASR for the run you actually ran. Provael never claims the paper's number as its own.
- On the deterministic `stub`, the measured numbers are **properties of the test fixture**, not of
  any real VLA — the command prints this and tells you how to run the real model.
- Provael reproduces the *threat class* with a templated, auditable family; it does **not** ship
  each paper's gradient/optimisation artifact. Each entry states the mapping.
- No "first" / "SOTA" claims.

## Run against a real model

```bash
pip install 'provael[lerobot]'
PROVAEL_INTEGRATION=1 provael reproduce freezevla \
    --policy smolvla --suite libero --model HuggingFaceVLA/smolvla_libero
```

Then the measured ASR is a real-model number (seeded, not byte-deterministic) you can compare —
with its own 95% CI and benign-FPR control — against the paper's reported figure.
