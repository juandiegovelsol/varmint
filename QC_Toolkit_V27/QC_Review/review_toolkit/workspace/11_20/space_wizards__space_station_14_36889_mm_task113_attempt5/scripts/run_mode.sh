#!/usr/bin/env bash
# Runs inside the task container: mimics harbor's oracle / nop flow.
#   oracle: bash /solution/solve.sh, then bash /tests/test.sh
#   nop:    bash /tests/test.sh only (untouched base)
set -u
mode="$1"
mkdir -p /logs/agent /logs/verifier
if [ "$mode" = "oracle" ]; then
  bash /solution/solve.sh > /logs/agent/oracle.txt 2>&1
  echo "solve.sh exit=$?" >> /logs/agent/oracle.txt
fi
bash /tests/test.sh > /logs/verifier/test_sh_console.txt 2>&1
echo "test.sh exit=$?" >> /logs/verifier/test_sh_console.txt
echo "reward.txt=$(cat /logs/verifier/reward.txt 2>/dev/null)" >> /logs/verifier/test_sh_console.txt
