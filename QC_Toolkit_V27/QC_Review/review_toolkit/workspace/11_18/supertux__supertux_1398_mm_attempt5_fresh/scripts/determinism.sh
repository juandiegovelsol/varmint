#!/usr/bin/env bash
# Runs inside the task image: 5 fresh processes per state, shuffled test order each time.
set -u
cd /app
git apply /tests/test.patch
cmake -S /app -B /build > /dev/null 2>&1
export SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy
runs() {
  cmake --build /build -j8 --target test_supertux2 > /out/$1.build.log 2>&1 || { echo "$1 BUILD FAILED"; return; }
  for i in 1 2 3 4 5; do
    /build/test_supertux2 --gtest_filter='RockBehaviour.*' --gtest_shuffle --gtest_random_seed=$((i*7919)) > /out/$1_$i.log 2>&1
    echo "$1 run$i exit=$? seed=$((i*7919)) passed=$(grep -cE '^\[       OK \] RockBehaviour' /out/$1_$i.log) failed=$(grep -E '^\[  FAILED  \] RockBehaviour\.[A-Za-z]+ \(' /out/$1_$i.log | sed -E 's/.*RockBehaviour\.([A-Za-z]+).*/\1/' | sort | tr '\n' ',')"
  done
}
runs base
git apply /solution/fix.patch
runs golden
