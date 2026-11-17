#!/bin/bash
# runtests.sh LABEL [pytest -k expr] : run the hidden hook-line tests against the current /app build
# (copies the test file from /kitsrc/tests into /app/scripts first). Output: /kit/runs/LABEL.log
mkdir -p /kit/runs
pkill -x Xvfb 2>/dev/null; pkill -x DDNet 2>/dev/null; pkill -x DDNet-Server 2>/dev/null
cp /kitsrc/tests/test_harvest_c01_hookline.py /app/scripts/
cd /app
K=()
[ -n "$2" ] && K=(-k "$2")
HOME=/root DDNET_BUILD_DIR=/app/build timeout 1800 python3 -m pytest -p no:cacheprovider -q -rA \
  --junitxml=/kit/runs/$1.xml "${K[@]}" scripts/test_harvest_c01_hookline.py > /kit/runs/$1.log 2>&1
grep -E "^(PASSED|FAILED|ERROR) |passed|failed" /kit/runs/$1.log | cut -c1-240
