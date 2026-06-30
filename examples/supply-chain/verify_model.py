"""Verify a policy checkpoint before you trust its ASR.

A red-team result is only as trustworthy as the model you ran it on. This example shows the two
cheap, high-value checks to run *before* red-teaming:

  1. Prefer **safetensors** over pickle. 2025 research shows pickle scanners are bypassable
     (NullifAI, CVE-2025-46417), so a pickle policy is a supply-chain risk. Warn/refuse on it.
  2. Verify a signature with OpenSSF **model-signing** (Sigstore) when one is present
     (https://github.com/sigstore/model-transparency).

    pip install model-signing       # optional, for step 2
    python examples/supply-chain/verify_model.py /path/to/model_dir

With no path it just explains the checks. The signature check is skipped (with a note) if
model-signing isn't installed.
"""

from __future__ import annotations

import sys
from pathlib import Path


def check_format(model_dir: Path) -> bool:
    """Warn if the checkpoint ships pickle weights and no safetensors."""
    has_safetensors = any(model_dir.rglob("*.safetensors"))
    pickles = [*model_dir.rglob("*.bin"), *model_dir.rglob("*.pt"), *model_dir.rglob("*.pkl")]
    if has_safetensors:
        print("OK: safetensors weights present.")
        return True
    if pickles:
        print(f"WARNING: pickle weights and no safetensors ({len(pickles)} file(s)). "
              "Pickle is unsafe to load from an untrusted source — prefer safetensors.")
        return False
    print("note: no recognised weight files found.")
    return True


def check_signature(model_dir: Path) -> None:
    """Verify a Sigstore model signature if model-signing is installed and a sig is present."""
    try:
        import model_signing  # noqa: F401
    except ImportError:
        print("note: model-signing not installed — skipping signature verification "
              "(pip install model-signing).")
        return
    print("model-signing available — verify with: "
          f"model_signing verify sigstore --signature {model_dir}/model.sig {model_dir}")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        return
    model_dir = Path(sys.argv[1])
    ok = check_format(model_dir)
    check_signature(model_dir)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
