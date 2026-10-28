#!/usr/bin/env bash
# Behavioral verifier for IvarK__AntimatterDimensionsSourceCode-3020-mm
#
# Applies the synthetic test additions (Vitest + @vue/test-utils v1), runs the
# f2p/p2p tests that mount the real components against a stubbed game state and
# assert on what is rendered / clickable, then computes a reward from the JUnit
# XML report.
#
# NEVER greps source for the fix — it mounts the Vue components and checks
# the rendered output.
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

# ── Step 1: Reset every path test.patch touches to its pristine harbor_base
# state before applying, so agent edits to tests cannot affect scoring and
# re-runs are idempotent. Use diff --git headers (present for text, binary,
# renames, and deletes) NOT +++ b/ (absent for binary/renames).
echo "== resetting test.patch paths ==" | tee -a "$STDOUT_LOG"
_patch_paths=$(
  { sed -n 's#^diff --git a/\(.*\) b/.*#\1#p' /tests/test.patch
    sed -n 's#^diff --git a/.* b/\(.*\)#\1#p' /tests/test.patch
  } | sort -u
)
for _p in $_patch_paths; do
  git -C /app checkout harbor_base -- "$_p" 2>/dev/null \
    || rm -f "/app/$_p" 2>/dev/null \
    || true
  # Scoped to the exact path (never its parent directory): a path like
  # vitest.config.js sits at the repo root, and `git clean -fd .` there would
  # delete every untracked file in the whole tree - including any new file
  # the fix itself adds outside src/__tests__/.
  git -C /app clean -fq -- "$_p" 2>/dev/null || true
done

# ── Step 2: Apply test.patch (adds vitest.config.js + src/__tests__/)
echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply /tests/test.patch             2>>"$STDERR_LOG" \
  || git apply --whitespace=nowarn /tests/test.patch 2>>"$STDERR_LOG" \
  || patch -p1 -i /tests/test.patch     2>>"$STDERR_LOG" \
  || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }

# ── Step 3: Install pinned test-only dependencies
# @vitejs/plugin-vue2 needs vue 2.7.x and vue-template-compiler must match it
# exactly; the repo ships 2.6.x, so both are pinned here for the test run only.
echo "== installing pinned test-only deps ==" | tee -a "$STDOUT_LOG"
npm install --no-save --prefer-offline \
    "vitest@1.6.1" \
    "@vitejs/plugin-vue2@1.1.2" \
    "@vue/test-utils@1.3.6" \
    "jsdom@24.1.3" \
    "vue@2.7.16" \
    "vue-template-compiler@2.7.16" \
    2>>"$STDERR_LOG" \
  || npm install --no-save \
    "vitest@1.6.1" \
    "@vitejs/plugin-vue2@1.1.2" \
    "@vue/test-utils@1.3.6" \
    "jsdom@24.1.3" \
    "vue@2.7.16" \
    "vue-template-compiler@2.7.16" \
    2>>"$STDERR_LOG" \
  || { echo "ERROR: npm install failed" | tee -a "$STDERR_LOG"; exit 1; }

# ── Step 4: Run the f2p/p2p tests, produce JUnit XML at $REPORT
echo "== running f2p/p2p tests ==" | tee -a "$STDOUT_LOG"
npx vitest run \
    >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || echo "(vitest exited non-zero; parsing report)" | tee -a "$STDOUT_LOG"

# ── Step 5: Compute reward from the JUnit XML
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
