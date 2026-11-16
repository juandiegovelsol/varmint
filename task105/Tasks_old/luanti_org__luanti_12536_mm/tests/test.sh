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
  # The image already has every base-commit object file compiled; this only
  # needs to pick up the new test_content_mapblock.cpp (added by test.patch)
  # and relink. CMake's Ninja generator reruns cmake's own configure step
  # automatically when it notices src/unittest/CMakeLists.txt changed.
  cmake --build /app/build --parallel 2 >&2

  LOG="$(mktemp)"
  set +e
  /app/bin/minetest --run-unittests > "$LOG" 2>&1
  RC=$?
  set -e
  echo "---- test binary output (exit $RC) ----" >&2
  cat "$LOG" >&2

  # Luanti's legacy TestBase/TEST() framework only prints to stdout
  # ("======== Testing module X" / "[PASS|FAIL] name - Nms"); convert that
  # log into a JUnit report.
  python3 - "$LOG" "$JUNIT_OUT" <<'PY'
import re
import sys
import xml.etree.ElementTree as ET

MODULE_RE = re.compile(r"^======== Testing module (\S+)")
TEST_RE = re.compile(r"^\[(PASS|FAIL)\] (\S+) - (\d+)ms$")

log_path, out_path = sys.argv[1], sys.argv[2]
with open(log_path, "r", errors="replace") as fh:
    lines = fh.read().splitlines()

cur_module = "Unknown"
pending = []
cases = []  # (classname, name, status, message)
for line in lines:
    m = MODULE_RE.match(line)
    if m:
        cur_module = m.group(1)
        pending = []
        continue
    m = TEST_RE.match(line)
    if m:
        status, name, _ms = m.groups()
        msg = "\n".join(pending).strip()
        cases.append((cur_module, name, status, msg))
        pending = []
        continue
    pending.append(line)

n_fail = sum(1 for c in cases if c[2] == "FAIL")
root = ET.Element("testsuite", name="luanti-unittests", tests=str(len(cases)),
                   failures=str(n_fail), errors="0")
for classname, name, status, msg in cases:
    tc = ET.SubElement(root, "testcase", classname=classname, name=name)
    if status == "FAIL":
        failure = ET.SubElement(tc, "failure",
                                 message=(msg.splitlines() or ["assertion failed"])[0][:200])
        failure.text = msg or "assertion failed"
ET.ElementTree(root).write(out_path, encoding="unicode", xml_declaration=True)
print(f"wrote {len(cases)} testcase(s), {n_fail} failing, to {out_path}", file=sys.stderr)
PY
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
