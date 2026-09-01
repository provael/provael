# RoboPAD submission

A reframe of the VLM4RWD submission in `../vlm4rwd/`, not a separate result. Same measurement,
same artifacts, same figure; the framing, the title, one new section and the reproducibility
statement differ. The two directories are kept apart so they cannot drift into each other.

```bash
make          # regenerate figure from artifacts, compile, run the anonymity gate
```

## Before uploading

**The anonymized repository URL is a placeholder.** `\anonrepo` in `paper.tex` reads
`ANONYMOUS-REPO-URL-TO-FILL-IN`. Create the mirror at <https://anonymous.4open.science> (it needs
the web UI and a GitHub URL) and replace the macro. `check_anonymity.sh` fails while the
placeholder is present, so `make` will not report success until it is filled in. Submitting with
the placeholder visible would be worse than including no link at all.

## What differs from the VLM4RWD version

| | VLM4RWD | RoboPAD |
| --- | --- | --- |
| Page limit | 8 excluding references | 9 of main content, references unlimited |
| This paper | 6 pages | 7 pages, 6 of main content |
| Anonymized repo link | not permitted | permitted, and used |
| New section | none | `A per-checkpoint protocol` |

Everything else is identical: method, results table, the three subsections on what the control arm
changes, the two self-reported defects, the recommendations and the limitations.
