#!/bin/bash
cd /app
for n in 01 02 03 04 05; do
  git checkout -q src/ && git apply /tmp/orig_fix.patch && python3 /tmp/mkbugs.py /app /tmp/x $n
  echo "== bug $n alone on oracle"; bash /usr/local/bin/rbrun "RockBehaviour.*" 400 | grep -E "^\[  FAILED  \] Rock" | sort -u
done
git checkout -q src/
