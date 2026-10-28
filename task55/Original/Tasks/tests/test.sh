#!/usr/bin/env bash
# Behavioral verifier for facebook__lexical-7959-mm.
# Applies the test additions, runs the f2p+p2p vitest suite, and computes a reward from
# the JUnit XML report. NEVER greps source for the fix -- it runs the tests.
set -uo pipefail
mkdir -p /logs/verifier
STDOUT_LOG=/logs/verifier/test-stdout.txt
STDERR_LOG=/logs/verifier/test-stderr.txt
REPORT=/logs/verifier/report.xml
: > "$STDOUT_LOG"; : > "$STDERR_LOG"

ensure_reward() { [ -f /logs/verifier/reward.txt ] || echo 0 > /logs/verifier/reward.txt; }
trap ensure_reward EXIT

cd /app || { echo "no /app" | tee -a "$STDERR_LOG"; exit 1; }

# Robustness: restore any test paths the agent may have edited to their pristine base
# state BEFORE applying test.patch, so agent edits to tests cannot change scoring. The
# suite is self-contained in the single file test.patch adds -- it imports no shared
# test helper -- so this one reset covers the whole harness.
echo "== resetting test files from harbor_base ==" | tee -a "$STDOUT_LOG"
for _p in $(grep '^+++ b/' /tests/test.patch | sed 's#^+++ b/##'); do
  git -C /app checkout harbor_base -- "$_p" 2>/dev/null \
    || rm -f "/app/$_p" 2>/dev/null \
    || true
done

echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply --binary /tests/test.patch 2>>"$STDERR_LOG" \
  || git apply /tests/test.patch 2>>"$STDERR_LOG" \
  || patch -p1 -i /tests/test.patch 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }

echo "== running f2p + p2p tests (vitest) ==" | tee -a "$STDOUT_LOG"
npx vitest run --project unit \
  packages/lexical-react/src/__tests__/unit/CollaborationAwareness.test.tsx \
  --reporter=verbose --reporter=junit --outputFile.junit="$REPORT" \
  >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || echo "(vitest exited non-zero; will parse report)" | tee -a "$STDOUT_LOG"

# Fallback: if outputFile.junit not supported, try legacy flag
if [ ! -f "$REPORT" ]; then
  echo "== retry with --outputFile flag ==" | tee -a "$STDOUT_LOG"
  npx vitest run --project unit \
    packages/lexical-react/src/__tests__/unit/CollaborationAwareness.test.tsx \
    --reporter=junit --outputFile="$REPORT" \
    >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
    || echo "(vitest fallback exited non-zero)" | tee -a "$STDOUT_LOG"
fi

echo "== computing reward ==" | tee -a "$STDOUT_LOG"
# Rubric judge. This task ships NO rubric layer (its nine f2p behaviours are all
# directly observable, so there is no defect class the behavioral suite structurally
# cannot catch), so the guard below is false and the block no-ops -- the --rubric
# plumbing stays for a uniform verifier shape and yields rubric_passed = -1.
# The `|| echo ""` is load-bearing: a judge must never be able to fail the run.
RUBRIC=""
if [ -f /tests/rubrics.json ]; then
  RUBRIC=$(python3 /tests/judge.py --rubrics /tests/rubrics.json --repo /app \
             2>/logs/verifier/judge.log || echo "")
  echo "Rubric verdict: ${RUBRIC:-pending (judge request written; rescore after grading)}"
fi

python3 /tests/verifier.py --rubric "${RUBRIC:-}" 2>>"$STDERR_LOG" | tee -a "$STDOUT_LOG"
echo "reward=$(cat /logs/verifier/reward.txt 2>/dev/null)" | tee -a "$STDOUT_LOG"
