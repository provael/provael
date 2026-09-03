"""A workflow step containing a pipeline must be able to fail on it.

WHY THIS EXISTS, AND WHY IT IS THE THIRD TIME. Bash takes a pipeline's exit status from the LAST
command, so `cmd | tee out.txt` reports tee's success no matter what `cmd` did. That has now bitten
this repository twice in two different lanes:

* `.github/workflows/gpu-scheduled.yml` spent 22 days green while `modal run` exited on "has no
  functions or local entrypoints" and measured nothing. Fixed there, with the reasoning written
  into the file.
* `.github/workflows/ci.yml` — the pytest gate itself — carried the identical defect from d7bc1e2
  (19 Aug 2026) until #183. `main` reported "success" on 2 September while SIXTEEN tests failed.
  Every green tick on every PR merged in that window was worth exactly nothing, including the ones
  that said so.

The second one is worse than the first because it is the gate the others are read against. A step
that cannot fail is a step that cannot report. Fixing the two occurrences does not stop the third,
so this asserts the property across every workflow instead.

WHAT COUNTS AS PROTECTED. Any of `set -o pipefail` (in any `set` form), `shell: bash` — which
GitHub runs as `bash --noprofile --norc -e -o pipefail {0}` — or an explicit `PIPESTATUS` check,
which `gpu-scheduled.yml` and `synthetic.yml` in the website repo use deliberately so they can tell
exit code 2 from exit code 1.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOWS = sorted((Path(__file__).resolve().parents[1] / ".github" / "workflows").glob("*.yml"))

#: Substrings that make a step's pipeline failures observable.
PROTECTIONS = ("pipefail", "PIPESTATUS")

_SUBST = re.compile(r"\$\([^)]*\)")
_DQUOT = re.compile(r'"[^"]*"')
_SQUOT = re.compile(r"'[^']*'")


def _is_bare_pipeline(line: str) -> bool:
    """True when the line pipes AND that pipeline's status reaches the step.

    Deliberately conservative. A pipe inside `$(...)`, inside a quoted string, inside an
    `if`/`while`/`until` condition, or with a `||` fallback is either consumed by something else or
    already handled, so it is not what this test is about.
    """
    s = line.strip()
    if not s or s.startswith("#"):
        return False
    s = _SUBST.sub(" ", s)
    s = _DQUOT.sub(" ", _SQUOT.sub(" ", s))
    s = s.replace("||", " ")
    if "|" not in s:
        return False
    # A pipe inside a conditional is consumed by the conditional, not by the step.
    return not (re.match(r"^(if|elif|while|until)\b", s) or s.rstrip().endswith("; then"))


def _steps() -> list[tuple[str, str, str]]:
    """(workflow file, step name, run body) for every step that runs a shell script."""
    out: list[tuple[str, str, str]] = []
    for wf in WORKFLOWS:
        doc = yaml.safe_load(wf.read_text(encoding="utf-8")) or {}
        for job in (doc.get("jobs") or {}).values():
            for step in job.get("steps") or []:
                run = step.get("run")
                if not isinstance(run, str):
                    continue
                shell = str(step.get("shell") or "")
                body = run if "bash" not in shell else run + "\n# shell: bash sets -o pipefail\n"
                out.append((wf.name, str(step.get("name") or "<unnamed>"), body))
    return out


def _unprotected() -> list[str]:
    bad = []
    for wf, name, body in _steps():
        if any(p in body for p in PROTECTIONS):
            continue
        if any(_is_bare_pipeline(line) for line in body.splitlines()):
            bad.append(f"{wf} :: {name}")
    return bad


def test_workflows_were_found_at_all() -> None:
    """A guard that scans nothing passes for the wrong reason, which is this file's whole subject."""
    assert len(WORKFLOWS) >= 5, f"only found {len(WORKFLOWS)} workflow(s); the glob has drifted"
    assert _steps(), "no run: steps parsed out of the workflows"


def test_every_piping_step_can_fail_on_the_pipe() -> None:
    unprotected = _unprotected()
    assert not unprotected, (
        "these steps pipe without `set -o pipefail`, `shell: bash` or a PIPESTATUS check, so they "
        f"take the LAST command's exit status and cannot fail on the first: {unprotected}. "
        "That is #183, and gpu-scheduled.yml before it."
    )


def test_the_ci_pytest_gate_specifically_is_protected() -> None:
    """Pinned by name, because this is the one whose greenness everything else is read against."""
    ci = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml").read_text()
    step = ci.split("- name: Test (pytest, CPU only) + coverage", 1)
    assert len(step) == 2, "the pytest step was renamed; update this test in the same commit"
    body = step[1].split("- name:", 1)[0]
    assert "pipefail" in body, "the pytest gate lost its pipefail and can no longer fail"
    assert "| tee" in body, "the tee was removed rather than fixed; the job summary needs the file"


@pytest.mark.parametrize(
    ("line", "flagged"),
    [
        ("uv run pytest -q | tee /tmp/out", True),
        ("modal run x.py | tee report.txt", True),
        ('COV=$(grep -E "^TOTAL" /tmp/out | awk "{print $NF}")', False),
        ('if [ -n "$b" ] && { printf %s "$b" | grep -qF "$2"; }; then', False),
        ("node scripts/check-live.mjs 2>&1 | tee probe.txt", True),
        ("echo 'a | b'", False),
        ("cmd | tee out || true", True),
        ("# uv run pytest | tee out", False),
    ],
)
def test_the_pipeline_detector_can_actually_fail(line: str, flagged: bool) -> None:
    """The detector is the load-bearing part; a false-negative here reinstates the whole defect."""
    assert _is_bare_pipeline(line) is flagged, line
