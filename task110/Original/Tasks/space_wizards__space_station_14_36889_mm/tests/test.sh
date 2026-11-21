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
  cd /app

  # Build a VSTest --filter expression that matches exactly the configured test ids (by fully
  # qualified name), OR'd together.
  FILTER=""
  while IFS= read -r id; do
    [ -z "$id" ] && continue
    clause="FullyQualifiedName=${id}"
    if [ -z "$FILTER" ]; then
      FILTER="$clause"
    else
      FILTER="${FILTER}|${clause}"
    fi
  done < "$TEST_IDS_FILE"

  WORKDIR="$(mktemp -d)"
  NUNIT_XML_DIR="$WORKDIR/nunit-xml"
  mkdir -p "$NUNIT_XML_DIR"

  # Rebuild (offline: the image already restored every NuGet package, and a source-only
  # patch does not change what needs restoring). -m lets MSBuild use multiple processes;
  # the verifier container is memory-capped, so this stays on top of the image's own
  # cached build rather than a from-scratch compile.
  dotnet build --configuration DebugOpt --no-restore /m

  # NUnit.NumberOfTestWorkers=1 overrides the assembly's [LevelOfParallelism(2)] and runs the
  # selected tests one at a time on a single dedicated worker thread, instead of on two
  # concurrent worker threads (NumberOfTestWorkers=0, which drops NUnit's threaded dispatcher
  # entirely and runs tests directly on the calling thread, turned out to be incompatible with
  # this engine's GameTest fixtures and produced a wrongly-attributed report -- a result from one
  # test landing under the other test's name -- so a single *worker thread* is used instead).
  # With only a couple of tests selected by filter (instead of the full suite), two GameTest-
  # derived tests can each spin up their own Robust server/client pair at the same time; those
  # pairs race on the engine's prototype-loading path (PrototypeManager.InstantiateKinds ->
  # KindData.Freeze) and the second server to start can intermittently hit an
  # ArgumentNullException while building its prototype dictionary. That's a pre-existing
  # concurrency bug in the engine's test-pool startup, not something either test or the fix
  # touches, so it's worked around here by serializing execution onto one worker thread.
  dotnet test --no-build --configuration DebugOpt Content.IntegrationTests/Content.IntegrationTests.csproj \
      --filter "$FILTER" \
      --logger "console;verbosity=normal" \
      -- NUnit.ConsoleOut=0 NUnit.MapWarningTo=Failed \
         NUnit.NumberOfTestWorkers=1 \
         NUnit.TestOutputXml="$(basename "$NUNIT_XML_DIR")" \
         NUnit.WorkDirectory="$WORKDIR" \
      || true   # test failures must not abort the script; we still need to emit JUnit XML

  # Convert whatever NUnit3-format XML files were produced into one JUnit-style report.
  python3 - "$NUNIT_XML_DIR" "$JUNIT_OUT" "$FILTER" <<'PY'
import sys, glob, os
import xml.etree.ElementTree as ET

nunit_dir, out_path, filt = sys.argv[1], sys.argv[2], sys.argv[3]

cases = []  # (classname, name, status, message)
for path in glob.glob(os.path.join(nunit_dir, "*.xml")):
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        continue
    for tc in root.iter("test-case"):
        classname = tc.get("classname") or ""
        name = tc.get("methodname") or tc.get("name") or ""
        fullname = tc.get("fullname") or f"{classname}.{name}"
        result = (tc.get("result") or "").lower()
        msg = ""
        failure = tc.find("failure")
        if failure is not None:
            m = failure.find("message")
            st = failure.find("stack-trace")
            msg = ((m.text or "") if m is not None else "") + "\n" + ((st.text or "") if st is not None else "")
        if result in ("passed",):
            status = "pass"
        elif result in ("skipped", "ignored", "explicit"):
            status = "skip"
        else:
            status = "fail"
        cases.append((classname, name, fullname, status, msg))

suite = ET.Element("testsuite", {"name": "Content.IntegrationTests", "tests": str(len(cases))})
for classname, name, fullname, status, msg in cases:
    # classname left empty and the full "Namespace.Class.Method" dotted id put in "name" so that
    # verifier.py's "{classname} {name}".strip() key equals config.json's f2p/p2p ids exactly.
    tc_el = ET.SubElement(suite, "testcase", {"classname": "", "name": fullname})
    if status == "fail":
        f_el = ET.SubElement(tc_el, "failure", {"message": (msg or "failed")[:500]})
        f_el.text = msg[:4000]
    elif status == "skip":
        ET.SubElement(tc_el, "skipped")

ET.ElementTree(suite).write(out_path, encoding="unicode", xml_declaration=True)
print(f"wrote {len(cases)} test-case results to {out_path}")
PY
}
# Directories holding the repo's test plumbing (configs, helpers) that must also be restored so a
# candidate cannot replace the harness. Space-separated, relative to /app; '' if none.
PROTECTED_DIRS='Content.IntegrationTests/Fixtures'
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
