"""The scheduled campaign: a declared grid, measured one shard per run slot, at one held release.

WHY A CAMPAIGN AND NOT A PROBE. Until 18 September 2026 the scheduled GPU lane measured one task,
eight arms, two seeds — sixteen episodes twice a week. It kept the age badge fed and it could not
move the published measurement: :func:`provael.watch.displacement` publishes the largest body of
real runs at one policy, suite and version that nothing supersedes, and that body is 550 attempts
over ten tasks at v0.32.0. The probe added fourteen attempts on one task per run, under a version
that changed every time a release re-pinned it. At that rate it would not have displaced the
published campaign this decade, and its own workflow header said it was spending a seventh of the
credit to do so.

So the lane now measures a **plan** (``studies/scheduled_campaign/plan.json``): the checkpoint, the
suite, the ten tasks, the arms and the seed count, declared before the first shard ran and modelled
on the 0.32.0 campaign's own shape so the two are comparable. The plan splits into **shards** — one
(task, seed) cell each, every arm, so a shard fits one Modal L4 hour with margin — and each
scheduled run measures the next few shards the committed tree does not yet hold. The tree IS the
ledger: a missed run costs a week and not correctness, and re-running a shard that already landed
selects the next one instead of writing a duplicate row.

ONE VERSION PER CAMPAIGN, held. :func:`provael.combine.combine_reports` refuses shards whose
``tool_version`` differs, because a rate over two builds describes a run that never happened. The
lane therefore pins one release for the whole campaign (``tests/test_gpu_image_pin.py`` allows the
pin to lag while a campaign is accumulating at it) and the campaign directory is named for that
version: ``results/gpu-scheduled/campaign-<version>/<shard>/``.

THE COMBINED ARTIFACT, AND THE RULE FOR IT. After each shard lands, :func:`write_campaign` combines
every shard of the campaign into ``campaign.json`` beside them, through the same combiner
``provael evidence-manifest`` uses, carrying :func:`provael.combine.shard_digests` so the artifact
names exactly which runs it rests on. Three things it is not, deliberately:

* **It is not ``report.json``.** Everywhere in this project a file by that name is an attestable
  artifact with one execution behind it; a combined view has none. The shards are the attestable
  artifacts and stay in their own directories with their own manifests.
* **It is not a ledger row.** :func:`provael.watch.measurements_from_results` reads execution
  manifests, and the campaign directory root carries none, so the artifact can never be counted
  beside the shards it summarises. The rows are the shards — exactly how the 0.32.0 campaign is
  recorded today, as twenty of them — and the body arithmetic sums those. Nothing in
  :mod:`provael.watch` reads this file, which is what "do not special-case the lane" means.
* **It is written continuously and says so.** While shards are missing it carries
  ``complete: false``, ``designation: "campaign-in-progress"`` and forces the combined report's
  ``preliminary`` flag on; only a campaign with every planned shard present is
  ``"campaign-complete"``. A partial campaign is a partial campaign in its own words, and a reader
  or a site that re-pins to it can refuse on a field rather than on prose.

And it is only written at all when every shard carries complete provenance
(:func:`provenance_gaps`): repository, commit, dependency-lock digest and precision. A shard that
cannot say what code and what package set produced it is not promoted into a published number.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, Field

from provael.combine import combine_reports, load_shards, shard_digests
from provael.watch import EXECUTION_MANIFEST, REPORT, RESULTS_DIR

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The declared grid. Committed under studies/ because it is a protocol fixed before the run, and
#: the commit that added it is the pre-registration date a reader can check.
PLAN_PATH = REPO_ROOT / "studies" / "scheduled_campaign" / "plan.json"

#: Where campaigns land, under the lane's results tree, one directory per pinned version.
CAMPAIGNS_SUBDIR = "gpu-scheduled"
CAMPAIGN_PREFIX = "campaign-"

#: The combined artifact's file name. Never ``report.json`` — see the module docstring.
CAMPAIGN_JSON = "campaign.json"

#: Provenance a shard must carry before it is recorded or combined. These are the four the
#: scheduled lane's manifests reported as missing on every run it ever made (execution-manifest
#: `missing_fields`), and the four `provael attack` now fills: the driver states the repository and
#: the release's commit, the run digests its own dependency set, the adapter reports its precision.
REQUIRED_PROVENANCE: tuple[str, ...] = ("repository", "commit", "dep_lock_digest", "precision")

DESIGNATION_IN_PROGRESS = "campaign-in-progress"
DESIGNATION_COMPLETE = "campaign-complete"


class ModelledOn(BaseModel):
    """The committed campaign this plan is shaped after, so a test can hold the shape to it."""

    tool_version: str = Field(alias="toolVersion")
    artifact_paths: list[str] = Field(alias="artifactPaths")

    model_config = {"populate_by_name": True}


class CampaignPlan(BaseModel):
    """The declared grid: what one complete campaign measures. Every field is a declared fact."""

    id: str
    policy: str
    model: str
    suite: str
    tasks: list[str]
    #: Attack names or family names, exactly as `provael attack --attacks` takes them.
    attacks: list[str]
    seeds: int
    horizon: int
    shards_per_run: int = Field(alias="shardsPerRun")
    modelled_on: ModelledOn = Field(alias="modelledOn")

    model_config = {"populate_by_name": True, "extra": "ignore"}

    @property
    def attacks_arg(self) -> str:
        return ",".join(self.attacks)


class Shard(BaseModel):
    """One (task, seed) cell of the plan: every arm, one seed, one task, one container."""

    id: str
    task: str
    seed: int


def load_plan(path: Path = PLAN_PATH) -> CampaignPlan:
    return CampaignPlan.model_validate(json.loads(path.read_text(encoding="utf-8")))


def shard_id(task: str, seed: int) -> str:
    """``libero_object/3`` at seed 2 -> ``libero_object_3__seed2``: a directory name and a key."""
    return f"{task.replace('/', '_')}__seed{seed}"


def shards(plan: CampaignPlan) -> list[Shard]:
    """Every shard of the plan, SEED-MAJOR.

    Seed-major so a partial campaign is always "the first k seeds over every task" — the shape
    :func:`provael.combine.combine_reports` pools and an evidence manifest is built over — rather
    than some tasks at many seeds and others at none.
    """
    return [
        Shard(id=shard_id(task, seed), task=task, seed=seed)
        for seed in range(plan.seeds)
        for task in plan.tasks
    ]


def campaign_dir(version: str, results_dir: Path = RESULTS_DIR) -> Path:
    """``results/gpu-scheduled/campaign-<version>`` — one campaign per pinned release."""
    return results_dir / CAMPAIGNS_SUBDIR / f"{CAMPAIGN_PREFIX}{version}"


def done_shards(plan: CampaignPlan, directory: Path) -> list[Shard]:
    """The plan's shards whose ``report.json`` is on disk under ``directory``."""
    return [s for s in shards(plan) if (directory / s.id / REPORT).is_file()]


