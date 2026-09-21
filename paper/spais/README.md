# SPAIS @ CoRL 2026 — four-page submission (draft 1, 21 September 2026)

Deadline **1 October 2026 AoE** (OpenReview due 2 Oct 11:59 UTC); up to 4 pages excluding references,
double-blind, non-archival, CoRL anonymized template (swap `neurips_2026.sty` for it before upload;
the body does not change). Topic: Evaluation & Red-Teaming; the CFP welcomes rigorous negative
results, replications and open-source tooling.

Draft 1 (21 September 2026) fills the 14 September skeleton from the committed runs under
`results/`; the source directory behind each table is named in a comment at the top of `paper.tex`
(never in the PDF), and nothing is typed from memory. No `\todo{}` remains. It compiles to four
pages including references and passes `check_anonymity.sh`. Still to do before 1 October: swap the
style for the CoRL anonymized template, fold in the calibrated-predicate result if the dawn run lands
in time (it is written as "reported separately"), and a read-through by the author.

Build (needs `tectonic`): `tectonic -X compile paper.tex && ./check_anonymity.sh`
