# SPAIS @ CoRL 2026 — four-page submission (draft 1 on the CoRL template, 21 September 2026)

Deadline **1 October 2026 AoE** (OpenReview due 2 Oct 11:59 UTC); up to 4 pages excluding references,
double-blind, non-archival, on the **CoRL 2026 anonymized template** — `corl_2026.sty` and
`corlabbrvnat.bst` here are the unmodified files from the template zip the CFP links
(spais-ws.org/cfp → "CoRL 2026 (anonymized)", downloaded 21 September 2026). With no package option
the style produces the submission form: line numbers, the "Submitted to the 10th Conference on Robot
Learning (CoRL 2026). Do not distribute." footnote, and the template's own anonymous author block.
Topic: Evaluation & Red-Teaming; the CFP welcomes rigorous negative results, replications and
open-source tooling. OpenReview venue: `robot-learning.org/CoRL/2026/Workshop/SPAIS`; notification
17 October 2026.

Draft 1 (21 September 2026) fills the 14 September skeleton from the committed runs under
`results/`; the source directory behind each table is named in a comment at the top of `paper.tex`
(never in the PDF), and nothing is typed from memory. No `\todo{}` remains. On the CoRL template it
compiles to four pages including references (the body ends on page 4, so the "4 pages excluding
references" rule holds with margin) and passes `check_anonymity.sh` — the style writes a proceedings
`pdfsubject`, an "Anonymous Submission" `pdfauthor` and the `\keywords` line into `pdfkeywords`, and
`paper.tex` clears all four after the style so the gate's empty-metadata rule still holds. Still to
do before 1 October: fold in the calibrated-predicate result if the dawn run lands in time (it is
written as "reported separately"), a read-through by the author, and the OpenReview upload.

Build (needs `tectonic`): `tectonic -X compile paper.tex && ./check_anonymity.sh`
