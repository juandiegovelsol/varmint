#!/usr/bin/env bash
# In-container QC runner for task109 (pw109:task image). Usage: run_mode.sh <oracle|nop|alt_tint>
set -u
MODE="$1"
cd /app || exit 1
echo "== QC: HEAD $(git rev-parse --short HEAD) tag $(git tag --points-at HEAD) mode $MODE =="
case "$MODE" in
  oracle)
    git apply --check /solution/fix.patch && echo "FIX_APPLY_CHECK=OK" || { echo "FIX_APPLY_CHECK=FAIL"; exit 2; }
    git apply /solution/fix.patch ;;
  nop) : ;;
  replay)
    git apply /replay/submission.patch && echo "REPLAY_APPLY=OK" || { echo "REPLAY_APPLY=FAIL"; exit 2; } ;;
  alt_tint)
    git apply /solution/fix.patch || { echo "FIX_APPLY_FAILED"; exit 2; }
    python3 /qc/add_tint.py || exit 3 ;;
  *) echo "unknown mode $MODE"; exit 4 ;;
esac
git diff --stat harbor_base
bash /tests/test.sh
echo "QC_MODE=$MODE QC_REWARD=$(cat /logs/verifier/reward.txt 2>/dev/null)"
