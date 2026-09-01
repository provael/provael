# Build the submission. Requires tectonic (self-contained TeX) and matplotlib.
#   make          -> figure, paper, anonymity gate
#   make paper    -> compile only
#   make check    -> anonymity gate only
.PHONY: all paper figure check clean

all: check

figure:
	cd ../.. && python paper/vlm4rwd/make_figure.py

paper: figure
	tectonic -X compile paper.tex --keep-logs

check: paper
	./check_anonymity.sh

clean:
	rm -f paper.pdf paper.log benign_firings.pdf
