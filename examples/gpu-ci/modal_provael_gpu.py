"""The scheduled real-model lane: the next shards of a declared campaign, on Modal L4s.

Provael's core is CPU-tested in CI; the headline credibility move is a cheap, *real-model* job.
Modal (https://modal.com) spins up GPU containers on demand, runs the gated integration path, and
shuts down. `.github/workflows/gpu-scheduled.yml` runs this twice a week.

WHAT THIS LANE IS FOR, AND WHAT IT USED TO BE. Until 18 September 2026 each run was a probe: one
task, eight arms, two seeds, sixteen episodes. It kept `watch/freshness.json` fed and it could never
move `watch/publish-freshness.json`. The published measurement is the largest body of real runs at
one lineage (policy, suite, task suite) and version that nothing supersedes
(:func:`provael.watch.displacement`) — 550 attempts over ten tasks at 0.32.0 — and the probe
added fourteen attempts on ONE task per run, under a version bucket that reset every time a release
re-pinned it. Twice a week for ever would have reached nothing, and the header of its own workflow
priced that at a seventh of the credit.

So each run now measures the next shards of a **declared campaign**: `studies/scheduled_campaign/
plan.json` names the checkpoint, the suite, the ten tasks, the arms and the seed count, modelled on
the published campaign's own shape so the two are comparable and sized so the completed campaign
exceeds its attempts (the 0.41.2 Object body of 14 September 2026, 656 attempts, since the evening
of 18 September; the plan's note is its amendment record). A shard is one (task, seed) cell with
every arm — small enough to fit one
L4 hour with margin — and :mod:`provael.campaign` decides which shards come next from what is
already committed under `results/gpu-scheduled/campaign-<PROVAEL_PIN>/`. The committed tree is the
ledger: a missed run costs a week and not correctness, a re-run of a slot that already landed
selects the shards after it, and nothing is measured twice.

ONE RELEASE PER CAMPAIGN. `PROVAEL_PIN` is held for the whole campaign (see the constant), because
:mod:`provael.combine` refuses to pool shards across tool versions and a campaign that could not be
combined could not be published. `tests/test_gpu_image_pin.py` allows the pin to lag while the
campaign is accumulating, and requires every lane to pin the same version.

PROVENANCE, AND WHY THE FIRST SHARDS AT 0.41.2 WILL BE REFUSED. Every manifest this lane ever
committed reported `repository`, `commit`, `dep_lock_digest` and `precision` as missing. The
driver passed `PROVAEL_COMMIT` correctly from 14 September; the container installed the released
0.41.2 wheel, which reads no such variable — the fix lived in `main` and the lane runs releases.
`provael attack` now fills all four (the driver states the repository and the commit, the run
digests its own dependency set, the adapter reports its precision), the workflow refuses to record
a shard that lacks any of them, and both take effect only once `PROVAEL_PIN` names a release that
carries them. Until that release ships and the pin moves, this lane runs and records nothing, and
says so. That is the honest state, not a bug to route around.

WHAT IT COSTS, DERIVED RATHER THAN QUOTED. The anchors are measured: the 0.32.0 suite ran 400
episodes in 15.4 L4-hours across ten 40-episode containers, this lane's probe ran 16 episodes in
~37 min — both ~139 s/episode including container setup, which the suite's `timing` stage put at
~174 s. The functions below turn those into an expected and a ceiling cost per run and per month
for the plan's shard shape, and `tests/test_gpu_scheduled_plan.py` holds the ceiling under the
credit. `scripts/gpu_arm_plan.py` prices the manual arms the same way from the same rate.

WHAT THIS CANNOT DO, STATED HERE SO NOBODY READS THE LANE AS A FIX FOR IT. Eighty shards at five a
run is sixteen runs, eight weeks. Between v0.32.0 (8 August 2026) and v0.41.2 (9 September 2026)
this project shipped nine minor releases in thirty-two days. At that cadence the body that
displaces the published measurement lands a dozen or more minors behind the current release on the
day it completes — past the two-release window it is measured against. The lane makes the published
measurement MOVE, repeatedly, and `watch/campaign.json` publishes how far along it is; it cannot
make it current. What would: a slower release cadence while a campaign runs, or a larger credit.
Neither is a code change, and neither is claimed here.

    pip install modal && pip install -e .    # the driver reads the plan through provael.campaign
    modal run examples/gpu-ci/modal_provael_gpu.py

WHY THE APP IS BUILT AT GLOBAL SCOPE. It used to be constructed inside `build_app()` so the module
would import without modal installed. That is exactly what broke it: `modal run` scans a module's
GLOBAL scope for an app and its entrypoint, so with everything local to a function it found none
and reported "has no functions or local entrypoints" — for 22 days, while the scheduled workflow
reported success. `modal_libero_suite.py` records the same trap at its own line 83. Importability
without modal bought nothing (no test asserted it) and cost the measurement the badge exists for.

WHY NOTHING FROM `provael` IS IMPORTED AT MODULE SCOPE. The container re-imports this file to run
:func:`redteam`, and the container's provael is the PINNED WHEEL, not this checkout: a module-level
import of something the wheel lacks (or of the plan file, which is not mounted) would fail every
shard at start. The plan is read inside the local entrypoint only, and the container is told what
to run as plain arguments.
"""

