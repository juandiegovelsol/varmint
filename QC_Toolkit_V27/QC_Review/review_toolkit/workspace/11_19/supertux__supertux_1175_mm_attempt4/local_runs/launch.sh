#!/usr/bin/env bash
export MSYS_NO_PATHCONV=1
W="$(cd "$(dirname "$0")" && pwd -W 2>/dev/null || pwd)"
T="$W/Tasks/supertux__supertux_1175_mm"
S="$W/../scripts"
run() { # name mode
  mkdir -p "$W/$1/logs"
  docker run --rm --network none --cpus 4 --memory 8g \
    -v "$T/solution:/solution:ro" -v "$T/tests:/tests:ro" -v "$W/$1/logs:/logs" -v "$S/run_mode.sh:/run_mode.sh:ro" \
    qc_st1175:task bash /run_mode.sh "$2" > "$W/$1/docker.txt" 2>&1
  echo "$1 exit=$?" >> "$W/$1/docker.txt"
}
run oracle oracle & run nop nop & run oracle_rerun oracle & wait
for d in oracle nop oracle_rerun; do echo "$d reward=$(cat $W/$d/logs/verifier/reward.txt 2>/dev/null)"; done
