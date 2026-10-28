#!/usr/bin/env bash
# Behavioral verifier for flutter__flutter-181500-mm.
# Applies the PR test additions, runs f2p+p2p tests, computes reward.
# NEVER greps source for the fix — scores from test execution only.
set -uo pipefail
mkdir -p /logs/verifier
STDOUT_LOG=/logs/verifier/test-stdout.txt
STDERR_LOG=/logs/verifier/test-stderr.txt
REPORT=/logs/verifier/report.json

: > "$STDOUT_LOG"; : > "$STDERR_LOG"

ensure_reward() { [ -f /logs/verifier/reward.txt ] || echo 0 > /logs/verifier/reward.txt; }
trap ensure_reward EXIT

cd /app || { echo "no /app" | tee -a "$STDERR_LOG"; exit 1; }

# Explicit PATH for flutter tool (also set by Dockerfile ENV)
export PATH="/opt/flutter/bin:${PATH}"

# Restore any test files the agent may have edited to their pristine base state
# BEFORE applying test.patch, so agent edits to tests cannot influence scoring.
echo "== restoring test files from harbor_base ==" | tee -a "$STDOUT_LOG"
for _p in $(grep '^+++ b/' /tests/test.patch | sed 's#^+++ b/##'); do
  git checkout harbor_base -- "$_p" 2>/dev/null \
    || rm -f "/app/$_p" 2>/dev/null || true
done

echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply --binary /tests/test.patch 2>>"$STDERR_LOG" \
  || git apply /tests/test.patch 2>>"$STDERR_LOG" \
  || patch -p1 -i /tests/test.patch 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }

echo "== building name regex from config.json ==" | tee -a "$STDOUT_LOG"
PATTERN=$(python3 - <<'PYEOF'
import re, json
c = json.load(open('/tests/config.json'))
names = c.get('f2p', []) + c.get('p2p', [])
print('|'.join('(?:' + re.escape(n) + ')' for n in names))
PYEOF
) || { echo "ERROR: failed to build test name pattern" | tee -a "$STDERR_LOG"; exit 1; }

echo "pattern: $PATTERN" | tee -a "$STDOUT_LOG"

# flutter test must run from within packages/flutter/ (not the monorepo root)
echo "== running f2p + p2p tests ==" | tee -a "$STDOUT_LOG"
cd /app/packages/flutter
flutter test \
  test/material/date_range_picker_test.dart \
  --name "$PATTERN" \
  --reporter json > "$REPORT" 2>>"$STDERR_LOG" \
  || echo "(flutter test exited non-zero; parsing report)" | tee -a "$STDOUT_LOG"

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

python3 /tests/verifier.py 2>>"$STDERR_LOG" | tee -a "$STDOUT_LOG"
echo "reward=$(cat /logs/verifier/reward.txt 2>/dev/null)" | tee -a "$STDOUT_LOG"
