#!/usr/bin/env bash
# Behavioral verifier for IvarK__AntimatterDimensionsSourceCode-2843-mm.
# Applies the synthetic test patch (vitest unit tests for the whole-number display
# path, from the two rendered panels down through the shared format helpers),
# installs test-only deps, runs f2p/p2p tests into a JUnit XML report, and calls verifier.py.
# NEVER greps candidate source for the fix — the test runs the production code.
set -uo pipefail
mkdir -p /logs/verifier
STDOUT_LOG=/logs/verifier/test-stdout.txt
STDERR_LOG=/logs/verifier/test-stderr.txt
REPORT=/logs/verifier/report.xml

: > "$STDOUT_LOG"; : > "$STDERR_LOG"

ensure_reward() { [ -f /logs/verifier/reward.txt ] || echo 0 > /logs/verifier/reward.txt; }
trap ensure_reward EXIT

cd /app || { echo "no /app" | tee -a "$STDERR_LOG"; exit 1; }

# ------------------------------------------------------------------
# Reset EVERY path the patch touches to harbor_base (idempotency +
# agent-edit protection). For new files not in harbor_base, the
# checkout fails silently and rm -f removes any leftover from a
# previous run.
# ------------------------------------------------------------------
_patch_paths=$(
  { sed -n 's#^diff --git a/\(.*\) b/.*#\1#p' /tests/test.patch
    sed -n 's#^diff --git a/.* b/\(.*\)#\1#p' /tests/test.patch
  } | sort -u )
for _p in $_patch_paths; do
  git -C /app checkout harbor_base -- "$_p" 2>/dev/null || rm -f "/app/$_p" 2>/dev/null || true
done
git -C /app clean -fdq -- $(printf '%s\n' $_patch_paths | xargs -r -n1 dirname | sort -u) 2>/dev/null || true

echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply --binary /tests/test.patch 2>>"$STDERR_LOG" \
  || git apply /tests/test.patch 2>>"$STDERR_LOG" \
  || patch -p1 -i /tests/test.patch 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }

echo "== installing pinned test-only deps ==" | tee -a "$STDOUT_LOG"
# Install vitest and jsdom without modifying package.json/package-lock.json.
# jsdom is the virtual browser environment required by vitest for this test.
npm install --no-save --no-package-lock --legacy-peer-deps \
    vitest@1.6.0 jsdom@24.1.3 \
    >> "$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || { echo "ERROR: npm install failed" | tee -a "$STDERR_LOG"; exit 1; }

echo "== running f2p/p2p tests ==" | tee -a "$STDOUT_LOG"
# Run every suite the test patch installs and emit a JUnit XML report.
# vitest exits non-zero when tests fail; we capture the exit code and continue to parse the report.
npx vitest run \
    --config /app/vitest.config.mjs \
    --reporter=junit \
    --outputFile="$REPORT" \
    /app/javascripts/__tests__/notation.test.js \
    /app/javascripts/__tests__/format-pipeline.test.js \
    >> "$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || echo "(vitest exited non-zero; parsing report)" | tee -a "$STDOUT_LOG"

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
