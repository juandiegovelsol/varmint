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
  rm -rf core-tests/build/test-results

  Xvfb :99 -screen 0 1280x800x24 >/tmp/xvfb.log 2>&1 &
  XVFB_PID=$!
  trap 'kill "$XVFB_PID" 2>/dev/null' EXIT
  # Give Xvfb a moment to come up.
  sleep 2

  TEST_ARGS=()
  while IFS= read -r t; do
    [ -z "$t" ] && continue
    # ids are "ClassName methodName" (space-separated); gradle --tests wants "ClassName.methodName".
    TEST_ARGS+=(--tests "${t% *}.${t##* }")
  done < "$TEST_IDS_FILE"

  ./gradlew --no-daemon --offline :core-tests:test "${TEST_ARGS[@]}"
  GRADLE_STATUS=$?

  mkdir -p "$(dirname "$JUNIT_OUT")"

  shopt -s nullglob
  xml_files=(core-tests/build/test-results/test/TEST-*.xml)
  shopt -u nullglob

  if [ "${#xml_files[@]}" -eq 0 ]; then
    cat > "$JUNIT_OUT" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="no-tests-ran" tests="1" failures="1" errors="0">
    <testcase classname="test_cmd" name="gradle_produced_no_junit_xml">
      <failure message="gradle exited $GRADLE_STATUS and produced no JUnit XML reports"/>
    </testcase>
  </testsuite>
</testsuites>
EOF
  else
    python3 - "$JUNIT_OUT" "${xml_files[@]}" <<'PYEOF'
import sys
import xml.etree.ElementTree as ET

out_path = sys.argv[1]
xml_files = sys.argv[2:]

root = ET.Element("testsuites")
for f in xml_files:
    try:
        suite = ET.parse(f).getroot()
    except Exception as exc:
        err = ET.SubElement(root, "testsuite", name=f, tests="1", failures="0", errors="1")
        case = ET.SubElement(err, "testcase", classname="test_cmd", name="parse_" + f)
        ET.SubElement(case, "error", message=str(exc))
        continue
    root.append(suite)

ET.ElementTree(root).write(out_path, encoding="UTF-8", xml_declaration=True)
PYEOF
  fi

  exit "$GRADLE_STATUS"
}
# Directories holding the repo's test plumbing (configs, helpers) that must also be restored so a
# candidate cannot replace the harness. Space-separated, relative to /app; '' if none.
PROTECTED_DIRS='core-tests'
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
