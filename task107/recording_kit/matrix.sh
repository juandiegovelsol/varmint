#!/bin/bash
# matrix.sh "label|bugs|extra" ... : rebuild each state and run the hidden tests.
#   bugs  = "all" | "none" | "1 3" ... ; extra = fixorig | alt | wrong_radius | wrong_reach | wrong_width
mkdir -p /kit/runs
for spec in "$@"; do
  IFS='|' read -r label bugs extra <<< "$spec"
  if [ "$extra" = fixorig ]; then
    /kit/state.sh "$bugs" fixorig > /kit/runs/$label.build 2>&1
  else
    /kit/state.sh "$bugs" > /kit/runs/$label.build 2>&1
    if [ -n "$extra" ]; then
      python3 /kitsrc/altfix.py "$extra" >> /kit/runs/$label.build 2>&1
      (cd /app/build && ninja DDNet DDNet-Server 2>&1 | grep -E "error|FAILED|Linking") >> /kit/runs/$label.build
    fi
  fi
  { echo "== $label (bugs: $bugs, $extra)"; grep -E "error|FAILED" /kit/runs/$label.build | head -5; /kit/runtests.sh "$label" | grep -E "^FAILED|passed|failed"; } > /kit/runs/$label.txt 2>&1
  cat /kit/runs/$label.txt
done
