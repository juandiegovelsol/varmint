#!/bin/bash
# state.sh "<bug numbers to apply, e.g. 01 03 | all | none>" [fixorig] [extra patch files...]
# Resets src/ and irr/ to the base commit, applies the chosen injected bugs (+ the upstream fix), rebuilds.
set -e
cd /app
git checkout -q -- src irr
sel="$1"; shift || true
[ "$sel" = all ] && sel="01 02 03 04"
[ "$sel" = none ] && sel=""
for n in $sel; do git apply /kit/bugs/bug_$n.patch; done
for x in "$@"; do
  case "$x" in
    fixorig) git apply /kit/fix_orig.patch ;;
    *) git apply "$x" ;;
  esac
done
git diff --stat | tail -1
cmake --build /app/build --parallel 16 2>&1 | grep -E "error|warning: |Linking CXX executable" | tail -5
