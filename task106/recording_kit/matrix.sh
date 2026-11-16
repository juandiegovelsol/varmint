#!/bin/bash
# matrix.sh "label|bugs|extra" ...   -> /kit/matrix/<label>.txt
mkdir -p /kit/matrix
for spec in "$@"; do
  IFS='|' read -r label bugs extra <<< "$spec"
  /kit/state.sh "$bugs" $extra > /kit/matrix/$label.build 2>&1
  cd /app && timeout 400 python3 /kit/probe/tests/harvest_c01/run_test.py --junit-out /tmp/j_$label.xml --shots-dir /kit/matrix/shots_$label > /kit/matrix/$label.log 2>&1
  { echo "== $label (bugs: $bugs $extra)"; grep -E "^(PASS|FAIL) |^wrote" /kit/matrix/$label.log; } > /kit/matrix/$label.txt
  cat /kit/matrix/$label.txt
done
