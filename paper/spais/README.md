# SPAIS @ CoRL 2026 — four-page submission (skeleton)

Deadline **1 October 2026 AoE** (OpenReview due 2 Oct 11:59 UTC); up to 4 pages excluding references,
double-blind, non-archival, CoRL anonymized template (swap `neurips_2026.sty` for it before upload;
the body does not change). Topic: Evaluation & Red-Teaming; the CFP welcomes rigorous negative
results, replications and open-source tooling.

The skeleton is dated 14 September 2026. Every red `\todo{}` names the committed artifact its number
comes from — the 14–15 September workstation runs under `results/` — and nothing is typed from
memory. `check_anonymity.sh` is the same gate the earlier workshop papers used.

Build (needs `tectonic`): `tectonic -X compile paper.tex && ./check_anonymity.sh`
