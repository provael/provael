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
import yaml

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


# --------------------------------------------------------------------------- #
# where the artifacts went — the contract between the example and the workflow
# --------------------------------------------------------------------------- #

WORKFLOW = pathlib.Path(__file__).resolve().parents[1] / ".github" / "workflows" / "gpu-scheduled.yml"


def _module_constant(path: pathlib.Path, name: str) -> str:
    """Read a module-level string constant without importing the module (no modal on this lane)."""
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            assert isinstance(node.value, ast.Constant) and isinstance(node.value.value, str), (
                f"{path.name}: {name} must be a plain string constant"
            )
            return node.value.value
    raise AssertionError(f"{path.name} no longer defines a module-level {name}")



def _ledger_script() -> str:
    """The ledger step's SHELL, with comments stripped.

    Comments are stripped on purpose. This repo writes down the bug each guard exists to prevent,
    at the site of the guard — so the ledger step's own comment quotes the mtime search it
    replaced. Matching against the raw file would make that explanation indistinguishable from a
    regression, and the only way to keep the guard green would be to delete the explanation.
    ``tests/test_version_consistency.py`` records the same trap from the other side.
    """
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["gpu-redteam"]["steps"]
    run = next(
        (s["run"] for s in steps if "ledger" in str(s.get("name", "")).lower()),
        None,
    )
    assert run is not None, (
        f"{WORKFLOW.name} no longer has a step whose name mentions the ledger; the recording "
        f"step is what moves the freshness badge and it must stay identifiable"
    )
    return "\n".join(
        line for line in run.splitlines() if not line.lstrip().startswith("#")
    )


def test_the_output_directory_is_one_fact_not_two() -> None:
    """The run's output path is declared once; both users of it read that declaration.

    It used to be the same literal typed twice — once for the CLI's ``--out`` inside the container,
    once for the mirror path in the local entrypoint — which is the shape #187 introduced when it
    gave the entrypoint artifacts to write. Two copies of one fact is the defect this repo keeps
    finding; here the second copy also had nothing checking it against the first.
    """
    out_dir = _module_constant(GPU_SCRIPT, "OUT_DIR")
    occurrences = GPU_SCRIPT.read_text(encoding="utf-8").count(f'"{out_dir}"')
    assert occurrences == 1, (
        f"{GPU_SCRIPT.name} spells the literal {out_dir!r} {occurrences} times. It is the run's "
        f"output directory and must be written once, as OUT_DIR, then referenced."
    )


def test_the_gpu_lane_declares_where_its_artifacts_went() -> None:
    """Writing the artifacts is not enough; the workflow has to be told where they are.

    THE FAILURE. On 4 September 2026 — the first scheduled run after #181's fix landed — this lane
    reached a real policy, printed ``Adversarial ASR: 33.3% (4/12)``, wrote three artifacts to the
    runner, and the ledger step reported that it had produced none. #181 made the lane write its
    measurement; nothing made the lane say where it put it.
    """
    src = GPU_SCRIPT.read_text(encoding="utf-8")
    out_dir_file = _module_constant(GPU_SCRIPT, "OUT_DIR_FILE")
    assert out_dir_file, "OUT_DIR_FILE must name a file"
    assert "pathlib.Path(OUT_DIR_FILE).write_text" in src, (
        "the local entrypoint must WRITE OUT_DIR_FILE. Without it the workflow has no way to "
        "learn where the artifacts landed and must fall back to guessing — which is #188."
    )


def test_the_workflow_reads_the_declared_path_instead_of_searching_by_mtime() -> None:
    """The ledger step must read OUT_DIR_FILE, and must not go back to the mtime search.

    ``find . -name report.json -newer gpu-scheduled-report.txt`` cannot ever be satisfied: the
    entrypoint prints its closing line AFTER writing the artifacts, that line goes through the same
    ``tee`` that produces the log, so the log's mtime is always newer than the report it announces.
    A predicate that is false by construction is worse than no check — it fails the job while
    naming the wrong cause, which is what sent #181 out as fixed.
    """
    out_dir_file = _module_constant(GPU_SCRIPT, "OUT_DIR_FILE")
    script = _ledger_script()

    assert out_dir_file in script, (
        f"the ledger step does not read {out_dir_file!r}. The example declares its output "
        f"directory there and this step is the only reader; if they disagree the lane records "
        f"nothing and says so in a message about the wrong file."
    )
    assert "-newer" not in script, (
        f"the ledger step is searching for the report by modification time again. The artifacts "
        f"are always OLDER than the tee'd log that announces them, so this can only ever find "
        f"nothing. Read the path out of {out_dir_file!r} instead."
    )


def test_the_ledger_script_extractor_sees_real_shell() -> None:
    """Guard the guard: an extractor that returned "" would make the test above vacuous."""
    script = _ledger_script()
    assert "provael watch --record" in script, (
        "the ledger script extractor is not returning the recording step's shell; every "
        "assertion made against it is passing on an empty string"
    )
    raw = next(
        st["run"]
        for st in yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["gpu-redteam"][
            "steps"
        ]
        if "ledger" in str(st.get("name", "")).lower()
    )
    assert len(raw.splitlines()) > len(script.splitlines()), (
        "no comment lines were stripped, so the assertions above are matching against prose as "
        "well as shell — the exact confusion this extractor exists to remove"
    )