from __future__ import annotations

import pathlib
import subprocess

import modal

#: Where the artifacts land on the runner, as ONE fact — one sub-directory per shard, named by the
#: shard id the plan assigns, so the workflow can copy the whole tree into the campaign directory.
#: It used to be the same string typed twice, once for `--out` and once for the mirror path, and
#: the workflow knew neither, so it went looking for `report.json` by modification time instead.
OUT_DIR = "runs/smolvla_libero"

#: The local entrypoint writes :data:`OUT_DIR` here, last, after the artifacts are on disk. The
#: workflow READS this file; it does not search.
#:
#: WHY THE SEARCH COULD NOT WORK. `gpu-scheduled.yml` ran
#: `find . -name report.json -newer gpu-scheduled-report.txt`, and that predicate is unsatisfiable
#: by construction: the entrypoint prints its closing line AFTER writing the artifacts, that line
#: goes through the same `tee` that produces the log, so the log's mtime is always newer than the
#: report it is announcing. On 4 September 2026 — the first scheduled run after #181's fix landed —
#: this lane reached a real policy, printed `Adversarial ASR: 33.3% (4/12)`, wrote three artifacts,
#: and the ledger step reported that it had produced none. Fourth time this lane has been unable to
#: report, after the nested app, the missing `pipefail`, and the discarded return value.
#:
#: The name is mirrored in `.github/workflows/gpu-scheduled.yml` and pinned by
#: `tests/test_modal_examples_are_runnable.py`, the same way every other cross-file contract in
#: this repo is held: copied deliberately, then guarded against drifting.
OUT_DIR_FILE = "gpu-scheduled-outdir.txt"

#: Shards that raised, one per line, written beside :data:`OUT_DIR_FILE` so the workflow can keep
#: the shards that succeeded AND fail the job. Absent when every shard returned.
FAILED_SHARDS_FILE = "gpu-scheduled-failed-shards.txt"

#: The repository whose release the container runs, stated by the driver because a wheel
#: installed from PyPI has no remote to read. Lands in the execution manifest's `repository`.
REPOSITORY = "provael/provael"

