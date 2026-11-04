# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The RFM recording tool: the selection rule as written, the cost cap as promised, the path end to end.

``scripts/rfm/`` records one SmolVLA LIBERO-Object episode for a video and composes the submitted
MP4s. LIBERO does not install here, so the real path cannot run in this suite; what can is held here:
the selection rule against the README that states it, the instructions against the attack template
and the committed 14 September report, the Modal cost ceiling against the $5 budget, the determinism
switches and the identical-actions verdicts, and the whole campaign on the synthetic CPU scene —
episodes, checks and three encoded videos — with every drawn string grepped for the banned words and
the measured report held byte-identical to a run with no recorder at all.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
RFM = ROOT / "scripts" / "rfm"
README = ROOT / "results" / "rfm_submission_2026-11" / "README.md"


def _load(name: str) -> ModuleType:
    if str(RFM) not in sys.path:
        sys.path.insert(0, str(RFM))
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, RFM / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


plan = _load("rfm_plan")
record = _load("rfm_record")

HAS_FFMPEG = shutil.which("ffmpeg") is not None or importlib.util.find_spec("imageio_ffmpeg")
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg with libx264")


# -- the selection rule --------------------------------------------------------------------------


def test_the_rule_submits_seed_zero_when_it_leaves() -> None:
    assert plan.select_seed([(0, True)]) == 0


def test_the_rule_takes_the_first_later_seed_that_leaves_in_order() -> None:
    assert plan.select_seed([(0, False), (1, False), (2, True), (3, True)]) == 2
    assert plan.select_seed([(3, True), (0, False), (1, True)]) == 1  # order is the rule's


def test_the_rule_selects_nothing_when_no_seed_leaves() -> None:
    assert plan.select_seed([(s, False) for s in plan.SELECTION_SEEDS]) is None


def test_the_readme_states_the_rule_the_code_runs() -> None:
    text = README.read_text(encoding="utf-8")
    rule = text.split("## Selection rule", 1)[1].split("\n## ", 1)[0]
    assert text.index("## Selection rule") < text.index("## Setup")  # the rule comes first
    assert plan.SELECTION_SEEDS == (0, 1, 2, 3, 4)
    assert "Seed 0 is submitted." in rule
    assert "seeds 1, 2, 3 and 4 are\n   recorded in that order" in rule
    assert f"`--pin-init-states {plan.PIN_START}`" in rule
    assert "Every seed run is reported" in rule
    assert "**Nothing in this folder is measured yet.**" in text


def test_the_readme_names_the_setup_the_code_runs() -> None:
    text = README.read_text(encoding="utf-8")
    assert plan.CHECKPOINT == "HuggingFaceVLA/smolvla_libero" and f"`{plan.CHECKPOINT}`" in text
    assert plan.TASK == "libero_object/0" and f"`{plan.TASK}`" in text
    assert plan.HORIZON == 280 and "| horizon | 280 steps |" in text
    for instruction in plan.EXPECTED_INSTRUCTIONS.values():
        assert f"`{instruction}`" in text
    for name in plan.VIDEO_NAMES.values():
        assert f"`{name}`" in text


def test_the_expected_roleplay_instruction_is_the_attacks_own_sentence() -> None:
    from provael.attacks.instruction import RolePlayAttack

    produced, _ = RolePlayAttack().perturb("anything", {})
    assert produced == plan.EXPECTED_INSTRUCTIONS["roleplay"]


def test_the_expected_benign_instruction_is_what_libero_gave_on_14_september() -> None:
    clip = json.loads((ROOT / "results" / "smolvla_libero_object_clip_2026-09-14" /
                       "report.json").read_text(encoding="utf-8"))
    benign = next(r for r in clip["results"] if r["attack"] == "none")
    assert benign["task"] == plan.TASK
    assert benign["original_instruction"] == plan.EXPECTED_INSTRUCTIONS["benign"]


# -- the Modal cost cap --------------------------------------------------------------------------


def test_the_modal_ceiling_is_under_the_budget() -> None:
    rate = plan.modal_usd_per_second()
    assert rate == pytest.approx(0.000222 + 4 * 0.0000131 + 16 * 0.00000222)
    ceiling = plan.modal_ceiling_usd()
    assert ceiling == pytest.approx(plan.MODAL_TIMEOUT_S * rate * plan.MODAL_MAX_ATTEMPTS)
    assert ceiling < plan.MODAL_BUDGET_USD == 5.0
    worst = plan.modal_plan_seconds(len(plan.SELECTION_SEEDS))
    assert worst < plan.MODAL_TIMEOUT_S, "the worst-case plan must fit one attempt's timeout"


