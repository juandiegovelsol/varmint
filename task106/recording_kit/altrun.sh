#!/bin/bash
# altrun.sh alt|wrong : buggy tree + altfix.py MODE, build, run probe
set -e
cd /app && git checkout -q -- src irr
for p in /kit/bugs/*.patch; do git apply "$p"; done
python3 /kit/altfix.py "$1"
cmake --build /app/build --parallel 16 2>&1 | grep -E "error|warning: .*content_cao|Linking CXX executable bin/minetest|minetest$" | tail -5
set +e
timeout 400 python3 /kit/probe/tests/harvest_c01/run_test.py --junit-out /tmp/j_$1.xml --shots-dir /kit/matrix/shots_$1 > /kit/matrix/$1.log 2>&1
echo "== $1"; grep -E "^(PASS|FAIL) |^wrote" /kit/matrix/$1.log | cut -c1-250
