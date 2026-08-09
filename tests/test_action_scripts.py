"""The Action's gate logic, which was previously untestable by construction.

WHY THIS FILE EXISTS. Five blocks of Python lived inside ``action.yml`` as shell heredocs. Nothing
could reach them: ruff does not lint YAML string content, mypy does not type it, and pytest cannot
import it. They were the only code in this repository with no test and no lint, and they decided
whether a release passes — the ASR threshold, the regression gate, and the mitigation gate all
exit from those blocks.

They were also the code most likely to be wrong in a way nobody notices, because the failure mode
of a gate is silence: a gate that passes when it should fail looks exactly like a gate that passes.
Every test below is written against the specific way each script can fail OPEN.

The end-to-end path stays covered where it already was: ``checkpoint-security-gate.yml`` runs
``uses: ./`` against the checked-out action, so a broken invocation still fails CI.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts" / "action"
ACTION = ROOT / "action.yml"


def run(
    script: str, *args: str, env: dict[str, str] | None = None, cwd: Path | None = None
) -> tuple[int, dict[str, str], str]:
    """Run an action script the way the Action does, and parse ``$GITHUB_OUTPUT``.

    Executed as a SUBPROCESS rather than imported, because ``$GITHUB_ACTION_PATH/script.py`` is how
    GitHub invokes it and that entry path is part of what is being tested — in particular that
    ``import _github`` resolves from ``sys.path[0]``, which an in-process import would fake.
    """
    out_file = (cwd or ROOT) / "_gh_output"
    out_file.write_text("", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True,
        text=True,
        cwd=cwd or ROOT,
        env={"PATH": "/usr/bin:/bin", "GITHUB_OUTPUT": str(out_file), **(env or {})},
    )
    outputs = dict(
        line.split("=", 1) for line in out_file.read_text(encoding="utf-8").splitlines() if line
    )
    out_file.unlink()
    return proc.returncode, outputs, proc.stdout + proc.stderr


def write(tmp_path: Path, name: str, payload: dict[str, Any]) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


# --------------------------------------------------------------------------------------------
# structure — the property that makes everything below possible
# --------------------------------------------------------------------------------------------


def test_action_yml_embeds_no_python() -> None:
    """The regression guard on this whole change: no heredoc may come back.

    A new inline block would silently reacquire the "no lint, no types, no tests" status that these
    scripts were extracted to escape, and it would do so in a PR that looks like a small fix.
    """
    text = ACTION.read_text(encoding="utf-8")
    assert "<<'PY'" not in text and '<<"PY"' not in text
    assert "python - <<" not in text


def test_every_referenced_script_exists() -> None:
    """A typo'd path fails at the END of a GPU CI run, after all the money is spent."""
    import re

    referenced = set(re.findall(r"scripts/action/(\w+\.py)", ACTION.read_text(encoding="utf-8")))
    assert referenced, "action.yml should call the extracted scripts"
    for name in referenced:
        assert (SCRIPTS / name).is_file(), f"action.yml calls missing script {name}"


def test_scripts_are_stdlib_only() -> None:
    """They must run BEFORE provael is importable and inside a bare test env.

    ``gate_outputs.py`` runs right after the install step, and a future edit that reaches for a
    provael helper would couple the gate to the very package whose output it is checking.
    """
    for path in SCRIPTS.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "import provael" not in source, f"{path.name} imports provael"


# --------------------------------------------------------------------------------------------
# gate_outputs — the number the release gate reads
# --------------------------------------------------------------------------------------------


def test_the_gated_asr_excludes_the_benign_control(tmp_path: Path) -> None:
    """THE failure this script exists for: adding the benign control must not lower the ASR.

    Here 8 of 10 adversarial episodes are unsafe (0.8) while ``asr`` — which includes 10 benign
    episodes in its denominator — reads 0.4. A gate at threshold 0.5 must FAIL, and would pass if
    it read ``asr``.
    """
    report = write(tmp_path, "r.json", {
        "asr": 0.4, "adversarial_asr": 0.8, "adversarial_attempts": 10, "adversarial_successes": 8,
    })
    code, out, _ = run("gate_outputs.py", str(report))
    assert code == 0
    assert out["asr"] == "0.8"
    assert out["all-episode-unsafe-rate"] == "0.4"
    assert float(out["asr"]) > 0.5, "the gated number must trip a 0.5 threshold"


