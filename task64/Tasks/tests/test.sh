#!/usr/bin/env bash
# Behavioral verifier for tldraw__tldraw-8821-mm
# "Following indicator border is hidden behind menus and panels" (PR #9210 / issue #8821)
#
# Applies the PR's test additions, runs vitest jsdom + RTL tests in @tldraw/tldraw,
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
# NOTE: clean the exact paths test.patch owns, never their parent directory —
# a dirname-wide `git clean` would also delete a legitimate off-file
# alternative's own new source file if it happens to land beside a test file.
_patch_paths=$(grep '^+++ b/' /tests/test.patch | sed 's#^+++ b/##')
for _p in $_patch_paths; do
  git checkout harbor_base -- "$_p" 2>/dev/null \
    || rm -f "/app/$_p" 2>/dev/null || true
done
git clean -fdq -- $_patch_paths 2>/dev/null || true

echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply --binary /tests/test.patch 2>>"$STDERR_LOG" \
  || git apply /tests/test.patch 2>>"$STDERR_LOG" \
  || patch -p1 -i /tests/test.patch 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }

echo "== installing pinned test-only deps (none extra; vitest + RTL are in the lockfile) ==" \
  | tee -a "$STDOUT_LOG"
# @testing-library/react, @testing-library/dom and vitest are already in yarn.lock
# (packages/tldraw's own devDependencies). No extra install step needed.

echo "== running f2p + p2p tests ==" | tee -a "$STDOUT_LOG"
# f2p: "places the following indicator inside the UI layout, not the canvas-in-front overlay"
#      "renders the following indicator after the toolbar and menu panels in the UI layout"
#      "still places the following indicator inside the UI layout while in focus mode"
#      "expands the viewport to fully contain the followed user, preserving our own aspect ratio"
#      "follows a user to another page without unfollowing them"
# p2p: "still renders the rich text toolbar inside the canvas-in-front overlay"
#      "still renders the image toolbar inside the canvas-in-front overlay"
#      "still renders the video toolbar inside the canvas-in-front overlay"
#      "still renders the cursor chat bubble inside the canvas-in-front overlay"
#      "renders no following indicator when no override is supplied and nobody is being followed"
#      "renders the following indicator override exactly once"
#
# These 11 tests live across two files that test.patch adds or extends: a new
# FollowingIndicatorLayering.test.tsx, plus real test cases added to the existing (until now
# all-it.todo) viewport-following.test.ts. Run both; vitest only executes the matched files.
cd /app/packages/tldraw
yarn run -T vitest run \
  --reporter=junit --outputFile="$REPORT" \
  "src/test/ui/FollowingIndicatorLayering" \
  "src/test/viewport-following" \
  >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || echo "(vitest exited non-zero; parsing report anyway)" | tee -a "$STDOUT_LOG"

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
