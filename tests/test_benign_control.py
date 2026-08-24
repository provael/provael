"""The benign control arm is published to the same standard as the ASR it qualifies.

The bug these pin: every exporter in this package emitted the adversarial ASR with a Wilson
interval and a denominator, and emitted the benign floor beside it as a bare percentage. An ASR is
a difference against that floor, so an interval on one term and a point on the other invites a
comparison the data does not support — and 0/5 and 0/500 serialise identically as ``0.0``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from provael.avid import to_avid
from provael.mlbom import to_ml_bom
from provael.oscal import to_oscal_json
from provael.report import benign_control_text, load_report, to_markdown
from provael.sarif import to_sarif
from provael.scorecard import to_scorecard_markdown
from provael.scoring.asr import benign_control
from provael.types import RunReport

#: The published ten-task run. Its benign arm is the 2/50 that issue #136 is about, and its
#: reports are `schema_version 2` — so these also pin that the recomputation works on a legacy
#: report, where the counts predate the stored fields entirely.
SUITE = Path("results/smolvla_libero_object_suite")


def _shards() -> list[RunReport]:
    paths = sorted(SUITE.glob("libero_object_*/report.json"))
    assert paths, "the committed ten-task suite is missing"
    return [load_report(p) for p in paths]


def test_benign_headline_reproduces_the_published_two_of_fifty() -> None:
    succ = att = 0
    for report in _shards():
        _rate, s, n = report.benign_headline()
        succ += s
        att += n
    assert (succ, att) == (2, 50)


def test_benign_and_adversarial_headlines_partition_the_applicable_episodes() -> None:
    """Neither arm may borrow an episode from the other, or double-count one.

    The two headlines are read as numerator and control of the same run. If their denominators
    overlap, the difference between them is not a difference at all.
    """
    for report in _shards():
        _r, _s, adv_n = report.adversarial_headline()
        _r2, _s2, ben_n = report.benign_headline()
        applicable = sum(1 for r in report.results if r.applicable)
        assert adv_n + ben_n == applicable


def test_benign_control_agrees_with_the_stored_rate() -> None:
    for report in _shards():
        control = benign_control(report)
        assert control is not None
        assert report.benign_fpr == pytest.approx(control.rate)


def test_benign_control_carries_an_interval_whenever_it_carries_counts() -> None:
    for report in _shards():
        control = benign_control(report)
        assert control is not None and control.attempts > 0
        assert control.ci95 is not None
        lo, hi = control.ci95
        assert lo <= control.rate <= hi, "the published interval must contain the published rate"


def test_trimmed_report_keeps_the_rate_and_refuses_to_invent_an_interval() -> None:
    """A report whose episodes were dropped keeps ``benign_fpr`` and loses the denominator.

    The wrong answers are both available and both worse than the right one: printing ``0/0``, or
    printing an interval computed from a denominator that is not there.
    """
    report = _shards()[0].model_copy(update={"results": []})
    control = benign_control(report)
    assert control is not None
    assert control.rate == report.benign_fpr
    assert (control.successes, control.attempts) == (0, 0)
    assert control.ci95 is None
    assert "counts not retained" in benign_control_text(report)


def test_no_control_arm_is_not_a_measured_zero() -> None:
    """An unmeasured false-positive floor and a measured floor of zero are different claims."""
    report = _shards()[0].model_copy(update={"results": [], "benign_fpr": None})
    assert benign_control(report) is None
    assert benign_control_text(report) == "n/a (no benign control arm)"


def test_every_exporter_publishes_the_control_arm_with_its_interval() -> None:
    """One assertion per published surface, because each is a separate place to forget.

    A reader of the SARIF run, the ML-BOM, the OSCAL observation, the AVID record, the scorecard
    or the Markdown report must be able to see how thin the floor is without opening the report.
    """
    report = _shards()[4]  # libero_object/4: one of the two tasks the benign arm fires on
    control = benign_control(report)
    assert control is not None and control.ci95 is not None

    sarif = json.loads(to_sarif(report)) if isinstance(to_sarif(report), str) else to_sarif(report)
    props = sarif["runs"][0]["properties"]
    assert props["benignAttempts"] == control.attempts
    assert props["benignSuccesses"] == control.successes
    assert props["benignFprCi95"] == list(control.ci95)

    bom = to_ml_bom(report)
    bom = json.loads(bom) if isinstance(bom, str) else bom
    benign_metrics = [
        m
        for c in bom.get("components", [])
        for m in c.get("modelCard", {}).get("quantitativeAnalysis", {}).get("performanceMetrics", [])
        if m.get("type") == "benign-false-positive-rate"
    ]
    assert benign_metrics, "the ML-BOM dropped the control arm entirely"
    assert "confidenceInterval" in benign_metrics[0]

    oscal = to_oscal_json(report)
    for prop in ("benign-fpr", "benign-n", "benign-ci95-low", "benign-ci95-high"):
        assert f'"name": "{prop}"' in oscal

    avid = to_avid(report)
    avid = json.loads(avid) if isinstance(avid, str) else avid
    results = avid["metrics"][0]["results"]
    assert results["benign_attempts"] == control.attempts
    assert results["benign_ci95"] is not None

    assert "Benign baseline FPR" in to_scorecard_markdown(report)
    markdown = to_markdown(report)
    assert "benign FPR 95% CI (Wilson)" in markdown
    assert f"({control.successes}/{control.attempts})" in markdown
