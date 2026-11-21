#!/usr/bin/env bash
# crosscheck.sh <plan>   -- runs inside the task image (buggy /app)
#   /tests, /solution, /parts mounted read-only; /out writable
set -u
plan="$1"
cd /app
summ=/out/$plan.summary.txt
: > "$summ"
git apply /tests/test.patch || { echo "test.patch FAILED" >> "$summ"; exit 1; }
cmake -S /app -B /build > /dev/null
export SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy
build_and_run() {  # $1 label, rest = extra gtest args
  local label="$1"; shift
  if ! cmake --build /build -j6 --target test_supertux2 > "/out/$label.build.log" 2>&1; then
    echo "$label: BUILD FAILED" >> "$summ"; return
  fi
  /build/test_supertux2 --gtest_filter='RockBehaviour.*' "$@" > "/out/$label.log" 2>&1
  local failed okn
  failed=$(grep -E '^\[  FAILED  \] RockBehaviour\.[A-Za-z]+ \(' "/out/$label.log" | sed -E 's/.*RockBehaviour\.([A-Za-z]+).*/\1/' | sort | uniq -c | awk '{printf "%s(x%s) ", $2, $1}')
  okn=$(grep -cE '^\[       OK \] RockBehaviour' "/out/$label.log")
  echo "$label: ok_lines=$okn failed=[ $failed]" >> "$summ"
}
ap() { git apply "/parts/$1.patch" || { echo "apply $1 FAILED" >> "$summ"; return 1; }; }
rv() { git apply -R "/parts/$1.patch" || { echo "revert $1 FAILED" >> "$summ"; return 1; }; }
PARTS="P0_coins P1_carry P2_throwdir P3_group P4_collides P5_leaf"
case "$plan" in
  single)
    build_and_run base_x3 --gtest_repeat=3 --gtest_shuffle
    for p in $PARTS; do ap "$p" && { build_and_run "only_$p"; rv "$p"; }; done
    ;;
  loo)
    for p in $PARTS; do
      for q in $PARTS; do [ "$q" = "$p" ] || ap "$q"; done
      build_and_run "all_but_$p"
      for q in $PARTS; do [ "$q" = "$p" ] || rv "$q"; done
    done
    ;;
  golden)
    git apply --check /solution/fix.patch && echo "git apply --check fix.patch on harbor_base: OK" >> "$summ"
    for p in $PARTS; do ap "$p"; done
    git diff --stat -- src >> "$summ"
    echo "parts-union vs fix.patch: $(git diff -- src | git apply -R --check - 2>&1 >/dev/null && echo same-tree)" >> "$summ"
    build_and_run golden_x10 --gtest_repeat=10 --gtest_shuffle
    for p in $PARTS; do rv "$p"; done
    python3 /parts/altB.py >> "$summ" && git diff -- src > /out/altB.patch && build_and_run altB_x3 --gtest_repeat=3 --gtest_shuffle
    ;;
esac
echo "done $plan" >> "$summ"