def next_shards(plan: CampaignPlan, directory: Path, count: int | None = None) -> list[Shard]:
    """The next un-run shards in plan order — what one scheduled run measures.

    Pure in the committed tree: the same directory always yields the same answer, so a re-run of a
    slot that already landed selects the shards after it rather than measuring the same cells twice.
    Empty when the campaign is complete.
    """
    want = plan.shards_per_run if count is None else count
    done = {s.id for s in done_shards(plan, directory)}
    return [s for s in shards(plan) if s.id not in done][:want]


def provenance_gaps(manifest: dict[str, object]) -> list[str]:
    """Which of :data:`REQUIRED_PROVENANCE` a manifest lacks — by value, not only by its own list.

    Both are checked. ``missing_fields`` is what the run itself admitted; the values are what a
    hand-edited or truncated manifest would actually carry. A field is a gap if either says so.
    """
    admitted = manifest.get("missing_fields")
    admitted_set = {str(x) for x in admitted} if isinstance(admitted, list) else set()
    gaps = []
    for field in REQUIRED_PROVENANCE:
        value = manifest.get(field)
        if field in admitted_set or value is None or (isinstance(value, str) and not value.strip()):
            gaps.append(field)
    return gaps


def shard_manifest(shard_dir: Path) -> dict[str, object]:
    loaded = json.loads((shard_dir / EXECUTION_MANIFEST).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{shard_dir / EXECUTION_MANIFEST} is not a JSON object")
    return loaded


class IncompleteProvenanceError(ValueError):
    """A shard lacks provenance the campaign requires; it must not be recorded or combined."""


def check_provenance(shard_dirs: list[Path]) -> dict[str, list[str]]:
    """Gaps per shard directory, keyed by path. Empty when every shard is complete."""
    problems: dict[str, list[str]] = {}
    for shard_dir in shard_dirs:
        manifest_path = shard_dir / EXECUTION_MANIFEST
        if not manifest_path.is_file():
            problems[str(shard_dir)] = ["execution-manifest.json (absent)"]
            continue
        gaps = provenance_gaps(shard_manifest(shard_dir))
        if gaps:
            problems[str(shard_dir)] = gaps
    return problems


def combine_campaign(plan: CampaignPlan, directory: Path) -> dict[str, object] | None:
    """The ``campaign.json`` content for ``directory``, or None when no shard has landed yet.

    Raises :class:`IncompleteProvenanceError` if any shard lacks required provenance — the
    campaign is not written around it, because item by item this artifact is what gets promoted.
    Raises :class:`provael.combine.ShardMismatchError` through the combiner if the shards disagree
    on an invariant (a shard at another version cannot be in this directory by construction, but
    the combiner checks rather than trusts).
    """
    loaded = load_shards(directory)
    if not loaded:
        return None
    problems = check_provenance([path.parent for path, _ in loaded])
    if problems:
        detail = "; ".join(f"{path}: {', '.join(gaps)}" for path, gaps in sorted(problems.items()))
        raise IncompleteProvenanceError(
            f"refusing to combine {directory}: shards with incomplete provenance — {detail}"
        )
    planned = {s.id for s in shards(plan)}
    present = {path.parent.name for path, _ in loaded}
    unplanned = sorted(present - planned)
    if unplanned:
        raise ValueError(
            f"{directory} holds shards the plan does not name: {unplanned}. A campaign is the "
            "plan and nothing else; move them out or change the plan first."
        )
    missing = [s.id for s in shards(plan) if s.id not in present]
    complete = not missing
    report = combine_reports([r for _, r in loaded])
    if not complete:
        # The combiner marks a report preliminary below five seeds; a partial campaign is
        # preliminary whatever its seed count, so the flag is forced rather than inherited.
        report = report.model_copy(update={"preliminary": True})
    ended = [
        str(shard_manifest(path.parent).get("ended_at") or "") for path, _ in loaded
    ]
    return {
        "$schema": "provael-campaign/1",
        "note": (
            "GENERATED by scripts/combine_campaign.py from the shards beside this file. Do not "
            "hand-edit. A combined view over every committed shard of one campaign, through "
            "provael.combine.combine_reports — the same combiner `provael evidence-manifest` "
            "uses — with every shard's schema-aware digest, so a consumer can re-fetch and verify "
            "each one. NOT report.json (a combined view has no single execution behind it) and NOT "
            "a ledger row (this directory carries no execution manifest, so provael.watch never "
            "counts it beside the shards it summarises). `complete` is whether every shard the "
            "plan names is present; until it is, `designation` says in-progress and the report's "
            "`preliminary` flag is forced on. Written only when every shard carries the four "
            "required provenance fields. No wall-clock field: `lastShardEndedAt` is a fact about "
            "the newest shard, not about when this file was written."
        ),
        "plan": {
            "id": plan.id,
            "policy": plan.policy,
            "model": plan.model,
            "suite": plan.suite,
            "tasks": list(plan.tasks),
            "attacks": list(plan.attacks),
            "seeds": plan.seeds,
            "horizon": plan.horizon,
        },
        "toolVersion": report.tool_version,
        "designation": DESIGNATION_COMPLETE if complete else DESIGNATION_IN_PROGRESS,
        "complete": complete,
        "shardsTotal": len(planned),
        "shardsDone": len(present),
        "shardsMissing": missing,
        "lastShardEndedAt": max(ended) if any(ended) else None,
        "shards": shard_digests(loaded, root=directory),
        "report": json.loads(report.model_dump_json()),
    }


def render_campaign(content: dict[str, object]) -> str:
    return json.dumps(content, indent=1, sort_keys=True) + "\n"


def write_campaign(plan: CampaignPlan, directory: Path) -> Path | None:
    """Write (or rewrite) ``campaign.json`` for ``directory``; None when nothing has landed."""
    content = combine_campaign(plan, directory)
    if content is None:
        return None
    out = directory / CAMPAIGN_JSON
    out.write_text(render_campaign(content), encoding="utf-8")
    return out


def campaign_dirs(results_dir: Path = RESULTS_DIR) -> list[Path]:
    """Every ``campaign-*`` directory under the lane's results tree, sorted."""
    root = results_dir / CAMPAIGNS_SUBDIR
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith(CAMPAIGN_PREFIX))


