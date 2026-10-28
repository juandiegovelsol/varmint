#!/usr/bin/env bash
# Behavioral verifier for vega__vega-4163-mm (tickMinStep enforcement fix).
# Applies the PR's test additions, runs f2p+p2p tests, and computes a reward
# from the TAP report. NEVER greps source for the fix — it runs the tests.
set -uo pipefail
mkdir -p /logs/verifier
STDOUT_LOG=/logs/verifier/test-stdout.txt
STDERR_LOG=/logs/verifier/test-stderr.txt
TAP_LOG=/logs/verifier/tap-output.txt
: > "$STDOUT_LOG"; : > "$STDERR_LOG"; : > "$TAP_LOG"

ensure_reward() { [ -f /logs/verifier/reward.txt ] || echo 0 > /logs/verifier/reward.txt; }
trap ensure_reward EXIT

cd /app || { echo "no /app" | tee -a "$STDERR_LOG"; exit 1; }

# Robustness: restore any test paths the agent may have edited to their
# pristine base state BEFORE applying test.patch, so agent edits to tests
# cannot change scoring. (Source fix preserved.)
echo "== restoring test files from harbor_base ==" | tee -a "$STDOUT_LOG"
for _p in $(grep '^+++ b/' /tests/test.patch | sed 's#^+++ b/##'); do
  git -C /app checkout harbor_base -- "$_p" 2>/dev/null || rm -f "/app/$_p" 2>/dev/null || true
done

echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply --binary /tests/test.patch 2>>"$STDERR_LOG" \
  || git apply /tests/test.patch 2>>"$STDERR_LOG" \
  || patch -p1 -i /tests/test.patch 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }

echo "== building vega-scale (pretest/rollup --config-test) ==" | tee -a "$STDOUT_LOG"
cd /app/packages/vega-scale \
  && npm run pretest 2>>"$STDERR_LOG" \
  || { echo "ERROR: pretest build failed" | tee -a "$STDERR_LOG"; exit 1; }

echo "== running f2p + p2p tests via tape ==" | tee -a "$STDOUT_LOG"
# Run all test files in vega-scale (f2p and p2p are all in this package).
/app/node_modules/.bin/tape 'test/**/*-test.js' > "$TAP_LOG" 2>>"$STDERR_LOG" \
  || echo "(tape exited non-zero; parsing report)" | tee -a "$STDOUT_LOG"

cat "$TAP_LOG" >> "$STDOUT_LOG"

echo "== computing reward ==" | tee -a "$STDOUT_LOG"
# Rubric judge - SUB-AGENT backend: no API key, no network. On the first pass there is no
# verdict yet, so judge.py writes a judge request under /logs/verifier/judge/ and prints
# nothing. The `|| echo ""` is load-bearing: the judge must never be able to fail the run.
RUBRIC=""
if [ -f /tests/rubrics.json ]; then
  RUBRIC=$(python3 /tests/judge.py --rubrics /tests/rubrics.json --repo /app \
             2>/logs/verifier/judge.log || echo "")
  echo "Rubric verdict: ${RUBRIC:-pending (judge request written; rescore after grading)}"
fi

python3 /tests/verifier.py --rubric "${RUBRIC:-}" 2>>"$STDERR_LOG" | tee -a "$STDOUT_LOG"
echo "reward=$(cat /logs/verifier/reward.txt 2>/dev/null)" | tee -a "$STDOUT_LOG"
