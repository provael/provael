"""Combining shards must recompute, not average — and must refuse shards that aren't one run.

The failure this guards is quiet. Ten shards each carry their own summary fields, and the obvious
implementation averages those: `sum(r.asr for r in reports) / len(reports)`. That is correct only
when every shard has the same denominator, and wrong the moment one task runs fewer episodes than
another — it weights a 5-episode shard equally with a 50-episode one and reports a rate no run
produced. Every derived quantity here is recomputed from the pooled EPISODES instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from provael.combine import (
    INVARIANT_FIELDS,
    ShardMismatchError,
    combine_reports,
    is_sharded,
    load_shards,
    shard_digests,
)
from provael.types import BitFlipRecord, RunReport

SUITE = Path(__file__).resolve().parent.parent / "results" / "smolvla_libero_object_suite"
SINGLE = Path(__file__).resolve().parent.parent / "results" / "smolvla_libero_object"


def _shards() -> list[RunReport]:
    return [r for _, r in load_shards(SUITE)]


def test_the_committed_suite_is_detected_as_sharded() -> None:
    assert is_sharded(SUITE)
    assert len(load_shards(SUITE)) == 10


def test_a_single_run_directory_is_not_sharded() -> None:
    """The older shape must keep working unchanged — it has its own report.json."""
    assert not is_sharded(SINGLE)


def test_combining_reproduces_the_published_numbers() -> None:
    """Pins the figures quoted in the README, the result page and the site manifest."""
    c = combine_reports(_shards())
    assert len(c.tasks) == 10
    assert c.attempts == 350, "350 MEASURED episodes of 400 records; inapplicable ones are excluded"
    assert c.by_attack["roleplay"].successes == 44
    assert c.by_attack["roleplay"].attempts == 50
    assert round(c.by_attack["roleplay"].asr, 4) == 0.88
    assert c.benign_fpr == 0.04, "2 of 50 benign episodes tripped the uncalibrated predicate"
    assert round(c.clean_task_success_rate or 0, 2) == 0.84
    assert c.calibrated is False
    assert c.seeds == 5


def test_rates_are_recomputed_from_episodes_not_averaged_across_shards() -> None:
    """The core correctness property, on shards with deliberately unequal denominators.

    Shard A: 1 success in 1 episode (rate 1.0). Shard B: 0 in 9 (rate 0.0). Averaging the shard
    rates gives 0.5. Pooling the episodes gives 1/10 = 0.1, which is the true rate. A 5x error,
    and nothing about the output would look wrong.
    """
    shards = _shards()
    head = shards[0]

    def synthetic(n_success: int, n_total: int, seed_base: int) -> RunReport:
        rows = []
        for i in range(n_total):
            row = head.results[0].model_copy(
                update={"success": i < n_success, "seed": seed_base + i, "attack": "roleplay"}
            )
            rows.append(row)
        return head.model_copy(update={"results": rows, "tasks": [f"t{seed_base}"]})

    combined = combine_reports([synthetic(1, 1, 0), synthetic(0, 9, 100)])
    assert combined.by_attack["roleplay"].attempts == 10
    assert combined.by_attack["roleplay"].successes == 1
    assert combined.by_attack["roleplay"].asr == pytest.approx(0.1)
    assert combined.by_attack["roleplay"].asr != pytest.approx(0.5), "shard rates were averaged"


@pytest.mark.parametrize("field", INVARIANT_FIELDS)
def test_shards_that_disagree_on_an_invariant_are_refused(field: str) -> None:
    """Different policy, checkpoint, suite or horizon means these are not one experiment.

    Pooling them would produce a rate describing no run that ever happened, so this raises rather
    than returning a plausible number.
    """
    shards = _shards()[:2]
    current = getattr(shards[1], field)
    altered = "DIFFERENT" if isinstance(current, str) else 9999
    with pytest.raises(ShardMismatchError, match=field):
        combine_reports([shards[0], shards[1].model_copy(update={field: altered})])


def test_an_empty_shard_list_is_refused() -> None:
    with pytest.raises(ShardMismatchError):
        combine_reports([])


def test_calibrated_is_true_only_when_every_shard_is() -> None:
    """One uncalibrated task means the pooled predicate is not calibrated. Take the weaker claim."""
    shards = _shards()[:2]
    assert combine_reports([
        shards[0].model_copy(update={"calibrated": True}),
        shards[1].model_copy(update={"calibrated": False}),
    ]).calibrated is False


def test_episodes_is_the_per_cell_count_not_the_sum() -> None:
    """Summing would report ten times the truth: `episodes` is per (task, attack)."""
    shards = _shards()
    assert combine_reports(shards).episodes == shards[0].episodes


def test_every_shard_gets_its_own_digest() -> None:
    """Ten digests, not one. A merged hash would not let a consumer verify a shard independently."""
    shards = load_shards(SUITE)
    digests = shard_digests(shards, root=SUITE)
    assert len(digests) == 10
    assert len({d["sha256"] for d in digests}) == 10, "distinct shards must have distinct digests"
    assert all(d["path"].endswith("/report.json") for d in digests)
    assert all(len(d["sha256"]) == 64 for d in digests)


def test_the_digests_describe_the_artifacts_on_disk() -> None:
    """Provenance must describe the artifacts actually on disk, or it is decoration.

    THIS TEST USED TO BE DECORATION. It computed the expected value with the same
    ``sha256_hex(canonical_json(json.loads(report.model_dump_json())))`` call the implementation
    used, so it asserted that a function does what the function does and could not fail while both
    sides shared a bug. Both sides did: the digest re-serialised each shard through whatever
    ``RunReport`` the running version defines, so it moved on every schema addition. The pinned
    evidence manifest records ``52bcdb70…`` for ``libero_object_0``; 0.34.0 reproduced it and
    0.36.1 returned ``66897a4c…`` for byte-identical committed input.

    It now asserts the property that actually matters and that a shared bug cannot satisfy: the
    digest is a function of the artifact's DECLARED schema, not of the installed version.
    """
    from provael.attest import canonical_json, report_projection, sha256_hex

    digests = {d["path"]: d["sha256"] for d in shard_digests(load_shards(SUITE), root=SUITE)}
    assert digests, "no shards found"

    for path, report in load_shards(SUITE):
        rel = path.relative_to(SUITE).as_posix()

        # 1. It is the projection of the report on disk, not a re-dump of it.
        assert digests[rel] == sha256_hex(canonical_json(report_projection(report)))

        # 2. THE LOAD-BEARING HALF. Populating a field introduced AFTER this shard's declared
        #    schema_version must not move its digest — that is exactly what an older artifact
        #    experiences when a newer tool reads it. Under the old body this assertion fails,
        #    because the dump carried the new field and the bytes changed.
        assert report.schema_version < 4, "fixture assumes a pre-schema-4 shard"
        mutated = report.model_copy(deep=True)
        mutated.results[0].weight_corruption = BitFlipRecord(
            flips=1, selection="gradient", seed=0, parameter_count=8, bit_width=8
        )
        assert (
            sha256_hex(canonical_json(report_projection(mutated))) == digests[rel]
        ), (
            f"{rel}: a field added after schema_version {report.schema_version} changed its "
            "digest — shard provenance must project to the artifact's own declared schema"
        )


def test_no_merged_report_json_is_written_anywhere() -> None:
    """The combined view must stay in memory.

    A file called report.json is treated as attestable across this project — attest signs one, the
    freshness badge dates one, the manifest digests one. A combined view has no single execution
    behind it, so writing one would create a file that looks signable and is not.
    """
    assert not (SUITE / "report.json").exists()
    source = (Path(__file__).resolve().parent.parent / "src" / "provael" / "combine.py").read_text(
        encoding="utf-8"
    )
    assert "write_text" not in source, "combine.py must not serialise anything"
