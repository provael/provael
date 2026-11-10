# Adopted keep-out calibrations

Every `*.json` here is loaded at import by `provael.suites.keepout_zones` and, if it passes the
adoption gate, becomes the keep-out predicate for its task. Dropping a file in is the whole
adoption step — **there is no code change**, which is the point.

## Why this directory exists and `results/calibration/` is not used directly

`results/` is **not packaged**. `pyproject.toml` ships `packages = ["src/provael"]`, so a
`pip install provael` has no `results/` at all. Loading the predicate from there would mean the
boundary every ASR is scored against differs between a source checkout and a wheel — the same
number, measured against two different predicates, depending on how the reader installed the tool.

This repository already learned that in 0.26.0 and wrote it down in `suites/__init__.py`:
`docs/` and `results/` are not packaged, so a filesystem probe "answers differently in a checkout
and in a wheel, and it fails toward *measured*". A calibration is the worst possible place to
repeat it.

So the two directories mean different things, and the difference is the review step:

| | what it holds | packaged |
| --- | --- | --- |
| `results/calibration/` | every fit a run produced, adopted or not | no |
| this directory | the fits that earned adoption | yes |

Promoting a fit is `cp` plus a commit someone reads.

## The adoption gate

A file here is adopted only if it carries `spatial_fit.detection_rate > 0` — evidence the predicate
actually flags an attacked rollout. A fit that meets its benign target and catches nothing is
loaded, reported, and **withheld**, with the reason shown by `provael doctor`.

That gate is not bureaucracy. A hazard box is disjoint from the benign envelope by construction, so
almost any placement scores a benign false-positive rate near zero; on the one task with committed
trajectories, five of the six candidate faces score 0.0 benign **and catch nothing**
(`studies/keepout_face_selection/`). A predicate that cannot fire scores a perfect ASR and means
nothing.

## Current contents: ten fits, all withheld

The ten `libero_object` fits from `results/calibration/` have sat here since #218 (8 September
2026), and the adoption gate withholds every one at import (`WithheldCalibration`): they were
fitted before `spatial_fit` existed, so they carry no adversarial arm at all, and the one that
could be checked against real trajectories flagged 0 of 12 attacked episodes. LIBERO therefore
runs the default, uncalibrated predicate. See issue #136.