#: The exact provael release every container installs.
#:
#: THIS IS A CAMPAIGN PIN, AND IT IS ALLOWED TO LAG. `tests/test_gpu_image_pin.py` used to require
#: it to equal `provael.__version__`, which is the right rule for a probe and the wrong rule for a
#: campaign: bumping it on every release reset the body this lane was building, so the lane could
#: accumulate toward nothing. The test now allows the pin to be the current version, OR the version
#: of the re-measurement in progress (the `challenger` in `watch/publish-freshness.json`), OR the
#: published measurement's version while it is still inside the release window. Every lane must
#: still pin the same version as every other — two lanes on different builds is the incident the
#: test was written for — and a pin that names none of the three fails, with the reason.
#:
#: So: do NOT bump this in a release PR while `publish-freshness.json` shows a challenger at this
#: version. Bump it when the body here has become the published measurement and a newer release
#: exists, and the test will say so in those words. The campaign directory is named for this value.
#:
#: THIS LANE WAS GENUINELY UNPINNED before 0.41.2, which is a different bug with a different
#: consequence. It installed `provael[lerobot]` with no constraint, so the probe measured whatever
#: PyPI served on the morning it ran — not reproducible in either direction, and it silently split
#: the two GPU lanes five releases apart while both looked healthy.
#:
#: NO RELEASE BEFORE 0.42.0 CAN RECORD FROM THIS LANE. The four provenance fields the Record step
#: requires (`repository`, `commit`, `dep_lock_digest`, `precision`) reached the wheel in 0.42.0;
#: on 0.41.2 every shard would have been refused. Bumped in the 0.42.0 release PR because the body
#: at 0.41.2 is the published measurement (the workstation's 14 September runs) and that was the
#: newer release — exactly the case the paragraph above allows — and moved with the 0.42.1 patch
#: the next day, before any shard had run at 0.42.0, so the campaign directory names the release
#: the containers actually install.
PROVAEL_PIN = "0.42.1"
PROVAEL = f"provael[lerobot]=={PROVAEL_PIN}"

# --------------------------------------------------------------------------- #
# cost, derived from measured anchors
# --------------------------------------------------------------------------- #

#: Modal's published L4 rate — the same figure `scripts/gpu_arm_plan.py` names, and a test holds
#: the two equal.
L4_USD_PER_HOUR = 0.7992
#: Marginal seconds per episode once a container is up: (15.4 h x 3600 - 10 x 174 s) / 400.
EPISODE_SECONDS = 134
#: Container start to first step, measured by the suite's `timing` stage.
SETUP_SECONDS = 174
#: The per-container kill switch, and therefore the real cost ceiling: a hung container bills until
#: it fires regardless of what it was asked to do. Forty-five minutes holds a twelve-episode shard
#: (~30 min expected; ~42 min if every episode runs the full horizon) inside one L4 hour with
#: margin, which is the order the campaign was sized to.
SHARD_TIMEOUT_SECONDS = 2700
#: Tuesday and Friday: 104.3 runs a year, 8.69 a month.
RUNS_PER_MONTH = 104.3 / 12
#: The credit this lane shares with the manual arms in `gpu-arm.yml`.
MONTHLY_CREDIT_USD = 30.0


def shard_seconds(arms: int) -> int:
    """Expected wall clock for one shard of ``arms`` episodes, setup included."""
    return SETUP_SECONDS + arms * EPISODE_SECONDS


def expected_usd_per_run(arms: int, shards_per_run: int) -> float:
    return shards_per_run * shard_seconds(arms) / 3600 * L4_USD_PER_HOUR


def ceiling_usd_per_run(shards_per_run: int) -> float:
    return shards_per_run * SHARD_TIMEOUT_SECONDS / 3600 * L4_USD_PER_HOUR


def cost_table(arms: int, shards_per_run: int) -> str:
    """The lane's cost, derived, in the shape the workflow log prints before spending."""
    expected = expected_usd_per_run(arms, shards_per_run)
    ceiling = ceiling_usd_per_run(shards_per_run)
    return "\n".join(
        [
            f"shards per run    {shards_per_run} (one container each, {arms} episodes per shard)",
            f"expected per run  ${expected:.2f} "
            f"({shards_per_run} x {shard_seconds(arms)} s x ${L4_USD_PER_HOUR}/L4-hour)",
            f"ceiling per run   ${ceiling:.2f} "
            f"({shards_per_run} x {SHARD_TIMEOUT_SECONDS} s timeout)",
            f"expected / month  ${expected * RUNS_PER_MONTH:.2f} at {RUNS_PER_MONTH:.2f} runs",
            f"ceiling / month   ${ceiling * RUNS_PER_MONTH:.2f} "
            f"of a ${MONTHLY_CREDIT_USD:.0f} credit",
        ]
    )


