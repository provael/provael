# RoboPAD submission

A reframe of the VLM4RWD submission in `../vlm4rwd/`, not a separate result. Same measurement,
same artifacts, same figure; the framing, the title, one new section and the reproducibility
statement differ. The two directories are kept apart so they cannot drift into each other.

```bash
make          # regenerate figure from artifacts, compile, run the anonymity gate
```

## The anonymized repository link

This venue permits linking an anonymized mirror, and the paper does **not** carry one. Creating it
needs the web UI at <https://anonymous.4open.science> plus a GitHub URL, so it cannot be produced
from the build. The reproducibility statement says the repository is withheld for anonymous review,
which is accurate and identifies nobody.

If you make the mirror, add it back in one line in the Reproducibility paragraph of `paper.tex` and
rebuild. `check_anonymity.sh` retains the gate that fails on an unfilled
`ANONYMOUS-REPO-URL-TO-FILL-IN`, so a half-finished edit cannot ship.

## What differs from the VLM4RWD version

| | VLM4RWD | RoboPAD |
| --- | --- | --- |
| Page limit | 8 excluding references | 9 of main content, references unlimited |
| This paper | 6 pages | 7 pages, 6 of main content |
| Anonymized repo link | not permitted | permitted, not used (mirror needs a web UI) |
| New section | none | `A per-checkpoint protocol` |

Everything else is identical: method, results table, the three subsections on what the control arm
changes, the two self-reported defects, the recommendations and the limitations.
