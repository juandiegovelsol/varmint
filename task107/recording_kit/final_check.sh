#!/bin/bash
# final_check.sh BUNDLE : replay the bundle in the dev container the way the image + verifier do it,
# without test.sh/solve.sh: base + environment/bugs/*.patch (= harbor_base), tests/test.patch,
# run exactly the f2p+p2p ids of tests/config.json; then solution/fix.patch, rebuild, run again.
set -e
B=$1
pkill -x Xvfb 2>/dev/null || true; pkill -x DDNet 2>/dev/null || true; pkill -x DDNet-Server 2>/dev/null || true
cd /app && git reset -q --hard base && git clean -fdq -e build
for p in "$B"/environment/bugs/*.patch; do git apply "$p" || patch -p1 < "$p"; done
git -c user.email=h@l -c user.name=h commit -qam harbor_base_sim
git apply --binary "$B/tests/test.patch"
mapfile -t IDS < <(python3 -c "import json;c=json.load(open('$B/tests/config.json'));print('\n'.join(c['f2p']+c['p2p']))")
run() {
  (cd build && cmake --build . --parallel "$(nproc)" --target DDNet DDNet-Server 2>&1 | grep -E "error|FAILED" || true)
  HOME=/root DDNET_BUILD_DIR=/app/build timeout 1800 python3 -m pytest -p no:cacheprovider -v \
    --junitxml=/kit/runs/final_$1.xml "${IDS[@]}" > /kit/runs/final_$1.log 2>&1 || true
  echo "== $1"; grep -E "(PASSED|FAILED|ERROR)( |$)|passed|failed" /kit/runs/final_$1.log | sed 's#scripts/test_harvest_c01_hookline.py::##' | cut -c1-150
}
run buggy
git apply "$B/solution/fix.patch" || patch -p1 < "$B/solution/fix.patch"
run fixed