def _pin_commit() -> str | None:
    """Commit of the tag the container installs from PyPI, resolved on the driver machine.

    The container has no git checkout (it pip-installs the pinned release), so without this the
    execution manifest records `commit: null`. Resolved from `v{PROVAEL_PIN}` — the code that
    actually runs — never from the driver's HEAD, which may be a different commit. None when the
    driver's checkout has no tags; the manifest then records the gap rather than a guess, and the
    workflow's provenance gate refuses the shard.
    """
    try:
        out = subprocess.run(  # noqa: S603,S607 - fixed argv, no user input
            ["git", "rev-parse", "--verify", "--short", f"v{PROVAEL_PIN}^{{commit}}"],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = out.stdout.strip()
    return sha if out.returncode == 0 and sha else None


PIN_COMMIT = _pin_commit()


image = (
    modal.Image.debian_slim(python_version="3.12")
    # cmake/build-essential/git are load-bearing: lerobot[libero] pulls `egl_probe` and
    # `hf-egl-probe`, which build native wheels and fail with "CMake must be installed."
    # modal_libero_suite.py already carries this list; this file did not, and the failure was
    # invisible while the step could not fail.
    .apt_install(
        "libegl1-mesa-dev", "libgl1-mesa-glx", "libosmesa6-dev", "git", "cmake",
        "build-essential", "libglib2.0-0", "libsm6", "libxrender1", "libfontconfig1",
    )
    .pip_install(PROVAEL, "lerobot[libero]==0.5.1")
    .env({
        "MUJOCO_GL": "egl",
        "PYOPENGL_PLATFORM": "egl",
        "PROVAEL_INTEGRATION": "1",
        # Provenance for execution-manifest.json: the repository and the pinned release's commit
        # (see _pin_commit). Read by provael releases that carry the fields; ignored by older ones,
        # whose shards the workflow's provenance gate then refuses.
        "PROVAEL_REPOSITORY": REPOSITORY,
        **({"PROVAEL_COMMIT": PIN_COMMIT} if PIN_COMMIT else {}),
    })
)
app = modal.App("provael-gpu-ci", image=image)


@app.function(gpu="L4", timeout=SHARD_TIMEOUT_SECONDS)
def redteam(
    shard: str, task: str, seed: int, model: str, attacks: str, horizon: int
) -> tuple[str, dict[str, str]]:
    """Measure ONE shard — every arm on one task at one seed — and return stdout AND the artifacts.

    Everything it needs arrives as arguments from the driver, which read the plan; the container
    holds only the pinned wheel (see the module docstring on imports).

    RETURNING THE ARTIFACTS IS THE WHOLE POINT, not a convenience. This used to return stdout
    alone, so `report.json` was written inside the container and died with it. The workflow's
    ledger step looks for that file ON THE RUNNER, found nothing, emitted a warning and exited 0 —
    so every run from 30 Aug to 3 Sep 2026 reached a real policy, printed a real ASR, and recorded
    nothing while `watch/freshness.json` sat at 2026-08-09 and provael.com served STALE MEASUREMENT
    off the back of it. A lane that measures and discards is indistinguishable from a lane that
    never ran. See #181.
    """
    out = pathlib.Path(OUT_DIR) / shard
    cmd = [
        "provael", "attack", "--policy", "smolvla", "--suite", "libero",
        "--model", model, "--tasks", task, "--attacks", attacks, "--seeds", "1",
        "--horizon", str(horizon), "--seed", str(seed), "--out", str(out),
    ]
    done = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if done.returncode != 0:
        # The reason travels back in the exception, not only the exit code: the driver lists
        # failed shards by this message, and "exit 1" would send someone to Modal's logs for it.
        tail = "\n".join(done.stderr.strip().splitlines()[-12:])
        raise RuntimeError(f"provael attack exited {done.returncode} on shard {shard}:\n{tail}")

    files = {
        str(path.relative_to(out)): path.read_text(encoding="utf-8")
        for path in sorted(out.rglob("*"))
        if path.is_file() and path.suffix in {".json", ".md"}
    }
    if not any(name.endswith("report.json") for name in files):
        raise RuntimeError(
            f"shard {shard} produced no report.json under {out} — refusing to return a success "
            f"that records nothing. Files seen: {sorted(files) or 'none'}"
        )
    return done.stdout, files


@app.local_entrypoint()
def main() -> None:
    """Select the next shards from the committed tree, run them, WRITE the artifacts, declare where.

    WRITING THE ARTIFACTS IS NOT ENOUGH, which is the lesson of the 4 September 2026 run. It wrote
    all three of them and the ledger step still recorded nothing, because the workflow was
    searching for `report.json` by modification time rather than being told the path. Announcing
    the location is therefore part of producing the measurement, not a courtesy: see
    :data:`OUT_DIR_FILE`.

    A shard that raises does not take the others with it. The shards that returned are written and
    declared, the ones that did not are listed in :data:`FAILED_SHARDS_FILE`, and the workflow
    keeps the former and fails on the latter — losing four good shards to one bad one would be the
    sixth version of the "measured and discarded" bug, and a green job with a missing shard would
    be the first version of a new one.
    """
    # Lazy on purpose: the driver runs this checkout's provael; the container must not.
    from provael.attacks.registry import resolve_attacks
    from provael.campaign import campaign_dir, done_shards, load_plan, next_shards, shards

    plan = load_plan()
    directory = campaign_dir(PROVAEL_PIN)
    done = done_shards(plan, directory)
    todo = next_shards(plan, directory)
    total = len(shards(plan))
    arms = len(resolve_attacks(list(plan.attacks)))
    print(
        f"[plan] {plan.id} at provael {PROVAEL_PIN}: {len(done)} of {total} shard(s) committed "
        f"under {directory}, {len(todo)} to run now"
    )
    if not todo:
        print("[plan] the campaign is complete at this pin; nothing to measure. Advance the pin.")
        return
    print(f"[plan] this run: {', '.join(s.id for s in todo)}")
    print(cost_table(arms, len(todo)))

    out = pathlib.Path(OUT_DIR)
    written = 0
    failed: list[str] = []
    args = [(s.id, s.task, s.seed, plan.model, plan.attacks_arg, plan.horizon) for s in todo]
    for shard, result in zip(todo, redteam.starmap(args, return_exceptions=True), strict=True):
        if isinstance(result, BaseException):
            failed.append(f"{shard.id}: {type(result).__name__}: {result}")
            continue
        stdout, files = result
        print(stdout)
        for rel, text in files.items():
            dest = out / shard.id / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text, encoding="utf-8")
        written += 1

    if failed:
        pathlib.Path(FAILED_SHARDS_FILE).write_text("\n".join(failed) + "\n", encoding="utf-8")
        print(f"[run] {len(failed)} shard(s) FAILED — listed in {FAILED_SHARDS_FILE}:")
        for line in failed:
            print(f"  {line}")
    if written == 0:
        raise SystemExit("every shard failed; nothing to declare, nothing to record")

    # LAST, and only once the artifacts are on disk: the file existing is the claim that they are
    # there, and its contents are where. A failed run leaves no file, so the ledger step fails
    # loudly instead of recording a measurement that was never produced.
    pathlib.Path(OUT_DIR_FILE).write_text(f"{OUT_DIR}\n", encoding="utf-8")
    print(
        f"wrote {written} shard(s) to {out}/ — path declared in {OUT_DIR_FILE}; "
        f"{len(done) + written} of {total} shards banked once this run is committed"
    )
