#!/usr/bin/env bash
# Local harbor-style control run: run_mode.sh <oracle|nop> <outdir-name>
set -u
export MSYS_NO_PATHCONV=1
W="/c/Users/Juan V/Documents/Outlier/VARMINT/QC_Toolkit_V27/QC_Review/review_toolkit/workspace/11_16/luanti_org__luanti_15105_mm/local_runs"
T="$W/Tasks/luanti_org__luanti_15105_mm"
mode="$1"; name="$2"
out="$W/$name"; rm -rf "$out"; mkdir -p "$out"
c="qc15105_$name"
docker rm -f "$c" >/dev/null 2>&1
start=$(date +%s)
docker run -d --name "$c" --cpus 4 --memory 8g qc15105:task sleep infinity >/dev/null
if [ "$mode" = oracle ]; then
  docker cp "$T/solution" "$c:/solution"
  docker exec "$c" bash /solution/solve.sh > "$out/oracle.txt" 2>&1
fi
docker cp "$T/tests" "$c:/tests"
docker exec "$c" bash /tests/test.sh > "$out/console.log" 2>&1
docker cp "$c:/logs/verifier" "$out/verifier"
docker rm -f "$c" >/dev/null
secs=$(( $(date +%s) - start ))
echo "$name rc=0 secs=$secs reward=$(cat "$out/verifier/reward.txt") $(tr -d '\n ' < "$out/verifier/reward_detail.json")" >> "$W/run_local_summary.log"
