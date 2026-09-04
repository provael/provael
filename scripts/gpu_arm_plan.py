"""Print what one GPU arm will cost, BEFORE `.github/workflows/gpu-arm.yml` spends it.

WHY THIS IS A SCRIPT AND NOT A HEREDOC IN THE WORKFLOW. It started as one, and it was wrong twice
in the same twenty lines: ``STAGES`` is an *annotated* assignment so walking for ``ast.Assign``
found nothing and raised ``StopIteration``, and ``ast.Dict`` exposes ``.keys``/``.values`` rather
than ``.items``. Both would have surfaced only on a dispatch, in the one step whose entire job is
to speak before money is spent. This repo already draws that line — the Action's gate logic lives
in ``scripts/action/`` rather than inside ``action.yml`` "lifted out specifically so it can be
tested" — and a cost estimate is exactly the kind of logic that must not be first exercised in
production.

WHY IT EXECUTES THE EXAMPLE INSTEAD OF PARSING IT. ``STAGES`` holds ``"tasks": ALL_TASKS``, and
``ALL_TASKS`` is computed (``",".join(f"libero_object/{i}" for i in range(10))``), so no amount of
``ast.literal_eval`` recovers it — a parser would have to re-implement the module to read it. So
the module is executed with a **stub modal** injected instead: nothing here needs the real client,
the CPU lane does not have it, and a stub keeps this runnable (and therefore testable) wherever
``provael``'s own tests run. The stub is inert — attribute access and calls return more stub — so
``modal.App(...)``, the image chain and the ``@app.function`` decorators all evaluate to nothing.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import types
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "gpu-ci" / "modal_libero_suite.py"

#: Modal's own published L4 rate. The ceiling below is only as honest as this number, so it lives
#: in one place and is named — `modal_libero_suite.py` quotes the same figure in its cost table.
L4_USD_PER_HOUR = 0.7992


class _Inert:
    """Absorbs every attribute access, call and decoration, and returns more of itself."""

    def __getattr__(self, _name: str) -> _Inert:
        return self

    def __call__(self, *_args: Any, **_kwargs: Any) -> _Inert:
        return self


def stages() -> dict[str, dict[str, str]]:
    """The example's own ``STAGES`` dict, with computed values resolved."""
    stub = types.ModuleType("modal")
    for name in ("App", "Image", "Volume", "NetworkFileSystem", "Secret", "Mount"):
        setattr(stub, name, _Inert())
    saved = sys.modules.get("modal")
    sys.modules["modal"] = stub
    # The example raises SystemExit at import if PROVAEL_STAGE names an unknown stage. `timing` is
    # its own default and always valid, so set it rather than inheriting whatever the caller has.
    saved_stage = os.environ.get("PROVAEL_STAGE")
    os.environ["PROVAEL_STAGE"] = "timing"
    try:
        # The same importlib idiom `tests/test_check_changelog_entry.py` uses to reach a script
        # that is not on the import path.
        spec = importlib.util.spec_from_file_location("modal_libero_suite", EXAMPLE)
        if spec is None or spec.loader is None:  # pragma: no cover - only on a deleted example
            raise SystemExit(f"cannot load {EXAMPLE}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if saved is None:
            sys.modules.pop("modal", None)
        else:
            sys.modules["modal"] = saved
        if saved_stage is None:
            os.environ.pop("PROVAEL_STAGE", None)
        else:
            os.environ["PROVAEL_STAGE"] = saved_stage
    result: dict[str, dict[str, str]] = module.STAGES
    if not result:
        raise SystemExit(f"{EXAMPLE} defines no STAGES")
    return result


def plan(stage: str) -> str:
    """A Markdown summary of one stage: its config, its shard count and its hard cost ceiling."""
    every = stages()
    if stage not in every:
        raise SystemExit(f"unknown stage {stage!r}; the example defines {sorted(every)}")
    cfg = every[stage]
    shards = len(cfg["tasks"].split(","))
    hours = int(cfg["timeout"]) / 3600
    lines = [f"### Arm: `{stage}`", "", "| field | value |", "| --- | --- |"]
    lines += [f"| `{key}` | `{value}` |" for key, value in cfg.items()]
    lines += [
        f"| shards | {shards} (one container per task) |",
        f"| **hard ceiling** | **~${shards * hours * L4_USD_PER_HOUR:,.2f}** "
        f"({shards} x {hours:.2f} h x ${L4_USD_PER_HOUR}/L4-hour) |",
        "",
        "The ceiling is what hung containers bill regardless of what they were asked to do — it is "
        "the number that matters, not the expected spend. The stage's own comment in "
        "`examples/gpu-ci/modal_libero_suite.py` derives the expected figure.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print a GPU arm's plan and cost ceiling.")
    parser.add_argument("stage", help="stage name, as defined in the example's STAGES")
    print(plan(parser.parse_args(argv).stage))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
