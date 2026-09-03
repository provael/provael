"""Guard that the Modal examples expose what ``modal run`` actually looks for.

WHY THIS EXISTS. ``examples/gpu-ci/modal_provael_gpu.py`` built its app inside ``build_app()`` so
the module would import without modal installed. ``modal run`` scans a module's GLOBAL scope for
an app and an entrypoint, found neither, and printed "has no functions or local entrypoints". The
scheduled workflow piped that into ``tee``, took tee's exit status, and reported success. The lane
was green and measuring nothing for 22 days; only the freshness badge ageing to 22 days showed it.

This parses the files rather than importing them, so it runs on the CPU lane where modal is absent
— the same lane that has to keep the expensive lane honest.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

EXAMPLES = sorted((pathlib.Path(__file__).parent.parent / "examples" / "gpu-ci").glob("modal_*.py"))


def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_declares_a_module_level_app(path: pathlib.Path) -> None:
    """``modal run`` resolves the app from global scope; a nested one is invisible to it."""
    assigned = {
        target.id
        for node in _tree(path).body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    assert "app" in assigned, (
        f"{path.name} defines no module-level `app`. If it is built inside a function, "
        "`modal run` reports 'has no functions or local entrypoints' and exits."
    )


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_declares_a_module_level_entrypoint(path: pathlib.Path) -> None:
    """At least one global-scope function must carry ``@app.local_entrypoint()``."""
    decorated = [
        node
        for node in _tree(path).body
        if isinstance(node, ast.FunctionDef)
        for dec in node.decorator_list
        if "local_entrypoint" in ast.dump(dec)
    ]
    assert decorated, f"{path.name} has no module-level @app.local_entrypoint()."


def test_the_guard_can_actually_fail() -> None:
    """Pin the regression against the exact shape that shipped, so it cannot stop matching."""
    shipped = ast.parse(
        "def build_app():\n"
        "    import modal\n"
        "    app = modal.App('x')\n"
        "    @app.local_entrypoint()\n"
        "    def main() -> None: ...\n"
        "    return app\n"
    )
    names = {
        t.id
        for n in shipped.body
        if isinstance(n, ast.Assign)
        for t in n.targets
        if isinstance(t, ast.Name)
    }
    assert "app" not in names, "the nested-app shape must still be detectable as broken"


GPU_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "examples" / "gpu-ci" / "modal_provael_gpu.py"


def test_the_gpu_lane_returns_its_artifacts_not_only_stdout() -> None:
    """The measurement happening and the measurement being RECORDED are different events.

    `redteam()` used to return `subprocess.run(...).stdout` alone, so `report.json` was written
    inside the Modal container and died with it. The workflow looks for that file on the RUNNER,
    found nothing, warned, and exited 0 — so every run from 30 Aug to 3 Sep 2026 reached a real
    policy, printed a real ASR, and recorded nothing while `watch/freshness.json` aged past 24 days
    and provael.com served STALE MEASUREMENT off the back of it (#181).

    Third time this lane has been green while producing nothing, after the nested app and the
    missing `pipefail`. Parsed rather than imported, because the CPU lane has no modal.
    """
    tree = ast.parse(GPU_SCRIPT.read_text(encoding="utf-8"))
    fn = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "redteam"), None
    )
    assert fn is not None, "examples/gpu-ci/modal_provael_gpu.py no longer defines redteam()"

    returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return) and n.value is not None]
    assert returns, "redteam() returns nothing"
    assert any(isinstance(r.value, ast.Tuple) for r in returns), (
        "redteam() must return the artifacts alongside stdout. Returning stdout alone is #181: the "
        "container is deleted with report.json still in it, and the ledger step records nothing "
        "while the job stays green."
    )

    src = GPU_SCRIPT.read_text(encoding="utf-8")
    assert "rglob" in src, "redteam() no longer collects the artifact files it must return"
    assert "write_text" in src, (
        "the local entrypoint must WRITE the returned artifacts to the runner; returning them and "
        "printing them leaves the ledger step with nothing to find"
    )
