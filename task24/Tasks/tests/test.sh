#!/usr/bin/env bash
# Behavioral verifier for tldraw__tldraw-9133-mm
#
# Applies the test additions, runs vitest jsdom tests in @tldraw/tldraw,
# and computes a reward from the JUnit XML report.
# NEVER greps source for the fix — it runs the tests.
set -uo pipefail
mkdir -p /logs/verifier
STDOUT_LOG=/logs/verifier/test-stdout.txt
STDERR_LOG=/logs/verifier/test-stderr.txt
REPORT=/logs/verifier/report.xml
: > "$STDOUT_LOG"; : > "$STDERR_LOG"

ensure_reward() { [ -f /logs/verifier/reward.txt ] || echo 0 > /logs/verifier/reward.txt; }
trap ensure_reward EXIT

cd /app || { echo "no /app" | tee -a "$STDERR_LOG"; exit 1; }

# ── Reset test files the agent may have touched ─────────────────────────────
# Restore every path mentioned in test.patch to the pristine harbor_base state
# BEFORE applying test.patch, so agent edits to tests cannot affect scoring.
# The agent's source fix (in the non-test files) is preserved.
for _p in $(grep '^+++ b/' /tests/test.patch | sed 's#^+++ b/##'); do
  git checkout harbor_base -- "$_p" 2>/dev/null \
    || rm -f "/app/$_p" 2>/dev/null || true
done
git clean -fdq -- \
  $(grep '^+++ b/' /tests/test.patch | sed 's#^+++ b/##' | xargs -r dirname | sort -u) \
  2>/dev/null || true

echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply --binary /tests/test.patch 2>>"$STDERR_LOG" \
  || git apply /tests/test.patch 2>>"$STDERR_LOG" \
  || patch -p1 -i /tests/test.patch 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }

echo "== installing pinned test-only deps (none extra; vitest is in the lockfile) ==" \
  | tee -a "$STDOUT_LOG"
# All test dependencies are already in yarn.lock; no extra install step needed.

echo "== running f2p + p2p tests ==" | tee -a "$STDOUT_LOG"
# f2p: "hides the export-as submenu when all export actions are removed"
#      "hides the copy-as submenu when all copy actions are removed"
#      "hides the export-all-as submenu when all export-all actions are removed"
# p2p: "shows the export-as and copy-as submenus by default"
#      "keeps the export-as submenu when at least one export action remains"
#      "shows the export-all-as submenu by default"
#      "keeps the export-all-as submenu when at least one export-all action remains"
#
# All seven tests live in the single ContextMenu.test.tsx file that test.patch appends to
# (the main-menu cases open the main menu dropdown from the same rendered <Tldraw/>).
# We run the whole file; vitest only executes the matched pattern.
cd /app/packages/tldraw
yarn run -T vitest run \
  --reporter=junit --outputFile="$REPORT" \
  "src/test/ui/ContextMenu" \
  >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || echo "(vitest exited non-zero; parsing report anyway)" | tee -a "$STDOUT_LOG"

# Rubric judge — SUB-AGENT backend: no API key, no network. On the first pass there is no
# verdict yet, so judge.py writes a judge request under /logs/verifier/judge/ and prints
# nothing; scoring falls back to tests alone. Once a judge sub-agent has written
# verdict.json there, `mm_run.sh <task> rescore` folds the verdict into the reward.
# The `|| echo ""` is load-bearing: the judge must never be able to fail the run.
RUBRIC=""
if [ -f /tests/rubrics.json ]; then
  RUBRIC=$(python3 /tests/judge.py --rubrics /tests/rubrics.json --repo /app \
             2>/logs/verifier/judge.log || echo "")
  echo "Rubric verdict: ${RUBRIC:-pending (judge request written; rescore after grading)}" \
    | tee -a "$STDOUT_LOG"
fi

echo "== computing reward ==" | tee -a "$STDOUT_LOG"
python3 /tests/verifier.py --rubric "${RUBRIC:-}" 2>>"$STDERR_LOG" | tee -a "$STDOUT_LOG"
echo "reward=$(cat /logs/verifier/reward.txt 2>/dev/null)" | tee -a "$STDOUT_LOG"
