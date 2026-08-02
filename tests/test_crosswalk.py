"""EAI ↔ RoboJailBench crosswalk: integrity, determinism, and the certify appendix.

The load-bearing guards (what stops the crosswalk silently rotting as families change):
  * every referenced EAI id exists in ``docs/top10.md``;
  * every referenced provael family name exists in the attack registry;
  * the emitted JSON is deterministic across two runs AND across ``PYTHONHASHSEED``;
  * the certify appendix reuses ``provael.scoring.asr`` (it does not reimplement ASR).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

import provael.crosswalk as cw_mod
from provael.attacks.registry import available_families
from provael.certify import CertifyProfile, build_dossier
from provael.cli import app
from provael.config import RunConfig
from provael.crosswalk import (
    EAI_TO_RJB,
    RJB_CATEGORIES,
    Coverage,
    build_appendix,
    coverage_counts,
    head_to_head,
    referenced_eai_ids,
    referenced_families,
    to_crosswalk_json,
    to_crosswalk_markdown,
)
from provael.eai import CATALOG, EaiCoverage
from provael.runner import run

runner = CliRunner()

_TOP10 = Path(__file__).resolve().parent.parent / "docs" / "top10.md"

#: The 18 RoboJailBench categories, verbatim from arXiv 2605.19328v1 Table 2 (do not paraphrase).
_RJB_18_VERBATIM = [
    "Collision with people", "Collision with robots", "Collision with objects",
    "Force/pressure violation", "Unsafe motion", "Entrapment/crushing",
    "Unauthorized capture", "Data misuse", "Unauthorized sharing", "Unauthorized retention",
    "Discrimination", "Deception/manipulation", "Public disruption", "Pornography",
    "Hateful conduct", "Terrorism/weaponization", "Theft", "Trespassing",
]


# --------------------------------------------------------------------------- #
# taxonomy integrity
# --------------------------------------------------------------------------- #


def test_all_18_categories_present_and_verbatim() -> None:
    assert [c.name for c in RJB_CATEGORIES] == _RJB_18_VERBATIM
    assert len({c.id for c in RJB_CATEGORIES}) == 18
    assert len(EAI_TO_RJB) == 10  # one entry per EAI01-EAI10


def test_every_referenced_eai_id_exists_in_top10() -> None:
    top10 = _TOP10.read_text(encoding="utf-8")
    missing = sorted(e for e in referenced_eai_ids() if e not in top10)
    assert not missing, f"EAI ids referenced by the crosswalk but absent from TOP10.md: {missing}"
    # every EAI in the reverse table is a real EAI0x id
    assert {e.id for e in EAI_TO_RJB} == {f"EAI{n:02d}" for n in range(1, 11)}


def test_every_referenced_family_exists_in_the_registry() -> None:
    families = set(available_families())
    missing = sorted(referenced_families() - families)
    assert not missing, f"families referenced by the crosswalk but not registered: {missing}"


def test_reverse_map_targets_are_real_category_ids() -> None:
    ids = {c.id for c in RJB_CATEGORIES}
    for entry in EAI_TO_RJB:
        assert set(entry.robojailbench) <= ids, f"{entry.id} points at an unknown RJB id"


def test_coverage_is_honest_not_all_green() -> None:
    counts = coverage_counts()
    assert sum(counts.values()) == 18
    assert counts[Coverage.covered.value] < 18  # a crosswalk that is 18/18 green is not credible
    # the out-of-scope + not-covered categories are stated, not hidden
    assert counts[Coverage.not_covered.value] > 0
    assert counts[Coverage.out_of_scope.value] > 0


# --------------------------------------------------------------------------- #
# determinism (two runs + PYTHONHASHSEED independence)
# --------------------------------------------------------------------------- #


def test_json_is_deterministic_across_two_runs() -> None:
    assert to_crosswalk_json() == to_crosswalk_json()
    assert to_crosswalk_markdown() == to_crosswalk_markdown()


def test_json_is_deterministic_across_pythonhashseed() -> None:
    code = "from provael.crosswalk import to_crosswalk_json; print(to_crosswalk_json())"

    def _emit(seed: str) -> str:
        out = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        return out.stdout

    assert _emit("0") == _emit("1") == _emit("12345")


def test_json_shape_is_a_valid_crosswalk() -> None:
    doc = json.loads(to_crosswalk_json())
    assert doc["target"] == "robojailbench"
    assert doc["source"]["arxiv"] == "2605.19328" and doc["source"]["arxiv_version"] == "v1"
    assert len(doc["robojailbench_to_eai"]) == 18 and len(doc["eai_to_robojailbench"]) == 10


# --------------------------------------------------------------------------- #
# head-to-head measured coverage (reuses scoring; carries the transfer statement)
# --------------------------------------------------------------------------- #


def test_head_to_head_labels_transfer_for_every_number() -> None:
    rows = head_to_head()
    assert rows, "head-to-head must report the mapped families"
    for row in rows:
        assert row["asr"] is not None and row["n"] > 0 and row["wilson_ci95"]
        assert row["transfer_statement"]  # mandatory, next to the number
    # only instruction is demonstrated on a real policy; the rest say so plainly
    inst = next(r for r in rows if r["family"] == "instruction")
    assert "real policy" in str(inst["transfer_statement"]) and "100%" in str(inst["transfer_statement"])
    for row in rows:
        if row["family"] != "instruction":
            assert "not demonstrated on a real policy" in str(row["transfer_statement"])


def test_head_to_head_reuses_scoring_without_reimplementing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"by_family": 0, "wilson": 0}
    real_by_family = cw_mod.by_family
    real_wilson = cw_mod.wilson_ci

    def wrapped_by_family(*a: object, **k: object) -> object:
        calls["by_family"] += 1
        return real_by_family(*a, **k)  # type: ignore[arg-type]

    def wrapped_wilson(*a: object, **k: object) -> object:
        calls["wilson"] += 1
        return real_wilson(*a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(cw_mod, "by_family", wrapped_by_family)
    monkeypatch.setattr(cw_mod, "wilson_ci", wrapped_wilson)
    head_to_head()
    assert calls["by_family"] > 0 and calls["wilson"] > 0


# --------------------------------------------------------------------------- #
# certify appendix (opt-in; composed, not re-rendered; reuses scoring)
# --------------------------------------------------------------------------- #


def _report():  # noqa: ANN202 - test helper
    return run(RunConfig(policy="stub", suite="stub", attacks=["none", "instruction"], episodes=5))


def test_certify_appendix_is_opt_in() -> None:
    common = {"profile": CertifyProfile.annex_i_part_a, "issued_at": "2026-07-20T00:00:00Z",
              "commit": "x"}
    assert "appendix_taxonomy_crosswalk" not in build_dossier(_report(), **common)
    d = build_dossier(_report(), **common, include_crosswalk=True)
    ap = d["appendix_taxonomy_crosswalk"]
    assert ap["target"] == "robojailbench" and ap["measured_head_to_head"]


def test_certify_appendix_reuses_scoring_without_reimplementing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The appendix's head-to-head must call the shipped scoring, exactly like the dossier itself.
    calls = {"by_family": 0}
    real = cw_mod.by_family

    def wrapped(*a: object, **k: object) -> object:
        calls["by_family"] += 1
        return real(*a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(cw_mod, "by_family", wrapped)
    build_appendix(_report())
    assert calls["by_family"] > 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def test_cli_crosswalk_json_matches_module() -> None:
    result = runner.invoke(app, ["crosswalk", "--target", "robojailbench"])
    assert result.exit_code == 0
    assert json.loads(result.output)["target"] == "robojailbench"


def test_cli_crosswalk_md_and_out(tmp_path: Path) -> None:
    assert runner.invoke(app, ["crosswalk", "--format", "md"]).exit_code == 0
    out = tmp_path / "cw.json"
    assert runner.invoke(app, ["crosswalk", "--out", str(out)]).exit_code == 0
    assert json.loads(out.read_text())["target"] == "robojailbench"


def test_committed_json_matches_current_emit() -> None:
    # The committed artifact must stay byte-identical to the deterministic emit (guards drift).
    committed = Path(__file__).resolve().parent.parent / "results" / "crosswalk" / cw_mod.CROSSWALK_JSON
    assert committed.read_text(encoding="utf-8").rstrip("\n") == to_crosswalk_json()


# --------------------------------------------------------------------------- #
# second target: MITRE ATLAS
# --------------------------------------------------------------------------- #


def test_atlas_crosswalk_covers_all_ten_risks() -> None:
    """The ATLAS target renders every EAI id, not only the ones carrying a technique."""
    payload = json.loads(cw_mod.to_atlas_json())
    assert payload["target"] == cw_mod.ATLAS_TARGET
    ids = [row["id"] for row in payload["eai_to_atlas"]]
    assert ids == sorted(CATALOG)
    assert len(ids) == 10


def test_atlas_rows_carry_coverage_and_never_invent_technique_ids() -> None:
    for row in json.loads(cw_mod.to_atlas_json())["eai_to_atlas"]:
        assert row["coverage"] in {c.value for c in EaiCoverage}
        assert row["coverage_note"], f"{row['id']} carries no coverage note"
        for technique in row["atlas_techniques"]:
            # Descriptive tactic -> technique phrasing only; a fabricated AML.TXXXX id would give
            # the mapping a precision it has not earned.
            assert "→" in technique and "AML.T" not in technique


def test_atlas_mapping_is_derived_from_the_catalog_not_restated() -> None:
    """A change in the catalog must move the ATLAS artifact, or the two can disagree."""
    for row in json.loads(cw_mod.to_atlas_json())["eai_to_atlas"]:
        entry = CATALOG[row["id"]]
        assert row["name"] == entry.name
        assert row["coverage"] == entry.coverage.value
        assert row["atlas_techniques"] == list(entry.atlas_techniques)


def test_atlas_is_deterministic_and_matches_the_committed_artifact() -> None:
    assert cw_mod.to_atlas_json() == cw_mod.to_atlas_json()  # no clock, no random
    committed = Path(__file__).resolve().parent.parent / "results" / "crosswalk" / cw_mod.ATLAS_JSON
    assert committed.read_text(encoding="utf-8").rstrip("\n") == cw_mod.to_atlas_json()


def test_atlas_markdown_names_the_uncovered_risks_and_the_mapping_status() -> None:
    md = cw_mod.to_atlas_markdown()
    assert "EAI07" in md and "EAI10" in md
    assert "no on-point ATLAS technique" in md
    # The mapping is ours, not MITRE's, and the artifact has to say so wherever it is pasted.
    assert "not reviewed or endorsed by MITRE" in md


# --------------------------------------------------------------------------- #
# foresight — the target that carries a published disagreement
# --------------------------------------------------------------------------- #


def _committed_foresight() -> dict:  # noqa: ANN401 - test helper
    p = Path(__file__).resolve().parent.parent / "results" / "crosswalk" / cw_mod.FORESIGHT_JSON
    return json.loads(p.read_text(encoding="utf-8"))


def test_foresight_artifact_carries_the_disagreement_record() -> None:
    """The disagreement is the reason this target exists; an artifact without it is decorative."""
    dis = _committed_foresight()["disagreement"]
    for key in ("their_finding", "our_measurement", "status", "why_unresolved",
                "what_would_resolve_it"):
        assert dis.get(key), f"the committed foresight crosswalk lost `disagreement.{key}`"
    assert "2606.27079" in dis["their_finding"], "the disagreement no longer cites its source"


def test_foresight_emits_cc_and_ret_per_mapped_category() -> None:
    """Their metrics are process-level; a coverage tally alone cannot carry the comparison.

    Asserted on a fresh stub run rather than the committed one **on purpose**: the committed
    real-policy report predates the per-step decision log, so its CC and RET are legitimately
    ``None`` everywhere. Testing field *population* against it would therefore pin the wrong thing —
    it would pass forever while measuring nothing, which is the vacuous-guard failure this repo has
    been bitten by before. A stub run carries decisions, so it can prove the wiring actually works.
    """
    rows = cw_mod.foresight_category_metrics(_report())
    assert rows, "no ForesightSafety category maps onto a provael family any more"
    required = {
        "id", "category", "coverage", "families_mapped", "families_in_this_run",
        "attempts", "successes", "asr", "asr_wilson_ci95",
        "cumulative_cost_unsafe_steps_per_episode",
        "risk_exposure_time_total_unsafe_steps", "risk_exposure_time_episodes_measured",
        "unmeasured_reason",
    }
    for row in rows:
        assert required <= set(row), f"{row['id']} is missing {required - set(row)}"

    exercised = [r for r in rows if r["attempts"]]
    assert exercised, "the stub run exercised no mapped category; the helper's attacks changed"
    assert any(r["cumulative_cost_unsafe_steps_per_episode"] is not None for r in exercised), (
        "no exercised category reported a CC. Either the decision log stopped being written or "
        "the metric stopped being read — both make this crosswalk's whole point unmeasurable."
    )
    assert any(r["risk_exposure_time_total_unsafe_steps"] is not None for r in exercised), (
        "no exercised category reported a RET"
    )


def test_foresight_unexercised_category_is_null_never_zero() -> None:
    """`None` and `0.0` mean opposite things here, and only one of them is a clean bill of health."""
    rows = cw_mod.foresight_category_metrics(_report())
    empty = [r for r in rows if not r["attempts"]]
    assert empty, "the stub run now exercises every mapped category; pick a narrower helper"
    for row in empty:
        for field in ("asr", "cumulative_cost_unsafe_steps_per_episode",
                      "risk_exposure_time_total_unsafe_steps"):
            assert row[field] is None, (
                f"{row['id']}.{field} is {row[field]!r} for a category this run never exercised. "
                f"Unmeasured is None — 0.0 would assert a measurement nobody made."
            )
        assert row["unmeasured_reason"], f"{row['id']} is empty and does not say why"


def test_foresight_is_deterministic_and_matches_the_committed_artifact() -> None:
    """Same input, byte-identical output — and the committed file is that output.

    Unlike the atlas artifact, this one is generated *with* the committed reference run, so the
    fixture is that report rather than nothing. That is the point: the measured columns are what
    make the disagreement inspectable instead of merely stated.
    """
    from provael.types import RunReport

    root = Path(__file__).resolve().parent.parent
    report = RunReport.model_validate_json(
        (root / "results" / "smolvla_libero_object" / "report.json").read_text(encoding="utf-8")
    )
    assert cw_mod.to_foresight_json(report) == cw_mod.to_foresight_json(report)  # no clock/random
    committed = root / "results" / "crosswalk" / cw_mod.FORESIGHT_JSON
    assert committed.read_text(encoding="utf-8").rstrip("\n") == cw_mod.to_foresight_json(report), (
        "results/crosswalk/crosswalk.foresight.json is stale. Regenerate it with:\n"
        "  provael crosswalk --target foresight --in results/smolvla_libero_object "
        "--out results/crosswalk"
    )
