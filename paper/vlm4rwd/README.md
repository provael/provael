# Workshop submission

One-line build (needs `tectonic` and `matplotlib`):

```bash
make
```

That regenerates the figure from the committed run artifacts, compiles the paper, and runs the
double-blind gate. Equivalent by hand, from this directory:

```bash
cd ../.. && python paper/vlm4rwd/make_figure.py && cd paper/vlm4rwd
tectonic -X compile paper.tex --keep-logs
./check_anonymity.sh
```

## Files

| File | What it is |
| --- | --- |
| `paper.tex` | the submission |
| `neurips_2026.sty` | official style, unmodified, from the NeurIPS 2026 formatting instructions |
| `make_figure.py` | generates `benign_firings.pdf` by reading the committed reports; hardcodes no counts |
| `check_anonymity.sh` | double-blind gate over the rendered PDF, not the sources |

## Notes

`make_figure.py` must be run from the repository root, because it reads the committed run
directories by relative path. The Makefile does this for you.

`check_anonymity.sh` reads the compiled PDF's extracted text, its document-info metadata and its
raw bytes. It carries a vacuity guard: an extraction under 200 words fails rather than passing,
because an empty extraction would let every grep pass by checking nothing. Running it against a
figure rather than the paper therefore fails by design.

Every quantitative claim in the paper is derived from artifacts committed in this repository. The
figure is generated, not drawn.