def test_the_readme_quotes_the_cost_model() -> None:
    text = " ".join(README.read_text(encoding="utf-8").split())
    summary = plan.cost_summary()
    rate = plan.modal_usd_per_second()
    assert f"${rate:.6f} a second" in text and f"${rate * 3600:.2f} an hour" in text
    assert f"${plan.modal_ceiling_usd():.2f}" in text and f"${plan.modal_ceiling_usd():.2f}" in summary
    likely, worst = plan.modal_plan_seconds(1, benign_steps=220), plan.modal_plan_seconds(5)
    assert f"about {likely / 60:.0f} minutes (${likely * rate:.2f})" in text
    assert f"about {worst / 60:.0f} minutes (${worst * rate:.2f})" in text


def _modal_tree() -> ast.Module:
    return ast.parse((RFM / "modal_rfm_record.py").read_text(encoding="utf-8"))


def test_the_modal_script_is_not_a_measurement_lane() -> None:
    """It installs this checkout's source, so it must not sit where the pin guard looks."""
    assert not (ROOT / "examples" / "gpu-ci" / "modal_rfm_record.py").exists()
    source = (RFM / "modal_rfm_record.py").read_text(encoding="utf-8")
    assert "uv_sync(" in source and 'extras=["lerobot"]' in source and "frozen=True" in source
    assert "RFM_ALLOW_DIRTY" in source  # refuses a dirty tree unless told otherwise


def test_the_modal_function_takes_its_limits_from_the_plan() -> None:
    decorator = next(
        d for node in ast.walk(_modal_tree()) if isinstance(node, ast.FunctionDef)
        and node.name == "record" for d in node.decorator_list
    )
    assert isinstance(decorator, ast.Call)
    kwargs = {kw.arg: ast.unparse(kw.value) for kw in decorator.keywords}
    assert kwargs["gpu"] == "plan.MODAL_GPU" and kwargs["timeout"] == "plan.MODAL_TIMEOUT_S"
    assert kwargs["cpu"] == "(plan.MODAL_CPU_REQUEST_CORES, plan.MODAL_CPU_CORES)"
    assert kwargs["memory"] == "(plan.MODAL_MEMORY_REQUEST_MIB, plan.MODAL_MEMORY_MIB)"
    # The bill is computed from the caps, which bound it only while no request exceeds its cap.
    assert 0 < plan.MODAL_CPU_REQUEST_CORES <= plan.MODAL_CPU_CORES
    assert 0 < plan.MODAL_MEMORY_REQUEST_MIB <= plan.MODAL_MEMORY_MIB
    assert plan.MODAL_GPU == "L4"


# -- determinism ---------------------------------------------------------------------------------


def test_without_torch_nothing_is_set_and_the_record_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "torch", None)
    rec = record.apply_determinism(strict=False)
    assert rec["torch"] is None and "no switch was set" in rec["note"]
    assert rec["CUBLAS_WORKSPACE_CONFIG"] == ":4096:8"  # set at import, before any CUDA init
    assert "torch not installed" in record.determinism_deviation(rec)


def test_with_torch_the_switches_are_set_and_read_back(monkeypatch: pytest.MonkeyPatch) -> None:
    state: dict[str, Any] = {"det": False, "warn": False}
    cudnn = SimpleNamespace(deterministic=False, benchmark=True, allow_tf32=True,
                            is_available=lambda: True, version=lambda: 91000)

    def use(flag: bool, warn_only: bool = False) -> None:
        state.update(det=flag, warn=warn_only)

    fake = SimpleNamespace(
        __version__="2.10.0", version=SimpleNamespace(cuda="12.8"),
        backends=SimpleNamespace(cudnn=cudnn, cuda=SimpleNamespace(
            matmul=SimpleNamespace(allow_tf32=False))),
        use_deterministic_algorithms=use,
        are_deterministic_algorithms_enabled=lambda: state["det"],
        is_deterministic_algorithms_warn_only_enabled=lambda: state["warn"],
    )
    monkeypatch.setitem(sys.modules, "torch", fake)
    rec = record.apply_determinism(strict=False)
    assert rec["in_force"] == {
        "cudnn.deterministic": True, "cudnn.benchmark": False,
        "use_deterministic_algorithms": True, "warn_only": True,
        "allow_tf32_matmul": False, "allow_tf32_cudnn": True,
    }
    line = record.determinism_deviation(rec)
    assert "published runs set none" in line and "CUBLAS_WORKSPACE_CONFIG=:4096:8" in line
    assert record.apply_determinism(strict=True)["in_force"]["warn_only"] is False


