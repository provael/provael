# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The workflow lint stays wired in, and no ``run:`` block expands text an outsider writes.

WHY. CVE-2026-137964 (ToolJet, GHSA-74h3-686h-cmvf, critical, NVD 27 November 2026): a release
workflow expanded a pull request's title inside a ``run:`` step, and the title ran as shell. A
``${{ }}`` expansion is pasted into the script before the shell parses it, so no quoting helps; the
fix is an ``env:`` entry and ``"$VAR"`` in the script. No workflow here did this when the zizmor job
landed (28 November 2026), and nothing kept it that way: ``test_workflow_permissions.py``,
``test_workflow_pins.py`` and ``test_workflow_pipefail.py`` read token scopes, pins and pipefail,
never what a script expands.

TWO GUARDS. ``ci.yml``'s ``zizmor`` job runs zizmor at a pinned version and fails on template
injection at every severity. This file checks that the job is still there and still pinned, and it
holds the event fields GitHub documents as attacker-controlled out of every ``run:`` block itself,
so the class stays guarded on a machine without zizmor and if the job is ever dropped. It reads the
composite ``action.yml`` as well: its steps run in every adopter's workflow, where ``github.event``
is the adopter's event.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
ACTION = ROOT / "action.yml"
CI = ROOT / ".github" / "workflows" / "ci.yml"

#: The fields GitHub lists as untrusted input ("Script injections", docs.github.com), plus
#: ``github.head_ref``, which is the same text as ``github.event.pull_request.head.ref``. A SHA, a
#: number or a repository name is not here: an outsider cannot put shell syntax in those.
UNTRUSTED = re.compile(
    r"\bgithub\s*\.\s*(?:head_ref\b|event\s*\.\s*(?:"
    r"(?:issue|pull_request|discussion)\.(?:title|body)\b"
    r"|pull_request\.head\.(?:ref|label|repo\.default_branch)\b"
    r"|(?:comment|review|review_comment)\.body\b"
    r"|pages(?:\.\*|\[\d+\])?\.page_name\b"
    r"|(?:commits(?:\.\*|\[\d+\])?|head_commit)\.(?:message|author\.(?:email|name))\b"
    r"|workflow_run\.(?:head_branch|head_commit\.(?:message|author\.(?:email|name)))\b"
    r"))"
)
#: One ``${{ ... }}`` expansion. The field may sit anywhere inside it, e.g. ``format('{0}', ...)``.
EXPANSION = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)
ZIZMOR = re.compile(r"\buvx\s+zizmor==(\d+\.\d+\.\d+)\b")


def _load(path: Path) -> dict[str, Any]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(doc, dict), f"{path.name} did not parse to a mapping"
    return doc


def _run_blocks(doc: dict[str, Any]) -> list[tuple[str, str]]:
    """(step label, script) for every ``run:`` in a workflow's jobs or a composite action."""
    if "jobs" in doc:
        steps = [s for job in doc["jobs"].values() for s in job.get("steps") or []]
    else:
        steps = list((doc.get("runs") or {}).get("steps") or [])
    return [
        (str(s.get("name") or s.get("id") or "<unnamed>"), s["run"])
        for s in steps
        if isinstance(s.get("run"), str)
    ]


def untrusted_expansions(script: str) -> list[str]:
    """Every ``${{ ... }}`` in ``script`` that reads a field an outsider can write."""
    return [m.group(0) for m in EXPANSION.finditer(script) if UNTRUSTED.search(m.group(1))]


@pytest.mark.parametrize("path", [*WORKFLOWS, ACTION], ids=lambda p: p.name)
def test_no_run_block_expands_untrusted_text(path: Path) -> None:
    found = [
        f"{label}: {hit}"
        for label, script in _run_blocks(_load(path))
        for hit in untrusted_expansions(script)
    ]
    assert not found, (
        f"{path.name} pastes attacker-writable text into a shell script: {found}. Move each value "
        "into the step's `env:` and read it as \"$VAR\" (CVE-2026-137964 is this, in a release "
        "workflow)"
    )


