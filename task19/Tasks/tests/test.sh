#!/usr/bin/env bash
# Behavioral verifier for recharts__recharts-6814-mm.
# Applies test.patch, runs f2p+p2p vitest tests, computes reward.
# NEVER greps source for the fix — reward comes from the test report only.
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

# ── Step 1: restore any test paths the agent may have edited ─────────────────
# Paths come from the `diff --git a/... b/...` headers, not from `+++ b/`, so that
# binary/rename hunks (which carry no `+++ b/` line) are reset too and re-runs stay
# idempotent instead of silently scoring 0.
echo "== restoring test files to harbor_base ==" | tee -a "$STDOUT_LOG"
_patch_paths=$( { sed -n 's#^diff --git a/\(.*\) b/.*#\1#p' /tests/test.patch
                  sed -n 's#^diff --git a/.* b/\(.*\)#\1#p' /tests/test.patch; } | sort -u )
for _p in $_patch_paths; do
  git -C /app checkout harbor_base -- "$_p" 2>/dev/null || rm -f "/app/$_p" 2>/dev/null || true
done

# ── Step 2: apply test.patch ──────────────────────────────────────────────────
echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply --binary /tests/test.patch 2>>"$STDERR_LOG" \
  || git apply /tests/test.patch 2>>"$STDERR_LOG" \
  || patch -p1 -i /tests/test.patch 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }



# ── Step 3: install pinned test-only deps ────────────────────────────────────
echo "== installing test deps ==" | tee -a "$STDOUT_LOG"
# pnpm is already installed in the image; no extra deps needed for vitest.

# ── Step 4: run f2p + p2p vitest tests ───────────────────────────────────────
echo "== running vitest ==" | tee -a "$STDOUT_LOG"
pnpm vitest run \
  --reporter=junit \
  --outputFile="$REPORT" \
  "test/chart/PieChart.spec.tsx" \
  >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || echo "(vitest exited non-zero; parsing report)" | tee -a "$STDOUT_LOG"

# ── Step 5: compute reward ───────────────────────────────────────────────────
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