# --------------------------------------------------------------------------- #
# progress: the campaign's state as a derivable artifact
# --------------------------------------------------------------------------- #


def runs_per_week(cron: str) -> int:
    """How many days a week a five-field cron fires, from its day-of-week field.

    Only the shapes this repo writes: ``*``, a list (``2,5``), a range (``1-5``), or a mix. A
    step (``*/2``) is not parsed and raises, so an unfamiliar schedule fails loudly rather than
    projecting a completion date from a guess.
    """
    fields = cron.split()
    if len(fields) != 5:
        raise ValueError(f"not a five-field cron expression: {cron!r}")
    dow = fields[4]
    if dow == "*":
        return 7
    days: set[int] = set()
    for part in dow.split(","):
        if "/" in part:
            raise ValueError(f"cron step syntax is not supported here: {cron!r}")
        if "-" in part:
            lo, hi = (int(x) for x in part.split("-", 1))
            days.update(range(lo, hi + 1))
        else:
            days.add(int(part))
    return len(days)


def progress(
    plan: CampaignPlan,
    version: str,
    *,
    cron: str,
    attempts_to_displace: int | None,
    published_with: str | None,
    results_dir: Path = RESULTS_DIR,
) -> dict[str, object]:
    """The re-measurement's state, as the fields a page can render instead of a flat STALE.

    Every value derives from the plan, the committed shards and the workflow's schedule.
    ``projectedCompletion`` is dated from the NEWEST SHARD's ``ended_at`` plus the runs still
    needed at the committed cadence — a fact about the run, not about when this was rendered — and
    is null until the first shard lands, because before that the only anchor would be the clock.
    """
    directory = campaign_dir(version, results_dir)
    all_shards = shards(plan)
    done = done_shards(plan, directory)
    banked = 0
    ended: list[str] = []
    for shard in done:
        report = json.loads((directory / shard.id / REPORT).read_text(encoding="utf-8"))
        banked += int(report.get("attempts", 0))
        manifest_path = directory / shard.id / EXECUTION_MANIFEST
        if manifest_path.is_file():
            value = json.loads(manifest_path.read_text(encoding="utf-8")).get("ended_at")
            if isinstance(value, str) and value:
                ended.append(value)
    remaining = len(all_shards) - len(done)
    per_week = runs_per_week(cron)
    runs_remaining = math.ceil(remaining / plan.shards_per_run) if remaining else 0
    last_ended = max(ended) if ended else None
    completion: str | None = None
    if last_ended is not None and runs_remaining:
        anchor = datetime.fromisoformat(last_ended.replace("Z", "+00:00"))
        completion = (anchor + timedelta(days=runs_remaining * 7 / per_week)).date().isoformat()
    elif last_ended is not None and not remaining:
        completion = datetime.fromisoformat(last_ended.replace("Z", "+00:00")).date().isoformat()
    return {
        "plan": {
            "id": plan.id,
            "policy": plan.policy,
            "model": plan.model,
            "suite": plan.suite,
            "tasks": len(plan.tasks),
            "attacks": list(plan.attacks),
            "seeds": plan.seeds,
            "horizon": plan.horizon,
            "shardsTotal": len(all_shards),
        },
        "toolVersion": version,
        "target": {
            "attemptsToDisplace": attempts_to_displace,
            "publishedWith": published_with,
        },
        "banked": {
            "attempts": banked,
            "shardsDone": len(done),
            "shardsRemaining": remaining,
            "lastShardEndedAt": last_ended,
        },
        "cadence": {
            "cron": cron,
            "runsPerWeek": per_week,
            "shardsPerRun": plan.shards_per_run,
        },
        "projected": {
            "runsRemaining": runs_remaining,
            "completion": completion,
        },
        "complete": remaining == 0 and bool(done),
    }


__all__ = [
    "CAMPAIGN_JSON",
    "PLAN_PATH",
    "REQUIRED_PROVENANCE",
    "CampaignPlan",
    "IncompleteProvenanceError",
    "Shard",
    "campaign_dir",
    "campaign_dirs",
    "check_provenance",
    "combine_campaign",
    "done_shards",
    "load_plan",
    "next_shards",
    "progress",
    "provenance_gaps",
    "render_campaign",
    "runs_per_week",
    "shard_id",
    "shards",
    "write_campaign",
]