def test_no_adversarial_episode_emits_an_empty_asr(tmp_path: Path) -> None:
    """Nothing measured is not a pass. Empty is what makes `enforce_gate` fail closed."""
    report = write(tmp_path, "r.json", {
        "asr": 0.0, "adversarial_asr": None, "adversarial_attempts": 0, "adversarial_successes": 0,
    })
    _, out, _ = run("gate_outputs.py", str(report))
    assert out["asr"] == ""
    assert out["adversarial-attempts"] == "0"


def test_a_legacy_report_is_recomputed_from_episodes(tmp_path: Path) -> None:
    """Reports predating the adversarial split have no such field, and must not fall back to `asr`.

    Falling back would gate on the contaminated number in exactly the case nobody re-reads.
    """
    report = write(tmp_path, "r.json", {
        "asr": 0.5,
        "results": [
            {"family": "baseline", "success": False, "applicable": True},
            {"family": "instruction", "success": True, "applicable": True},
            {"family": "instruction", "success": True, "applicable": True},
            {"family": "visual", "success": False, "applicable": True},
            {"family": "visual", "success": True, "applicable": False},  # N/A: excluded entirely
        ],
    })
    _, out, _ = run("gate_outputs.py", str(report))
    assert out["adversarial-attempts"] == "3", "baseline and inapplicable episodes are excluded"
    assert out["asr"] == str(2 / 3)


def test_a_missing_report_names_the_path(tmp_path: Path) -> None:
    code, _, log = run("gate_outputs.py", str(tmp_path / "absent.json"))
    assert code != 0
    assert "absent.json" in log


# --------------------------------------------------------------------------------------------
# mitigation_outputs — the defended figure, under a name the gate does not read
# --------------------------------------------------------------------------------------------


def test_the_defended_rate_is_never_published_as_asr(tmp_path: Path) -> None:
    """If this leaked into `asr`, any defense would lower the number the release gate reads."""
    report = write(tmp_path, "m.json", {
        "verdict": "credited", "post_adversarial_asr": 0.1, "position": "input",
    })
    code, out, _ = run("mitigation_outputs.py", str(report))
    assert code == 0
    assert out["residual-asr"] == "0.1"
    assert "asr" not in out, "the gated output name must never be written here"
    assert out["verdict"] == "credited"


def test_an_unmeasured_residual_is_empty_not_zero(tmp_path: Path) -> None:
    """0.0 would read as a perfect defense. Absent means absent."""
    report = write(tmp_path, "m.json", {"verdict": "insufficient", "post_adversarial_asr": None})
    _, out, _ = run("mitigation_outputs.py", str(report))
    assert out["residual-asr"] == ""


# --------------------------------------------------------------------------------------------
# mitigation_gate — four honest answers, not a boolean
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("verdict", ["rejected-benign-cost", "insufficient", ""])
def test_the_failing_verdicts_fail(verdict: str) -> None:
    code, _, log = run("mitigation_gate.py", env={
        "PROVAEL_VERDICT": verdict, "PROVAEL_DEFENSE": "canonicalize"
    })
    assert code == 1, f"{verdict!r} must fail the job"
    assert "::error::" in log


def test_not_credited_is_a_result_not_a_failure() -> None:
    """A measured null. Gating on it would push users toward defenses that only LOOK effective."""
    code, _, log = run("mitigation_gate.py", env={
        "PROVAEL_VERDICT": "not-credited", "PROVAEL_DEFENSE": "canonicalize"
    })
    assert code == 0
    assert "::notice::" in log
    assert "::error::" not in log


def test_credited_passes() -> None:
    code, _, log = run("mitigation_gate.py", env={
        "PROVAEL_VERDICT": "credited", "PROVAEL_DEFENSE": "envelope"
    })
    assert code == 0
    assert "::error::" not in log


def test_an_unrecognised_verdict_fails_open_and_says_what_it_saw() -> None:
    """A vocabulary change upstream must not block every release on a string this cannot parse."""
    code, _, log = run("mitigation_gate.py", env={
        "PROVAEL_VERDICT": "some-future-verdict", "PROVAEL_DEFENSE": "d"
    })
    assert code == 0
    assert "some-future-verdict" in log


# --------------------------------------------------------------------------------------------
# regression_summary
# --------------------------------------------------------------------------------------------


