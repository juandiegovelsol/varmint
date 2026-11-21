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
  # test.patch (applied above) added src/unittest/test_tile_polygon_offset.cpp and touched
  # src/unittest/CMakeLists.txt + src/unittest/test.cpp (adds a JUnit reporter hook keyed off
  # LUANTI_JUNIT_OUT). Re-running cmake's ninja build picks up the CMakeLists.txt change
  # automatically (ninja -j2 reconfigures itself when a CMakeLists.txt it depends on changes) and
  # only recompiles what changed, so this stays fast even though the full engine was already
  # built once at image build time.
  cmake --build /app/build --parallel 2

  # Build a Catch2 test spec ("name1","name2",...) that selects exactly the configured test
  # cases, from the one-per-line id list the harness wrote to $TEST_IDS_FILE.
  FILTER=""
  while IFS= read -r name; do
    [ -z "$name" ] && continue
    esc=${name//\"/\\\"}
    if [ -z "$FILTER" ]; then
      FILTER="\"${esc}\""
    else
      FILTER="${FILTER},\"${esc}\""
    fi
  done < "$TEST_IDS_FILE"

  LUANTI_JUNIT_OUT="$JUNIT_OUT" /app/bin/luanti --run-unittests --test-module "$FILTER"
}
# Directories holding the repo's test plumbing (configs, helpers) that must also be restored so a
# candidate cannot replace the harness. Space-separated, relative to /app; '' if none.
PROTECTED_DIRS='src/unittest'
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
