#!/usr/bin/env bash
# In-container QC runner for task108 Attempt5 (qc_st1398:task). Usage: run_mode.sh <oracle|nop|replay>
set -u
MODE="$1"
cd /app || exit 1
echo "== QC: HEAD $(git rev-parse --short HEAD) tag $(git tag --points-at HEAD) mode $MODE =="
case "$MODE" in
  oracle)
    git apply --check /solution/fix.patch && echo "FIX_APPLY_CHECK=OK" || { echo "FIX_APPLY_CHECK=FAIL"; exit 2; }
    bash /solution/solve.sh >/dev/null 2>&1 && echo "SOLVE_SH=OK" || echo "SOLVE_SH=FAIL" ;;
  nop) : ;;
  replay)
    git apply /replay/submission.patch && echo "REPLAY_APPLY=OK" || { echo "REPLAY_APPLY=FAIL"; exit 2; } ;;
  *) echo "unknown mode $MODE"; exit 4 ;;
esac
git diff --stat harbor_base
ls -la /app/.harbor_assets
bash /tests/test.sh
echo "QC_MODE=$MODE QC_REWARD=$(cat /logs/verifier/reward.txt 2>/dev/null)"
cat /logs/verifier/reward.json 2>/dev/null; echo
