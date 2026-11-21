#!/usr/bin/env bash
# Behavioral verifier. Resets every path test.patch touches to the immutable harbor_base tag, applies
# the hidden tests, runs ONLY the configured f2p + p2p tests with the repository's own runner into a
# JUnit report, and lets verifier.py turn that report into the reward. Nothing here reads the
# candidate's source to decide anything.
set -uo pipefail

# ---- task-specific values, filled by the task builder ----------------------------------------
# run_tests runs the configured tests with the repository's own runner and writes JUnit XML to
# $JUNIT_OUT. The test ids (f2p + p2p from /tests/config.json) are in $TEST_IDS_FILE, one per line.
# Write plain shell commands here; no quoting of the whole block is needed.
run_tests() {
  cd /app/bokehjs

  # make/tasks/test.ts looks for a system "chromium"/"chromium_rNNNN" binary on PATH instead of
  # using playwright-core's API directly. Point it at the exact Chromium build pinned by (and
  # already installed via) playwright-core at image build time.
  export BOKEH_CHROME="$(node -e "console.log(require('playwright-core').chromium.executablePath())" 2>/dev/null || true)"

  echo "=== node make build ==="
  node make build 2>&1 | tail -n 300

  mapfile -t IDS < "$TEST_IDS_FILE"
  GREP_ARGS=()
  for id in "${IDS[@]}"; do
    esc=$(node -e 'process.stdout.write(process.argv[1].replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))' "$id")
    GREP_ARGS+=("--grep=^${esc}\$")
  done

  # The configured tests are behavioral browser tests in the unit suite: they render layouts
  # and assert on the geometry of what is drawn, with no stored layout or image snapshots.
  echo "=== node make test:unit (${#IDS[@]} tests) ==="
  mkdir -p /tmp/logs
  node make test:unit "${GREP_ARGS[@]}" > /tmp/logs/unit.log 2>&1
  echo "(test:unit exit code: $?)"
  tail -n 300 /tmp/logs/unit.log

  node /app/gen_junit.mjs /app/tests.json "$JUNIT_OUT" /app/bokehjs /tmp/logs
  GEN_STATUS=$?
  if [ $GEN_STATUS -ne 0 ]; then
    echo "FATAL: gen_junit.mjs failed with status $GEN_STATUS" >&2
    exit $GEN_STATUS
  fi
}
# Directories holding the repo's test plumbing (configs, helpers) that must also be restored so a
# candidate cannot replace the harness. Space-separated, relative to /app; '' if none.
PROTECTED_DIRS='bokehjs/test/framework bokehjs/test/devtools bokehjs/test/unit/index.ts bokehjs/make'
# -----------------------------------------------------------------------------------------------

mkdir -p /logs/verifier
STDOUT_LOG=/logs/verifier/test-stdout.txt
STDERR_LOG=/logs/verifier/test-stderr.txt
export JUNIT_OUT=/logs/verifier/junit.xml
export TEST_IDS_FILE=/logs/verifier/test_ids.txt
: > "$STDOUT_LOG"; : > "$STDERR_LOG"
rm -f "$JUNIT_OUT" /logs/verifier/reward.txt /logs/verifier/reward.json

ensure_reward() { [ -f /logs/verifier/reward.txt ] || echo 0 > /logs/verifier/reward.txt; }
trap ensure_reward EXIT

cd /app || { echo "no /app" | tee -a "$STDERR_LOG"; exit 1; }

# 1. Restore every path test.patch touches. Both diff headers are read, so new files, binary
#    baselines (image-comparison PNGs, snapshots), renames and deletions are all covered.
_patch_paths=$( { sed -n 's#^diff --git a/\(.*\) b/.*#\1#p' /tests/test.patch
                  sed -n 's#^diff --git a/.* b/\(.*\)#\1#p' /tests/test.patch; } | sort -u )
for _p in $_patch_paths; do
  git -C /app checkout harbor_base -- "$_p" 2>/dev/null || rm -rf "/app/$_p" 2>/dev/null || true
done
for _d in $PROTECTED_DIRS; do
  git -C /app checkout harbor_base -- "$_d" 2>/dev/null || true
  git -C /app clean -fdq -- "$_d" 2>/dev/null || true
done

# 2. Apply the hidden tests.
echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply --binary /tests/test.patch 2>>"$STDERR_LOG" \
  || git apply /tests/test.patch 2>>"$STDERR_LOG" \
  || patch -p1 -i /tests/test.patch 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }

# 3. Run only the configured tests.
python3 - <<'PY' > "$TEST_IDS_FILE"
import json
c = json.load(open("/tests/config.json"))
print("\n".join(c["f2p"] + c["p2p"]))
PY
echo "== running f2p + p2p tests ==" | tee -a "$STDOUT_LOG"
( cd /app && run_tests ) >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || echo "(tests exited non-zero; parsing the report)" | tee -a "$STDOUT_LOG"

# 4. Reward from the report.
echo "== computing reward ==" | tee -a "$STDOUT_LOG"
python3 /tests/verifier.py 2>>"$STDERR_LOG" | tee -a "$STDOUT_LOG"
echo "reward=$(cat /logs/verifier/reward.txt 2>/dev/null)" | tee -a "$STDOUT_LOG"
