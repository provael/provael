# Accelerators — and why TPU is not supported yet

Provael records **where** a run executed. The `RunConfig.accelerator` field (CLI: `--accelerator`)
takes one of:

| value | meaning |
| --- | --- |
| `cpu` | CPU (the deterministic stub core runs here) |
| `cuda` | an NVIDIA GPU (the real SmolVLA × LIBERO transfer path) |
| `mps` | Apple-silicon Metal |
| _unset_ | let the policy choose its own device |
| `tpu` | **reserved but unimplemented** — raises `NotImplementedError` |

The value is threaded into the report and the signed attestation, so a measured number always says
what hardware and precision produced it (D6).

## Why `tpu` raises instead of running

Every policy Provael targets today — SmolVLA, OpenVLA/-OFT, π0, GR00T — ships a **PyTorch**
inference path with `cpu` / `cuda` (and often `mps`) support. None ships a first-class, verified TPU
inference path. Silently "supporting" TPU would mean either (a) a JAX/TPU reimplementation of each
policy's forward pass that no upstream maintains, or (b) an `torch_xla` bridge whose numerical and
performance parity with the CUDA path is unverified for these VLA-class models. Either route would
produce a number we could not honestly attest as equivalent to the CUDA measurement — so instead of
guessing, `accelerator='tpu'` fails loudly and points at this page and ROADMAP §8.

## The revisit trigger (both required)

We will implement `tpu` when **both** of these hold — not one:

1. **TorchTPU is generally available** (a stable, non-experimental PyTorch-on-TPU path), and
2. **a third-party, VLA-class policy ships verified PyTorch TPU inference at parity** with its CUDA
   path (so we are validating an existing path, not authoring one).

Until both land, the honest answer is: use the PyTorch `cpu` / `cuda` / `mps` path every current
target already provides. This mirrors Provael's general stance — we measure what a real, maintained
inference path does; we do not stand up an unverified one to produce a number.

See [ROADMAP §8](https://github.com/provael/provael) for the decision record (D5/§8).