# -- the identical-actions verdict ---------------------------------------------------------------


def _actions(tmp: Path, name: str, actions: list[list[float]]) -> Path:
    path = tmp / name
    path.mkdir()
    (path / "actions.json").write_text(json.dumps(
        {"steps": list(range(1, len(actions) + 1)), "actions": actions}), encoding="utf-8")
    return path


def test_identical_runs_are_called_identical(tmp_path: Path) -> None:
    acts = [[0.1, 0.2], [0.3, 0.4]]
    verdict = record.check_actions(_actions(tmp_path, "r", acts), _actions(tmp_path, "a", acts),
                                   _actions(tmp_path, "b", acts))
    assert verdict["verdict"].startswith("IDENTICAL") and verdict["recording_identical"]


def test_a_nondeterministic_baseline_is_said_plainly(tmp_path: Path) -> None:
    verdict = record.check_actions(_actions(tmp_path, "r", [[0.1], [0.2]]),
                                   _actions(tmp_path, "a", [[0.1], [0.2]]),
                                   _actions(tmp_path, "b", [[0.1], [0.25]]))
    assert verdict["verdict"].startswith("NOT DETERMINISTIC")
    assert "first differing step 2" in verdict["verdict"]
    assert not verdict["baseline_deterministic"]


def test_a_recording_that_changed_the_actions_is_named(tmp_path: Path) -> None:
    verdict = record.check_actions(_actions(tmp_path, "r", [[0.1], [0.9]]),
                                   _actions(tmp_path, "a", [[0.1], [0.2]]),
                                   _actions(tmp_path, "b", [[0.1], [0.2]]))
    assert verdict["verdict"].startswith("RECORDING CHANGED THE ACTIONS")
    assert verdict["plain_a_vs_recorded"]["first_differing_step"] == 2


# -- helpers -------------------------------------------------------------------------------------


def test_orientation_relations_are_found_exactly() -> None:
    a = np.arange(24, dtype=np.uint8).reshape(2, 4, 3)
    assert record.relation_between(a, a[:, ::-1]) == "mirror_lr"
    assert record.relation_between(a, a[::-1, ::-1]) == "rotate_180"
    assert record.relation_between(a, a + 1) is None


def test_box_edges_are_clipped_to_the_image() -> None:
    from provael.recording import CameraProjection

    cam = CameraProjection("c", 100, 100, (2.0, 0.0, 0.0),
                           ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)), 90.0)
    inside = record.box_segments(cam, (-0.1, 0.1), (-0.1, 0.1), (-0.1, 0.1))
    assert len(inside) == 12
    for (ua, va), (ub, vb) in inside:
        assert all(0 <= c <= 100 for c in (ua, va, ub, vb))
    huge = record.box_segments(cam, (-0.1, 0.1), (-50.0, 50.0), (-0.1, 0.1))
    assert huge and all(0 <= c <= 100 for seg in huge for pt in seg for c in pt)


def test_an_out_directory_with_foreign_files_is_never_cleared(tmp_path: Path) -> None:
    (tmp_path / "report.json").write_text("{}")
    (tmp_path / "precious.txt").write_text("keep me")
    with pytest.raises(SystemExit, match="refusing to clear"):
        record._clear_episode_dir(tmp_path)
    assert (tmp_path / "precious.txt").exists()


def test_the_workstation_lines_survive_the_boxs_paste() -> None:
    """That terminal drops tildes, asterisks and underscores beside punctuation."""
    block = README.read_text(encoding="utf-8").split("### (a) The workstation", 1)[1]
    block = block.split("```", 2)[1]
    for line in [ln for ln in block.splitlines() if ln.strip()]:
        assert "~" not in line and "*" not in line
        assert not re.search(r"_[^A-Za-z0-9]|[^A-Za-z0-9]_", line), line
    script = (RFM / "run_workstation.sh").read_text(encoding="utf-8")
    assert "uvx uv@0.13.6 sync --frozen --extra lerobot" in script
    assert "git status --porcelain --untracked-files=no" in script
    assert "rfm_record.py campaign" in script


# -- the whole path, on the synthetic scene ------------------------------------------------------


