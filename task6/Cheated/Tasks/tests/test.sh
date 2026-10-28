#!/usr/bin/env bash
# Behavioral verifier for fabricjs__fabric.js-10775-mm
# Tests that calcTextHeight() returns finite value with lineHeight=0 edge case.
# NEVER greps source for the fix.
set -uo pipefail

mkdir -p /logs/verifier
STDOUT_LOG=/logs/verifier/test-stdout.txt
STDERR_LOG=/logs/verifier/test-stderr.txt
REPORT=/logs/verifier/report.xml

: > "$STDOUT_LOG"
: > "$STDERR_LOG"

ensure_reward() {
    [ -f /logs/verifier/reward.txt ] || echo 0 > /logs/verifier/reward.txt
}
trap ensure_reward EXIT

cd /app || { echo "no /app" | tee -a "$STDERR_LOG"; exit 1; }

# ── Step 1: reset test files from harbor_base ────────────────────────────────
echo "== resetting test files ==" | tee -a "$STDOUT_LOG"
_patch_paths=$(
  { sed -n 's#^diff --git a/\(.*\) b/.*#\1#p' /tests/test.patch
     sed -n 's#^diff --git a/.* b/\(.*\)#\1#p' /tests/test.patch
  } | sort -u )
for _p in $_patch_paths; do
    git -C /app checkout harbor_base -- "$_p" 2>/dev/null \
        || rm -f "/app/$_p" 2>/dev/null || true
done

# ── Step 2: apply test.patch ─────────────────────────────────────────────────
echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply --binary /tests/test.patch 2>>"$STDERR_LOG" \
    || git apply /tests/test.patch 2>>"$STDERR_LOG" \
    || patch -p1 -i /tests/test.patch 2>>"$STDERR_LOG" \
    || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }

# ── Step 3: run vitest f2p+p2p tests ─────────────────────────────────────────
echo "== running vitest tests ==" | tee -a "$STDOUT_LOG"
npx vitest run \
    --project unit-node \
    --reporter=junit \
    --outputFile.junit="$REPORT" \
    'src/shapes/Text/Text.spec.ts' \
    >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
    || echo "(vitest exited non-zero; parsing report)" | tee -a "$STDOUT_LOG"

# ── Step 4: compute reward ────────────────────────────────────────────────────
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

python3 /tests/verifier.py "$REPORT" --rubric "${RUBRIC:-}" 2>>"$STDERR_LOG" | tee -a "$STDOUT_LOG"
echo "reward=$(cat /logs/verifier/reward.txt 2>/dev/null)" | tee -a "$STDOUT_LOG"