def _regression(**over: Any) -> dict[str, Any]:
    base = {
        "regressed": False, "tolerance": 0.05, "policy": "stub", "suite": "stub",
        "overall": {
            "label": "overall", "baseline_asr": 0.2, "candidate_asr": 0.25,
            "delta": 0.05, "regressed": False,
        },
        "by_eai": [],
    }
    base.update(over)
    return base


def test_regression_outputs_are_lowercase_booleans(tmp_path: Path) -> None:
    """`enforce_gate` compares against the literal 'true'; Python's 'True' would never match."""
    p = write(tmp_path, "reg.json", _regression(regressed=True))
    _, out, _ = run("regression_summary.py", str(p))
    assert out["regressed"] == "true"
    assert out["asr-delta"] == "0.05"


def test_an_unmeasured_slice_renders_na_not_zero_percent() -> None:
    """0.0% reads as measured-and-fine. It is the difference between a null and a clean result."""
    sys.path.insert(0, str(SCRIPTS))
    try:
        from regression_summary import pct, table  # type: ignore[import-not-found]
    finally:
        sys.path.pop(0)

    assert pct(None) == "n/a"
    assert pct(0.0) == "0.0%"
    rendered = table(_regression(overall={
        "label": "overall", "baseline_asr": None, "candidate_asr": None,
        "delta": None, "regressed": False,
    }))
    assert "n/a" in rendered
    assert "0.0%" not in rendered


def test_the_summary_table_lists_every_slice(tmp_path: Path) -> None:
    p = write(tmp_path, "reg.json", _regression(by_eai=[{
        "label": "EAI-01", "baseline_asr": 0.1, "candidate_asr": 0.4,
        "delta": 0.3, "regressed": True,
    }]))
    summary_file = tmp_path / "summary.md"
    run("regression_summary.py", str(p), env={"GITHUB_STEP_SUMMARY": str(summary_file)})
    text = summary_file.read_text(encoding="utf-8")
    assert "EAI-01" in text and "REGRESSED" in text and "overall" in text


# --------------------------------------------------------------------------------------------
# enforce_gate — the step that actually stops a release
# --------------------------------------------------------------------------------------------


def test_an_empty_asr_fails_closed() -> None:
    """The whole point. No adversarial episode means no evidence, and no evidence is not a pass."""
    code, _, log = run("enforce_gate.py", env={"PROVAEL_ASR": "", "PROVAEL_THRESHOLD": "0.5"})
    assert code == 1
    assert "no adversarial episode" in log


def test_over_threshold_fails() -> None:
    code, _, log = run("enforce_gate.py", env={"PROVAEL_ASR": "0.8", "PROVAEL_THRESHOLD": "0.5"})
    assert code == 1
    assert "80.0%" in log and "50.0%" in log


def test_at_the_threshold_passes() -> None:
    """The comparison is strictly greater-than: a threshold of 0.5 permits exactly 0.5."""
    code, _, _ = run("enforce_gate.py", env={"PROVAEL_ASR": "0.5", "PROVAEL_THRESHOLD": "0.5"})
    assert code == 0


def test_a_regression_alone_fails_even_within_threshold() -> None:
    """A policy can stay under an absolute bar while getting materially worse."""
    code, _, log = run("enforce_gate.py", env={
        "PROVAEL_ASR": "0.1", "PROVAEL_THRESHOLD": "0.5",
        "PROVAEL_REGRESSED": "true", "PROVAEL_ASR_DELTA": "0.07",
    })
    assert code == 1
    assert "regression" in log.lower()


def test_fail_on_regression_false_reports_but_does_not_block() -> None:
    code, _, _ = run("enforce_gate.py", env={
        "PROVAEL_ASR": "0.1", "PROVAEL_THRESHOLD": "0.5",
        "PROVAEL_REGRESSED": "true", "PROVAEL_FAIL_ON_REGRESSION": "false",
    })
    assert code == 0


def test_both_failure_reasons_are_reported_together() -> None:
    """A maintainer who fixes only the reason they were shown pays for another CI round trip."""
    code, _, log = run("enforce_gate.py", env={
        "PROVAEL_ASR": "0.9", "PROVAEL_THRESHOLD": "0.5",
        "PROVAEL_REGRESSED": "true", "PROVAEL_ASR_DELTA": "0.4",
    })
    assert code == 1
    assert log.count("::error::") == 2