@pytest.fixture(scope="module")
def synthetic_campaign(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not HAS_FFMPEG:
        pytest.skip("needs ffmpeg with libx264")
    out = tmp_path_factory.mktemp("rfm") / "campaign"
    assert record.campaign(out, synthetic=True, horizon=60, preset="ultrafast") == 0
    return out


@needs_ffmpeg
def test_the_campaign_writes_three_videos_at_the_sizes_asked_for(synthetic_campaign: Path) -> None:
    compose = json.loads((synthetic_campaign / "compose.json").read_text(encoding="utf-8"))
    expected = {"roleplay": (1080, 1080), "benign": (1080, 1080), "pair": (1920, 1080)}
    seconds = 3 + 60 / 20 + 1 + 4  # title + 60 steps at 20 fps + hold + end card
    for key, (width, height) in expected.items():
        video = compose["videos"][key]
        probe = video["probe"]
        assert (probe["width"], probe["height"]) == (width, height)
        assert (probe["codec"], probe["pix_fmt"]) == ("h264", "yuv420p")
        assert probe["fps"] == pytest.approx(20.0)
        assert probe["duration_s"] == pytest.approx(seconds)
        assert video["bytes"] < 50_000_000 and video["crf"] == 18
    sums = (synthetic_campaign / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    assert sorted(line.split()[1] for line in sums) == sorted(plan.VIDEO_NAMES.values())


@needs_ffmpeg
def test_no_string_drawn_in_any_video_carries_a_banned_word(synthetic_campaign: Path) -> None:
    video = _load("rfm_video")
    drawn = json.loads((synthetic_campaign / "compose.json").read_text())["text_drawn"]
    assert drawn, "the compose report must list what it drew"
    offenders = [s for s in drawn if video.banned_words_in(s)]
    assert offenders == []
    for line in video.END_CARD_LINES:
        assert any(line.startswith(s) or s in line for s in drawn)  # wrapped, but drawn


@needs_ffmpeg
def test_the_recorded_report_is_the_report_of_a_run_with_no_recorder(
    synthetic_campaign: Path,
) -> None:
    import rfm_synthetic

    from provael.config import RunConfig
    from provael.report import to_json
    from provael.runner import run

    episode = synthetic_campaign / "episodes" / "roleplay_seed0"
    recorded = (episode / "report.json").read_text(encoding="utf-8")
    plain = (synthetic_campaign / "checks" / "roleplay_seed0_plain_a" / "report.json").read_text(
        encoding="utf-8")
    config = RunConfig(policy="stub", suite=rfm_synthetic.SUITE_NAME, tasks=[rfm_synthetic.TASK],
                       attacks=["roleplay"], episodes=1, seed=0, horizon=60)
    with rfm_synthetic.installed():
        bare = to_json(run(config))
    assert json.loads(recorded) == json.loads(bare) == json.loads(plain)
    meta = json.loads((episode / "recording.json").read_text(encoding="utf-8"))
    result = json.loads(recorded)["results"][0]
    assert result["steps"] == result["steps_to_success"] == meta["verdict_step"]
    assert meta["recorded_steps"] == 60 and meta["ended_by"] == "horizon"


@needs_ffmpeg
def test_the_campaign_records_its_checks(synthetic_campaign: Path) -> None:
    state = json.loads((synthetic_campaign / "campaign.json").read_text(encoding="utf-8"))
    assert state["selected_seed"] == 0 and state["result"] == "composed"
    assert state["identical_actions"]["verdict"].startswith("IDENTICAL")
    meta = json.loads((synthetic_campaign / "episodes" / "roleplay_seed0" / "recording.json")
                      .read_text(encoding="utf-8"))
    assert meta["replay_fidelity"]["passed"]
    assert meta["policy_input_from_upright"] == "flip_ud"
    assert meta["cameras_rendered"] == ["agentview", "frontview"]
    assert meta["projections"]["agentview"]["check"]["passed"]
    manifest = json.loads((synthetic_campaign / "episodes" / "roleplay_seed0" /
                           "execution-manifest.json").read_text(encoding="utf-8"))
    assert manifest["deviations"][0].startswith("recorded for video")


@needs_ffmpeg
def test_a_second_campaign_resumes_without_rerunning_episodes(
    synthetic_campaign: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(record.subprocess, "run",
                        lambda cmd, **kw: calls.append(cmd))  # would record any re-run
    monkeypatch.setattr(record, "compose", lambda *a, **k: {"videos": {}})
    assert record.campaign(synthetic_campaign, synthetic=True, horizon=60) == 0
    assert calls == []
