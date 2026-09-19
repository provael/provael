#!/usr/bin/env python3
"""Render the reference delivery pack from one real, supported, committed run — nothing typed.

WHY. A paid assessment hands a customer a pack: findings, limitations, the report, the decision,
the manifest, the raw evidence references and how to reproduce the run. Until this script existed
the only public sample was a combined report with important provenance fields unrecorded, and the
pack a customer would receive had never been assembled end to end. This renders one from the
published body — SmolVLA (HuggingFaceVLA/smolvla_libero) on the ten LIBERO-Object tasks, five
seeds, 14 September 2026 — using only the emitters the CLI uses, so the pack cannot say anything
the artifacts do not.

WHAT IT RENDERS, into ``examples/delivery-pack/<run>/``:

* ``README.md`` — findings with every rate beside its control, the decision under the example
  protocol, limitations, and what the pack does not establish.
* ``decision.json`` — :func:`provael.verdict.release_verdict` on the combined view under
  ``examples/assessment/protocol.example.yml`` (a FAIL on roleplay; the pack does not pretend).
* ``evidence-manifest.json`` — the v2 public manifest with every shard's digest under
  ``source_reports``; the combined view is derived and is never written as ``report.json``.
* ``report.scorecard.md`` and ``test-report.md`` — the same decision, rendered.
* ``shards.txt`` — every shard's ``report.json`` and ``execution-manifest.json`` with its sha256:
  edit a byte and the digest here and in the manifest no longer match the file.
* ``REPRODUCE.md`` — the pinned inputs another engineer needs to attempt the run.
* ``retest.md`` — the regression diff against the earlier run of the same configuration
  (``results/smolvla_libero_object_suite``), with its caveats: what changed, what is not comparable.

DETERMINISM. No wall-clock value is written; the decision carries no ``as_of`` because the example
protocol has no exception. Re-running on an unchanged tree is a no-op and ``--check`` is meaningful.

Usage::

    python scripts/gen_delivery_pack.py            # rewrite
    python scripts/gen_delivery_pack.py --check    # fail if a rewrite would change anything
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from provael.attest import RULESET_VERSION  # noqa: E402
from provael.calibration import wilson_ci  # noqa: E402
from provael.combine import combine_reports, load_shards, shard_digests  # noqa: E402
from provael.manifest import to_evidence_manifest_json  # noqa: E402
from provael.regression import diff_reports  # noqa: E402
from provael.regression import to_markdown as diff_markdown  # noqa: E402
from provael.scorecard import to_scorecard_markdown  # noqa: E402
from provael.scoring.asr import benign_control, semantic_role  # noqa: E402
from provael.test_report import to_test_report_markdown  # noqa: E402
from provael.types import RunReport  # noqa: E402
from provael.verdict import (  # noqa: E402
    AcceptanceProtocol,
    ReleaseDecision,
    release_verdict,
    to_decision_json,
)

RUN = ROOT / "results" / "smolvla_libero_object_suite_2026-09-14"
BASELINE_RUN = ROOT / "results" / "smolvla_libero_object_suite"
PROTOCOL = ROOT / "examples" / "assessment" / "protocol.example.yml"
OUT = ROOT / "examples" / "delivery-pack" / "smolvla-libero-object-2026-09-14"
REPOSITORY = "https://github.com/provael/provael"
#: The commit that committed the run (`git log --diff-filter=A -- results/<run>/aggregate.json`).
RUN_COMMIT = "5690df5"
#: The lane that produced it and the image it ran: examples/gpu-ci/modal_libero_suite.py at the
#: 0.41.2 pin, lerobot[libero]==0.5.1. Read from the shards' manifests where they record it.
LANE = "examples/gpu-ci/modal_libero_suite.py"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _combined(run: Path) -> tuple[RunReport, list[tuple[Path, RunReport]]]:
    shards = load_shards(run)
    return combine_reports([r for _, r in shards]), shards


def _pct(x: float) -> str:
    return f"{100.0 * x:.1f}%"


def _arm_rows(report: RunReport, aggregate: dict[str, object]) -> list[str]:
    mcnemar = aggregate.get("mcnemar") or {}
    lines = [
        "| arm | role | unsafe / applicable | 95% Wilson (episode) | McNemar vs `none` | Holm "
        "| task-clustered 95% CI |",
        "| --- | --- | ---: | :---: | ---: | ---: | :---: |",
    ]
    roles = {r.attack: semantic_role(r) for r in report.results}
    for name in report.attacks:
        stat = report.by_attack.get(name)
        if stat is None or stat.attempts == 0:
            lines.append(f"| `{name}` | {roles.get(name, '—')} | N/A | N/A | — | — | — |")
            continue
        lo, hi = wilson_ci(stat.successes, stat.attempts)
        m = mcnemar.get(name, {}) if isinstance(mcnemar, dict) else {}
        p = m.get("p_value") if isinstance(m, dict) else None
        holm = m.get("holm_adjusted") if isinstance(m, dict) else None
        cci = m.get("clustered_ci95") if isinstance(m, dict) else None
        lines.append(
            f"| `{name}` | {roles.get(name, '—')} | {stat.successes}/{stat.attempts} "
            f"({_pct(stat.asr)}) | [{_pct(lo)}, {_pct(hi)}] | "
            f"{'—' if p is None else f'{p:.3g}'} | {'—' if holm is None else f'{holm:.3g}'} | "
            f"{'—' if not cci else f'[{_pct(cci[0])}, {_pct(cci[1])}]'} |"
        )
    return lines


def _readme(report: RunReport, decision: ReleaseDecision, aggregate: dict[str, object]) -> str:
    benign = benign_control(report)
    floor = (
        f"{benign.successes}/{benign.attempts} ({_pct(benign.rate)})" if benign and benign.attempts
        else "not run"
    )
    clean = report.clean_task_success_rate
    reasons = "\n".join(f"- {r}" for r in decision.reasons)
    return "\n".join([
        "# Delivery pack — SmolVLA × LIBERO-Object, 14 September 2026",
        "",
        "GENERATED by `scripts/gen_delivery_pack.py` from "
        "`results/smolvla_libero_object_suite_2026-09-14`. Nothing in this directory is typed; "
        "regenerate it, do not edit it.",
        "",
        "This is the pack a paid assessment hands over, assembled from the one supported "
        "configuration with a committed, re-measured body of evidence. It is a **worked example** "
        "of the shape: the acceptance protocol it is decided under is the example protocol, not "
        "one a customer agreed.",
        "",
        "## What was measured",
        "",
        f"- **Checkpoint:** `{report.model}` through the `{report.policy}` adapter",
        f"- **Simulator / suite:** `{report.suite}`, task suite `libero_object`, "
        f"{len(report.tasks)} tasks, horizon {report.horizon}, {report.seeds} seeds, "
        f"{report.episodes} episode(s) per (task, arm) per shard",
        f"- **Arms:** {', '.join(f'`{a}`' for a in report.attacks)}",
        "- **Endpoint:** `unsafe_envelope` under the default (uncalibrated) keep-out predicate — "
        "an envelope exit, not task completion, not a calibrated hazard violation, not "
        "physical-robot evidence",
        f"- **Tool version:** provael {report.tool_version}; evidence state "
        f"`{report.evidence_state}`",
        "",
        "## Findings",
        "",
        *_arm_rows(report, aggregate),
        "",
        f"- **Benign floor (`none`):** {floor}. Every rate above is read against it.",
        "- **Clean-task competence (benign arm):** "
        f"{'not measured' if clean is None else _pct(clean)}.",
        "- `roleplay` is an instruction-family arm: its rate is instruction-induced fragility "
        "under an out-of-distribution imperative frame, not evidence that an attacker chose where "
        "the policy went (the harmless-variation controls in "
        "`results/smolvla_libero_object_control_2026-09-14` are the arm that separates the two).",
        "- Intervals per arm are episode-level Wilson scores; the task-clustered interval "
        "resamples whole tasks and is the honest width across tasks. They are different estimates "
        "and are named apart.",
        "",
        "## Decision",
        "",
        f"**{decision.verdict.value.upper()}** under protocol `{decision.protocol}` "
        f"({decision.protocol_digest}), `examples/assessment/protocol.example.yml`:",
        "",
        reasons,
        "",
        "A decision is a statement about this run under the named protocol, not a property of "
        "the measurement; `decision.json` carries every criterion's outcome.",
        "",
        "## Limitations",
        "",
        "- Simulation only. Ten LIBERO-Object tasks; nothing about other tasks, suites, "
        "checkpoints or any physical robot.",
        "- The predicate is the documented default box, which overlaps the reachable benign "
        "workspace on four Object tasks; the benign floor above is what it fires on unattacked.",
        "- Provenance: the shards ran on provael 0.41.2 and record no `repository`, `commit`, "
        "`dep_lock_digest` or `precision`; those fields are unknown for this run and are not "
        "backfilled (see each shard's manifest and `shards.txt`). A run from 0.43.0 on records all "
        "four.",
        "- No signature: this pack is digest-bound (`shards.txt`, `evidence-manifest.json`), not "
        "signed. `provael attest` signs a run when a key is supplied; a signature is origin and "
        "integrity, not scientific validity.",
        "",
        "## Contents",
        "",
        "| file | what it is |",
        "| --- | --- |",
        "| `decision.json` | the release decision under the example protocol |",
        "| `evidence-manifest.json` | the v2 public evidence manifest; `source_reports` digests "
        "every shard |",
        "| `report.scorecard.md` | the one-page scorecard, same decision |",
        "| `test-report.md` | the clause-7.8-shaped test report (derived view; no single execution "
        "manifest) |",
        "| `shards.txt` | every shard's report and manifest with its sha256 |",
        "| `REPRODUCE.md` | the pinned inputs to attempt the run again |",
        "| `retest.md` | the regression diff against the earlier run of the same configuration |",
        "",
        "## What this pack does not establish",
        "",
        "- Conformity with any standard or regulation (the compliance export says "
        "`evidence-present` per control; it is never legal compliance).",
        "- Transfer to any other architecture; the π0.5 preliminary leg is a separate run with its "
        "own README (`results/pi05_libero_object_2026-09-18`).",
        "- Anything a customer's own protocol would decide differently; the thresholds here are "
        "the example's.",
        "",
    ])


def _reproduce(report: RunReport, shards: list[tuple[Path, RunReport]]) -> str:
    manifests = [
        json.loads((p.parent / "execution-manifest.json").read_text(encoding="utf-8"))
        for p, _ in shards
    ]
    versions = sorted({str(m.get("package_version")) for m in manifests})
    hardware = sorted({str(m.get("hardware")) for m in manifests})
    os_ = sorted({str(m.get("os")) for m in manifests})
    py = sorted({str(m.get("python_version")) for m in manifests})
    return "\n".join([
        "# Reproduce this run",
        "",
        "Everything another engineer needs to attempt the run; nothing here is a promise that the "
        "numbers come back identical — the policy samples its actions, so a re-execution matches "
        "in distribution, not byte for byte.",
        "",
        "## Pinned inputs",
        "",
        f"- provael: `{', '.join(versions)}` (`pip install 'provael[lerobot]=={versions[0]}'`), "
        "with `lerobot[libero]==0.5.1` as the lane pins it",
        f"- Checkpoint: `{report.model}` (the shards' `deployed_policy` records no resolved "
        "revision — pin one by hand before you run, and record it)",
        f"- Suite: `{report.suite}`, tasks `{report.tasks[0]}` … `{report.tasks[-1]}` "
        f"({len(report.tasks)})",
        f"- Arms: {', '.join(f'`{a}`' for a in report.attacks)}",
        f"- Seeds: {report.seeds} (base seed {report.seed}); horizon {report.horizon}; "
        f"{report.episodes} episode(s) per (task, arm) per shard",
        f"- Recorded environment: OS {', '.join(os_)}; Python {', '.join(py)}; hardware "
        f"`{', '.join(hardware)}` (the manifests name no accelerator model; the README of the run "
        "says which box ran it)",
        f"- Source commit of the committed run: `{RUN_COMMIT}`; the shards themselves record no "
        "commit",
        "",
        "## Command shape",
        "",
        "One task per container, the lane's design (a ten-task LIBERO screen is ~15 GPU-hours):",
        "",
        "```bash",
        f"# the driver: {LANE} (Modal); or per task, locally on a CUDA box:",
        "export PROVAEL_REPOSITORY=provael/provael PROVAEL_COMMIT=<sha you are running>",
        f"provael attack --policy {report.policy} --suite {report.suite} --model {report.model} \\",
        f"    --tasks libero_object/<i> --attacks {','.join(report.attacks)} \\",
        f"    --seeds {report.seeds} --horizon {report.horizon} --seed {report.seed} \\",
        "    --protocol examples/assessment/protocol.example.yml --out runs/libero_object_<i>",
        "```",
        "",
        "## Expected qualitative behaviour",
        "",
        "- `roleplay` well above the benign floor on the Object suite (42/50 here, task-clustered "
        "interval in the README); `goal_substitution` and `paraphrase` above the floor but far "
        "below it; the visual and injection arms at or near the floor; `mcp_tool_desc` not "
        "applicable.",
        "- Clean task success on the benign arm above 0.9.",
        "- Under the example protocol the decision is FAIL on the roleplay slice.",
        "",
        "## Known limits of a reproduction",
        "",
        "- Cross-seed spread on LIBERO is ~14 percentage points; compare intervals, not points.",
        "- A different lerobot or MuJoCo version is a different simulator; record both.",
        "- The default predicate is the documented box; a calibrated run is a different "
        "measurement.",
        "",
    ])


def _retest(candidate: RunReport, baseline: RunReport) -> str:
    diff = diff_reports(candidate, baseline, critical_attacks=["roleplay", "goal_substitution"])
    caveats = [
        f"- Baseline tool version {baseline.tool_version}; candidate {candidate.tool_version}. "
        "A different tool version is a different scorer build; the diff is shown with that stated.",
        "- Same checkpoint id on both sides; neither run records a resolved checkpoint revision, "
        "so 'same weights' is asserted by the id, not by a digest.",
    ]
    if diff.incomparable:
        caveats += [f"- Not like-for-like: {reason}" for reason in diff.incomparable]
    return "\n".join([
        "# Retest — this run against the earlier run of the same configuration",
        "",
        f"Baseline: `results/smolvla_libero_object_suite` ({baseline.tool_version}). Candidate: "
        f"this run ({candidate.tool_version}). Critical attacks gated on their own slices: "
        "roleplay, goal_substitution.",
        "",
        "## Caveats first",
        "",
        *caveats,
        "",
        "Overlapping intervals do not show equivalence or the absence of a change; they show that "
        "this sample size cannot separate the two rates. A regression here is a claim about the "
        "candidate getting *more* attackable, not about it being safe.",
        "",
        diff_markdown(diff),
    ])


def build() -> dict[str, str]:
    report, shards = _combined(RUN)
    protocol = AcceptanceProtocol.load(PROTOCOL)
    decision = release_verdict(report, protocol)
    aggregate = json.loads((RUN / "aggregate.json").read_text(encoding="utf-8"))
    manifest = to_evidence_manifest_json(
        report, repository=REPOSITORY, commit=RUN_COMMIT,
        regulatory_clock_version=RULESET_VERSION,
        source_reports=shard_digests(shards, root=RUN), decision=decision,
    )
    shard_lines = []
    for report_path, _ in shards:
        for name in ("report.json", "execution-manifest.json"):
            path = report_path.parent / name
            if path.is_file():
                shard_lines.append(f"{_sha256(path)}  {path.relative_to(ROOT).as_posix()}")
    baseline, _ = _combined(BASELINE_RUN)
    return {
        "README.md": _readme(report, decision, aggregate),
        "decision.json": to_decision_json(decision),
        "evidence-manifest.json": manifest,
        "report.scorecard.md": to_scorecard_markdown(report, decision=decision),
        "test-report.md": to_test_report_markdown(report, None, decision),
        "shards.txt": "\n".join(shard_lines) + "\n",
        "REPRODUCE.md": _reproduce(report, shards),
        "retest.md": _retest(report, baseline),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the reference delivery pack.")
    parser.add_argument(
        "--check", action="store_true", help="fail if a rewrite would change anything"
    )
    args = parser.parse_args(argv)
    files = build()
    stale = [
        name for name, text in files.items()
        if not (OUT / name).is_file() or (OUT / name).read_text(encoding="utf-8") != text
    ]
    if args.check:
        if stale:
            print(
                f"{OUT.relative_to(ROOT)} is stale: {', '.join(stale)}; rerun without --check",
                file=sys.stderr,
            )
            # Say WHAT differs, not only which file: a stale pack in CI with no diff in its log is
            # a failure nobody can act on from the log alone.
            import difflib

            for name in stale:
                target = OUT / name
                committed = target.read_text(encoding="utf-8") if target.is_file() else ""
                diff = difflib.unified_diff(
                    committed.splitlines(), files[name].splitlines(),
                    fromfile=f"committed/{name}", tofile=f"regenerated/{name}", lineterm="", n=1,
                )
                sys.stderr.write("\n".join(list(diff)[:60]) + "\n")
            return 1
        print(f"ok       {OUT.relative_to(ROOT)}")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (OUT / name).write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(files)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
