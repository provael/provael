#!/usr/bin/env bash
# Double-blind gate for the workshop submission.
#
# Checks the RENDERED PDF, never the sources. A .tex file can be clean while the PDF carries an
# identifying string in an embedded font name, an XMP packet, or a figure's producer metadata, and
# only the compiled artifact is what a reviewer downloads.
#
# Scans three surfaces, because a hit in any one of them is a desk reject:
#   1. extracted text          (prose, captions, table cells, bibliography)
#   2. document info metadata  (/Author /Title /Subject /Keywords must be empty)
#   3. raw bytes               (XMP packets, embedded file names, object streams)
#
# Exits non-zero on any hit. Run from this directory:  ./check_anonymity.sh
set -uo pipefail

PDF="${1:-paper.pdf}"
fail=0

if [ ! -f "$PDF" ]; then
  echo "  x $PDF not found - compile first"
  exit 1
fi

# Identifying strings. Case-insensitive. Kept explicit rather than clever: a reviewer greps for
# names, and so should this.
TERMS=(provael sattyam jain attri github pypi zenodo orcid sattyamjjain provael.com)

echo "Anonymity check on $PDF"
echo

# -- 1. extracted text -------------------------------------------------------------------------
TXT="$(mktemp)"; trap 'rm -f "$TXT"' EXIT
pdftotext "$PDF" "$TXT" 2>/dev/null || { echo "  x pdftotext failed"; exit 1; }
words=$(wc -w < "$TXT" | tr -d ' ')
if [ "$words" -lt 200 ]; then
  # Vacuity guard: an empty extraction would let every grep below pass by checking nothing.
  echo "  x extracted only $words words - not trusting this run"
  exit 1
fi
echo "  text: $words words extracted"
for t in "${TERMS[@]}"; do
  if grep -qi -- "$t" "$TXT"; then
    echo "  x TEXT contains '$t':"; grep -in -- "$t" "$TXT" | head -3 | sed 's/^/      /'
    fail=1
  fi
done

# -- 1b. the anonymized-repo placeholder ------------------------------------------------------
# This venue permits a link to an anonymized mirror, so the paper carries one. Shipping the
# placeholder text is worse than shipping no link: it tells a reviewer the reproducibility
# statement was written and never read. Checked in the RENDERED text, because \url{} of an
# undefined-looking macro still typesets the literal string.
if grep -q 'ANONYMOUS-REPO-URL-TO-FILL-IN' "$TXT"; then
  echo "  x PLACEHOLDER still present: ANONYMOUS-REPO-URL-TO-FILL-IN"
  echo "      replace \\anonrepo in paper.tex with the real anonymized mirror before upload"
  fail=1
else
  echo "  placeholder: anonymized-repo URL has been filled in"
fi

# -- 2. document info metadata ----------------------------------------------------------------
INFO="$(pdfinfo "$PDF" 2>/dev/null)"
for field in Author Title Subject Keywords; do
  val="$(printf '%s\n' "$INFO" | awk -F: -v f="$field" '$1==f {sub(/^[ \t]+/,"",$2); print $2}')"
  if [ -n "${val// /}" ]; then
    echo "  x METADATA /$field is not empty: '$val'"
    fail=1
  fi
done
[ "$fail" -eq 0 ] && echo "  metadata: /Author /Title /Subject /Keywords all empty"

# -- 3. raw bytes ------------------------------------------------------------------------------
# Catches XMP and embedded paths that pdftotext does not surface.
for t in "${TERMS[@]}"; do
  if LC_ALL=C grep -qai -- "$t" "$PDF"; then
    echo "  x RAW BYTES contain '$t' (XMP packet or embedded path)"
    fail=1
  fi
done
[ "$fail" -eq 0 ] && echo "  raw bytes: no identifying string found"

echo
if [ "$fail" -ne 0 ]; then
  echo "ANONYMITY CHECK FAILED"
  exit 1
fi
echo "ANONYMITY CHECK PASSED"
