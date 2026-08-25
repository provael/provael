"""Every CPU-only example actually runs, unmodified, with no arguments.

WHY THIS EXISTS. `examples/python-api/` had four scripts and nothing executed any of them — not a
test, not a workflow. An example is the one artifact whose whole value is that it runs; when it
breaks it breaks silently, and the reader who finds out is a stranger evaluating the project.

That is not a hypothetical cost here. The benchmark census this project already tracks found that
code running with ZERO modification predicted citation density at p = 0.005, and that code needing
any modification was statistically indistinguishable from shipping no code at all. A broken example
is not a neutral artifact; it is worse than the empty directory it replaced.

Run as subprocesses rather than imported, because importing would exercise a code path no reader
uses. The reader types the command in the docstring, so that is what this types.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples" / "python-api"

#: Scripts that are runnable with no arguments, no GPU, no network and no optional extra. A script
#: needing any of those belongs in a gated lane, not here — and adding one to this list without
#: meeting the bar is how a suite starts skipping instead of failing.
CPU_ONLY = sorted(p.name for p in EXAMPLES.glob("*.py"))


def test_the_example_directory_is_not_empty() -> None:
    """Guard the guard: an empty glob parametrises to nothing and passes silently."""
    assert len(CPU_ONLY) >= 4, f"only {len(CPU_ONLY)} examples found in {EXAMPLES}"


@pytest.mark.parametrize("script", CPU_ONLY)
def test_example_runs_unmodified(script: str) -> None:
    proc = subprocess.run(
        [sys.executable, str(EXAMPLES / script)],
        cwd=ROOT, capture_output=True, text=True, timeout=300, check=False,
    )
    assert proc.returncode == 0, (
        f"examples/python-api/{script} exits {proc.returncode}. An example that does not run is "
        f"worse than no example.\n--- stderr ---\n{proc.stderr[-2000:]}"
    )
    assert proc.stdout.strip(), f"examples/python-api/{script} ran but printed nothing"


def test_the_benign_floor_example_prints_both_arms_with_an_interval() -> None:
    """The specific thing that example is FOR: neither headline alone, and the floor's interval.

    Asserted on the output rather than on the source, because a reader copies what it prints.
    """
    proc = subprocess.run(
        [sys.executable, str(EXAMPLES / "benign_floor_beside_asr.py")],
        cwd=ROOT, capture_output=True, text=True, timeout=300, check=True,
    )
    out = proc.stdout
    assert "adversarial ASR" in out
    assert "benign floor" in out
    # The interval is the point: 0/5 and 0/500 both render as "0.0%", and only one is evidence.
    assert "[" in out and "]" in out, "the benign floor printed no confidence interval"
