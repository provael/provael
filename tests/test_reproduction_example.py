"""`examples/lerobot_eval_smolvla_libero.py` must stay a reproduction, not merely a script.

WHY THIS EXISTS. The example advertises specific numbers — `roleplay` 44/50, benign control 2/50 —
and a specific configuration behind them. Both are copies of facts that live in
``results/smolvla_libero_object_suite/``. Copies drift, and this particular copy drifts *silently*:
the file needs a GPU and a 15-hour run to execute, so nothing in CI would ever notice that its
claimed baseline stopped matching the artifact it claims to reproduce. A stranger would find out
after spending $12.

So these tests pin the copy against the original, and exercise the one path that CAN run on CPU.
They deliberately do not import the module at collection time under a name that would pull torch —
``--dry-run`` is the contract that it stays importable on a laptop, and it is tested as a
subprocess for exactly that reason.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
EXAMPLE = REPO / "examples" / "lerobot_eval_smolvla_libero.py"
AGGREGATE = REPO / "results" / "smolvla_libero_object_suite" / "aggregate.json"
SHARD = REPO / "results" / "smolvla_libero_object_suite" / "libero_object_0" / "report.json"


@pytest.fixture(scope="module")
def example() -> Any:
    """Import the example as a module. Safe: nothing heavy is imported at its module scope."""
    spec = importlib.util.spec_from_file_location("_provael_reproduction_example", EXAMPLE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def aggregate() -> dict[str, Any]:
    return json.loads(AGGREGATE.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_the_example_imports_without_the_gpu_stack(example: Any) -> None:
    """Module scope must not pull torch, or `--dry-run` stops working on a laptop.

    The fixture above already proves it: `exec_module` runs the whole file top to bottom, and CPU
    CI has no torch installed, so a top-level `from provael.runner import run` would raise here
    rather than reach this assertion.
    """
    assert example.CHECKPOINT == "HuggingFaceVLA/smolvla_libero"


def test_reference_numbers_match_the_committed_run(example: Any, aggregate: dict[str, Any]) -> None:
    """The advertised baseline is the artifact's, not a retyped memory of it.

    `aggregate.json` records McNemar discordant counts rather than raw rates, so the successes are
    reconstructed from them: successes = attack_only + (pairs where both fired). With the benign
    arm at b/n, `both = benign_total - benign_only`, so `successes = attack_only + benign_total -
    benign_only`. That identity is why this test can check the example against the artifact without
    the example needing to ship a copy of the raw per-episode data.
    """
    mcnemar = aggregate["mcnemar"]
    benign_successes, benign_n = example.REFERENCE["none"]

    for arm, (claimed_successes, claimed_n) in example.REFERENCE.items():
        if arm == "none":
            continue
        assert arm in mcnemar, f"{arm!r} is advertised by the example but absent from aggregate.json"
        row = mcnemar[arm]
        derived = row["attack_only"] + benign_successes - row["benign_only"]
        assert derived == claimed_successes, (
            f"the example advertises {arm} at {claimed_successes}/{claimed_n}, but aggregate.json "
            f"implies {derived}. One of them is stale."
        )
        assert claimed_n == benign_n == row["attack_only"] + row["benign_only"] + row["concordant"]


def test_reference_mcnemar_p_value_is_the_committed_one(
    example: Any, aggregate: dict[str, Any]
) -> None:
    """The headline p-value is quoted in the example, the finding and the README. Pin it once."""
    assert aggregate["mcnemar"]["roleplay"]["p_value"] == example.REFERENCE_MCNEMAR_ROLEPLAY


def test_the_config_matches_the_shard_that_produced_the_numbers(example: Any) -> None:
    """Every knob the example sets is read back out of a real shard's report.

    This is the test that would have caught a plausible and expensive mistake: setting `episodes=1,
    episodes_per_seed=5` instead of `episodes=5, episodes_per_seed=1`. Both produce 5 episodes per
    cell; only one produces 5 distinct *seeds*, and the difference decides whether the per-seed
    variance is computable at all.
    """
    shard = json.loads(SHARD.read_text(encoding="utf-8"))
    assert shard["model"] == example.CHECKPOINT
    assert shard["horizon"] == example.HORIZON
    assert shard["seeds"] == example.EPISODES, "episodes must equal the shard's distinct seed count"
    assert shard["episodes"] == example.EPISODES * example.EPISODES_PER_SEED
    assert len(example.TASKS) == 10
    assert shard["tasks"] == ["libero_object/0"]  # one task per shard; the example runs all ten
    assert example.TASKS[0] == "libero_object/0"


def test_the_benign_control_cannot_be_dropped_from_the_arm_list(example: Any) -> None:
    """`none` is load-bearing, not decorative — every McNemar pair is built against it."""
    assert "none" in example.ATTACK_FAMILIES
    assert "none" in example.REFERENCE


def test_the_arms_resolve_to_exactly_the_committed_set(example: Any) -> None:
    """Families expand; the expansion must still be the eight arms the reference run measured."""
    from provael.attacks.registry import resolve_attacks

    resolved = {attack.name for attack in resolve_attacks(list(example.ATTACK_FAMILIES))}
    shard = json.loads(SHARD.read_text(encoding="utf-8"))
    assert resolved == set(shard["by_attack"]), (
        "the example's attack families no longer expand to the arms in the committed run"
    )


def test_dry_run_succeeds_as_a_subprocess() -> None:
    """The smoke test a stranger runs, run the same way they run it.

    A subprocess rather than a function call, because the contract is about the *file* being
    executable — including its argparse wiring and its exit code, neither of which an in-process
    call to `main()` fully exercises.
    """
    proc = subprocess.run(
        [sys.executable, str(EXAMPLE), "--dry-run"],
        cwd=REPO, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, f"dry run failed:\n{proc.stdout}\n{proc.stderr}"
    assert "Dry run OK" in proc.stdout
    # The plan must print the honest measured cost, not a rounded-down one.
    assert "$12.29" in proc.stdout
    assert "350 measured" in proc.stdout


def test_the_pinned_lerobot_version_is_the_one_that_produced_the_numbers() -> None:
    """0.6.x exists and is newer. The result was measured on 0.5.1, so 0.5.1 is what ships.

    Pinning forward would turn a reproduction into a script that merely runs. If someone bumps this
    pin, they must also re-measure — and this test is where that conversation starts.
    """
    text = EXAMPLE.read_text(encoding="utf-8")
    assert 'lerobot[libero]==0.5.1' in text
    assert "0.6" in text, "the newer versions must be acknowledged, not silently ignored"
