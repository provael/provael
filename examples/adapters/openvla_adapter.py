"""Red-team OpenVLA / OpenVLA-OFT — the model-agnostic, NON-LeRobot path.

OpenVLA loads directly through Hugging Face ``transformers`` (no LeRobot), which is exactly why
it's a good demonstration that Provael is model-agnostic. Run it from the CLI:

    pip install 'provael[openvla]'              # GPU machine
    export PROVAEL_INTEGRATION=1
    provael attack \\
        --policy openvla \\
        --model moojink/openvla-7b-oft-finetuned-libero-object \\
        --unnorm-key libero_object \\
        --suite libero \\
        --attacks none,instruction,visual,injection \\
        --seeds 10 --seed 0 --out runs/openvla_libero

This script shows the equivalent Python wiring. On a CPU box (no ``[openvla]`` extra) it prints
the install hint instead of crashing — so it's safe to run anywhere.

NOTE: ``--unnorm-key`` is checkpoint-specific (the action-normalization stats id, usually the
fine-tuning dataset). OpenVLA lists valid keys in its error if the one you pass is unknown.
"""

from __future__ import annotations

import numpy as np

from provael.policies.openvla_adapter import MissingOpenVLAError, OpenVLAAdapter


def main() -> None:
    adapter = OpenVLAAdapter(
        model_id="moojink/openvla-7b-oft-finetuned-libero-object",
        unnorm_key="libero_object",
    )
    try:
        adapter.load()
    except MissingOpenVLAError as exc:
        print("OpenVLA is not available in this environment:\n")
        print(exc)
        print("\nThis is expected on a CPU box. Install 'provael[openvla]' on a GPU to run it.")
        return

    # A real run drives the LIBERO suite via the CLI (above). Here we show a single forward step
    # on a dummy frame to illustrate the adapter contract: (observation, instruction) -> action.
    observation = {"image": np.zeros((224, 224, 3), dtype=np.uint8)}
    action = adapter.act(observation, "pick up the cup and put it on the plate")
    print("action:", action)


if __name__ == "__main__":
    main()
