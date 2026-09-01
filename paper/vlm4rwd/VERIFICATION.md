# Verification report

Every quantitative claim in `paper.tex` was re-derived from committed artifacts rather than
transcribed. This file exists because the verification was originally produced only as working
output, and a verification that cannot be re-read is not an artifact. Re-derive with:

```bash
python studies/keepout_calibration/run.py
python paper/vlm4rwd/make_figure.py     # from the repository root
```

| Claim | Verdict | Source |
| --- | --- | --- |
| 400 records, 350 measured; gap is one arm with `applicable:false` and `steps:0` | CONFIRMED | all ten shards |
| provael 0.32.0, 9 August 2026 | CONFIRMED | `results/smolvla_libero_object_suite/README.md` |
| Arm table: every rate, McNemar p, Holm p, clustered CI | CONFIRMED | re-derived via `paired_by_attack`, `holm_bonferroni`, `cluster_bootstrap_ci` |
| Benign 2/50 (4.0%), Wilson [1.1%, 13.5%] | CONFIRMED | `wilson_ci(2, 50)` |
| Clean task success 84% mean, 40%-100% range | CONFIRMED | per-shard `clean_task_success_rate` |
| **"Zero benign twins fired at a roleplay-success cell"** | **CORRECTED** | **Both** benign firings land on roleplay-success cells (`libero_object/4` seed 2, `libero_object/5` seed 2). This is why McNemar counts **42** discordant pairs, not 44 |
| Keep-out study: 3/50, 2/50, pooled 5/100; per-task 2/10 and 3/10; eight silent | CONFIRMED | `studies/keepout_calibration/run.py` |
| Cross-test p = 0.0080 and p = 0.0400; conservative 0.04 headline | CONFIRMED | same |
| All five firings: `task_success:false`, `steps == steps_to_success`, `danger 0.0`, empty endpoints | CONFIRMED | shard records |
| `DEFAULT_KEEP_OUT_ZONE` x (0.10, 0.40), y (-0.40, -0.10), z (0.0, 0.30) | CONFIRMED | `src/provael/suites/keepout_zones.py:105` |
| `ForbiddenObjectGrasp` inert (empty objects, no extractor) | CONFIRMED | `src/provael/suites/libero.py:89` |
| Single-task run: goal substitution 6/10 fails Holm (0.156); roleplay 10/10; no clustered CI | CONFIRMED | `results/smolvla_libero_object/report.json`, tool version 0.1.0 |
| A zero-width clustered interval published for 21 days; corrected to the 7.1% exact binomial upper bound; leaderboard correct throughout | CONFIRMED | `CHANGELOG.md` `[0.38.1]` |
| `calibrated:false` and `stochastic:true` on every shard; 1/4 then 0/4 pilot | CONFIRMED | both runs |
| Horizon 280 | FOUND | `horizon` field, every shard |
| Ten containers, ~2 h wall clock, 15.4 GPU-hours, ~$12 on an L4 | FOUND | suite README |
| Control run date 9 August 2026 | FOUND | control README |

## Notes

The suite README's phrase "seven measured nulls when there are six" counts measured **arms**, not
nulls. The nulls are three. Wording, not a numeric disagreement.

`PRIOR_ART.md` records ESTI's headline figures as improvements over baselines rather than absolute
rates. Both papers state them that way.