def test_the_run_block_walk_is_not_vacuous() -> None:
    """A walker that found no scripts would pass the test above for the wrong reason."""
    blocks = [b for path in [*WORKFLOWS, ACTION] for b in _run_blocks(_load(path))]
    assert len(blocks) >= 60, f"found only {len(blocks)} run: blocks; did the files move?"
    assert _run_blocks(_load(ACTION)), "action.yml yielded no run: steps; is it still composite?"


def _zizmor_job() -> dict[str, Any]:
    jobs = _load(CI)["jobs"]
    assert "zizmor" in jobs, (
        "ci.yml lost its `zizmor` job, the workflow lint that fails on template injection"
    )
    job = jobs["zizmor"]
    assert isinstance(job, dict)
    return job


def _zizmor_commands(job: dict[str, Any]) -> list[str]:
    scripts = [s["run"] for s in job.get("steps") or [] if isinstance(s.get("run"), str)]
    return [script for script in scripts if ZIZMOR.search(script)]


def test_ci_runs_zizmor_at_one_pinned_version() -> None:
    commands = _zizmor_commands(_zizmor_job())
    assert len(commands) == 2, f"expected the two zizmor runs, found {len(commands)}"
    versions = {v for c in commands for v in ZIZMOR.findall(c)}
    assert len(versions) == 1, f"the two zizmor runs name different versions: {sorted(versions)}"
    for command in commands:
        assert "--offline" in command, f"a zizmor run went online: {command!r}"
        assert ".github/workflows" in command, f"a zizmor run lost its input: {command!r}"


def test_ci_fails_on_medium_findings_and_on_template_injection_at_any_severity() -> None:
    first, second = _zizmor_commands(_zizmor_job())
    assert "--min-severity medium" in first, "the general run no longer fails at medium"
    assert "--format github" in first, "the general run no longer annotates the diff"
    # zizmor rates an expansion it cannot prove safe as informational; `low` would skip it.
    assert "--min-severity informational" in second
    assert '.ident == "template-injection"' in second
    assert "--no-exit-codes" in second, "without it a finding exits before jq can name it"
    assert "test ! -s" in second, "the template-injection run reports but cannot fail"


def test_the_zizmor_job_is_read_only() -> None:
    job = _zizmor_job()
    assert job.get("permissions") == {"contents": "read"}, job.get("permissions")
    checkout = next(
        s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout@")
    )
    assert checkout.get("with", {}).get("persist-credentials") is False


@pytest.mark.parametrize(
    ("script", "flagged"),
    [
        ('echo "${{ github.event.pull_request.title }}"', True),
        ("title=${{github.event.issue.body}}", True),
        ("git switch ${{ github.head_ref }}", True),
        ("echo ${{ format('{0}', github.event.pull_request.head.ref) }}", True),
        ('msg="${{ github.event.head_commit.message }}"', True),
        ("echo ${{ github.event.commits[0].author.name }}", True),
        ("echo ${{ github.event.comment.body }}", True),
        ("echo ${{ github.event.workflow_run.head_branch }}", True),
        # Safe: a SHA, a number, a step output, and the env-var form of the fix itself.
        ("${{ github.event.pull_request.base.sha }}..${{ github.event.pull_request.head.sha }}", False),
        ("echo ${{ github.event.pull_request.number }}", False),
        ("echo ${{ steps.ver.outputs.version }}", False),
        ('echo "$PR_TITLE"', False),
        ("# github.event.pull_request.title outside an expansion is only text", False),
    ],
)
def test_the_detector_reads_each_form(script: str, flagged: bool) -> None:
    """The regex is the load-bearing part; a false negative here reopens the whole class."""
    assert bool(untrusted_expansions(script)) is flagged, script
