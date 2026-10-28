#!/usr/bin/env bash
# Behavioral verifier for recharts__recharts-6937-mm.
# Resets test files to harbor_base, applies test.patch, runs ONLY the configured
# f2p + p2p tests, computes reward.
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
# Paths come from the `diff --git` headers, not from `+++ b/`: binary and rename
# diffs carry no `+++ b/` line, so that form silently skips them and the suite
# scores 0 on every re-run after the first.
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

# ── Step 3: build the run set from config.json ───────────────────────────────
# Only f2p + p2p may run. The name filter is built from the leaf test names so it
# does not depend on how the reporter joins suite names; verifier.py then scores
# the fully-qualified ids exactly.
echo "== selecting f2p + p2p tests ==" | tee -a "$STDOUT_LOG"
TEST_FILES=$(python3 -c '
import json
print(" ".join(json.load(open("/tests/config.json"))["test_files"]))
')
NAME_FILTER=$(python3 -c '
import json, re
c = json.load(open("/tests/config.json"))
seen = []
for ident in c["f2p"] + c["p2p"]:
    name = ident.split("::", 1)[1] if "::" in ident else ident
    leaf = name.split(" > ")[-1]
    if leaf not in seen:
        seen.append(leaf)
print("|".join(re.escape(s) for s in seen))
')
echo "test files: $TEST_FILES" | tee -a "$STDOUT_LOG"

# ── Step 4: run f2p + p2p vitest tests ───────────────────────────────────────
echo "== running vitest ==" | tee -a "$STDOUT_LOG"
# shellcheck disable=SC2086
npx vitest run \
  --reporter=junit \
  --outputFile="$REPORT" \
  -t "$NAME_FILTER" \
  $TEST_FILES \
  >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || echo "(vitest exited non-zero; parsing report)" | tee -a "$STDOUT_LOG"

# ── Step 5: compute reward ───────────────────────────────────────────────────
# Scored from the behavioral f2p + p2p results only - nothing here is graded by eye.
echo "== computing reward ==" | tee -a "$STDOUT_LOG"
# Rubric judge — SUB-AGENT backend: no API key, no network. On the first pass there is no
# verdict yet, so judge.py writes a judge request under /logs/verifier/judge/ and prints
# nothing; scoring falls back to tests alone. Once a judge sub-agent has written
# verdict.json there, `mm_run.sh <task> rescore` folds the verdict into the reward.
# The `|| echo ""` is load-bearing: the judge must never be able to fail the run.
RUBRIC=""
if [ -f /tests/rubrics.json ]; then
  RUBRIC=$(python3 /tests/judge.py --rubrics /tests/rubrics.json --repo /app \
             2>/logs/verifier/judge.log || echo "")
  echo "Rubric verdict: ${RUBRIC:-pending (judge request written; rescore after grading)}"
fi

python3 /tests/verifier.py --rubric "${RUBRIC:-}"

echo "reward=$(cat /logs/verifier/reward.txt 2>/dev/null)" | tee -a "$STDOUT_LOG"
