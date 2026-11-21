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
  # patch does not change what needs restoring). Only the integration test project and what it
  # references (Content.Client, Content.Server, Content.Shared, Content.Tests and the engine)
  # are built -- the rest of the solution (benchmarks, map renderer, packaging, linters, tools)
  # plays no part in the tests. -m lets MSBuild use multiple processes; this stays on top of
  # the image's own cached build rather than a from-scratch compile.
  dotnet build Content.IntegrationTests/Content.IntegrationTests.csproj --configuration DebugOpt --no-restore /m

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

# Capture the agent's submission BEFORE anything below mutates /app -- this is the last
# moment the tree is base + agent work; the restore loop and test.patch come next.
#
# A THROWAWAY INDEX, never /app/.git/index: `git add` against the real one would leave paths
# staged and change how the `git checkout harbor_base --` and `git clean` below behave.
#
# TRACKED EDITS + A SOURCE WHITELIST, not `add -A` with a blacklist. The image builds the .NET
# solution in-tree AFTER the harbor_base commit (environment/Dockerfile), so build output sits in
# the working tree as untracked files. A bare `add -A` risks sweeping up generated output along
# with the agent's work. Inverting it -- stage tracked modifications, then add only untracked
# files that LOOK like source -- keeps the agent's work and drops generated output by default.
_SUB=/logs/verifier/submission.patch
_SUBIDX=/tmp/.submission_index
_SUBSRC=('*.c' '*.cc' '*.cpp' '*.cxx' '*.h' '*.hh' '*.hpp' '*.hxx' '*.inl' '*.m' '*.mm'
         '*.py' '*.rb' '*.go' '*.rs' '*.java' '*.js' '*.ts' '*.tsx' '*.cs' '*.kt' '*.swift')
rm -f "$_SUBIDX"
# Seed the throwaway index from a COPY of the real one (harbor_base plus anything the agent
# staged): it carries git's cached file stats, so `add -u` below only re-hashes files that
# actually changed. A bare `read-tree harbor_base` has no stats and makes `add -u` re-hash every
# tracked file in this large repo (minutes per run). The real index itself is never written.
if ! cp /app/.git/index "$_SUBIDX" 2>>"$STDERR_LOG"; then
  GIT_INDEX_FILE="$_SUBIDX" git -C /app read-tree harbor_base 2>>"$STDERR_LOG" || true
fi
GIT_INDEX_FILE="$_SUBIDX" git -C /app add -u 2>>"$STDERR_LOG" || true
# Enumerate before adding: `git add` aborts and stages NOTHING if any one pathspec matches
# no file, which silently drops the agent's new files on most tasks.
# Generated-output dirs are dropped from the UNTRACKED scan only. A project that keeps real
# source under lib/ is unaffected: those files are tracked at harbor_base, so `add -u` above
# already has them. This drops only files CREATED under a build dir during the run -- which,
# left in, break replay: they are recorded as new-file hunks and a fresh container from the
# same image already has them, so `git apply` fails with "already exists in working directory".
mapfile -t _SUBNEW < <(git -C /app ls-files --others --exclude-standard \
  -- "${_SUBSRC[@]}" ':(exclude)lib/' ':(exclude)build/' ':(exclude).deps/' 2>/dev/null)
if [ "${#_SUBNEW[@]}" -gt 0 ]; then
  GIT_INDEX_FILE="$_SUBIDX" git -C /app add -- "${_SUBNEW[@]}" 2>>"$STDERR_LOG" || true
fi
GIT_INDEX_FILE="$_SUBIDX" git -C /app diff --binary --cached harbor_base \
  > "$_SUB" 2>>"$STDERR_LOG" || true
rm -f "$_SUBIDX"

# WHAT THE WHITELIST DROPPED, listed rather than silently discarded. The split above captures
# every change to a TRACKED file (any extension, deletions included) but only NEW files that
# look like source -- so an agent adding config.yml, a .cmake module or an extensionless script
# loses it, and the patch still looks clean. That is the failure this manifest exists to expose.
#
# NEWEST FIRST, which is the useful ordering and not a cosmetic one: build output and image
# assets are created before the agent phase starts, so anything the agent made sorts to the top.
# Build artifacts are excluded by the same rules as the capture, to keep the list readable.
#
# If something here belongs in the submission, widen _SUBSRC. Do not reach for `add -A`.
_SUBSKIP=/logs/verifier/submission-skipped.txt
_SUBCAP=/tmp/.submission_captured
if [ "${#_SUBNEW[@]}" -gt 0 ]; then printf '%s\n' "${_SUBNEW[@]}" > "$_SUBCAP"; else : > "$_SUBCAP"; fi
_SUBSKIPN=$(git -C /app ls-files --others --exclude-standard -- . \
    ':(exclude)lib/' ':(exclude)build/' ':(exclude).deps/' \
    ':(exclude)*.o' ':(exclude)*.d' ':(exclude)*.a' ':(exclude)*.lo' ':(exclude)*.la' \
    ':(exclude)*.so' ':(exclude)*.so.*' ':(exclude)*.gch' ':(exclude)*.pyc' 2>/dev/null \
  | grep -vxF -f "$_SUBCAP" 2>/dev/null | wc -l)
{ echo "# Untracked files NOT captured into submission.patch, newest first."
  echo "# Anything the agent created sorts above build output, which predates the agent phase."
  echo "# total: ${_SUBSKIPN}  (showing at most 40)"
  git -C /app ls-files --others --exclude-standard -- . \
      ':(exclude)lib/' ':(exclude)build/' ':(exclude).deps/' \
      ':(exclude)*.o' ':(exclude)*.d' ':(exclude)*.a' ':(exclude)*.lo' ':(exclude)*.la' \
      ':(exclude)*.so' ':(exclude)*.so.*' ':(exclude)*.gch' ':(exclude)*.pyc' 2>/dev/null \
    | grep -vxF -f "$_SUBCAP" 2>/dev/null | head -200 \
    | while IFS= read -r _f; do
        printf '%s\t%s\t%s\n' "$(stat -c %Y "/app/$_f" 2>/dev/null || echo 0)" \
                              "$(stat -c %s "/app/$_f" 2>/dev/null || echo 0)" "$_f"
      done \
    | sort -rn | head -40 | awk -F'\t' '{printf "%s\t%s\t%s\n",$1,$2,$3}'
} > "$_SUBSKIP" 2>/dev/null || true
rm -f "$_SUBCAP"

# Size guard. The whitelist is a heuristic, so a task laying out source unusually could still
# produce something enormous. Cap it and leave a diagnosable stub: a truncated capture is
# recoverable, a full disk is not.
_SUBSZ=$(wc -c < "$_SUB" 2>/dev/null || echo 0)
if [ "$_SUBSZ" -gt 5242880 ]; then
  { echo "SUBMISSION CAPTURE SUPPRESSED: ${_SUBSZ} bytes exceeds the 5MB cap."
    echo "Directories contributing to the discarded patch:"
    grep -a "^diff --git" "$_SUB" | sed 's#^diff --git a/##; s# b/.*##; s#/[^/]*$##' \
      | sort | uniq -c | sort -rn | head -20
  } > "$_SUB.suppressed" 2>/dev/null
  : > "$_SUB"
  echo "== submission.patch SUPPRESSED (${_SUBSZ} bytes > 5MB cap) ==" | tee -a "$STDOUT_LOG"
else
  echo "== captured submission.patch (${_SUBSZ} bytes, $(grep -ac '^diff --git' "$_SUB" 2>/dev/null || echo 0) files) ==" \
    | tee -a "$STDOUT_LOG"
fi


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

python3 /tests/verifier.py --rubric "${RUBRIC:-}" 2>>"$STDERR_LOG" | tee -a "$STDOUT_LOG"

echo "reward=$(cat /logs/verifier/reward.txt 2>/dev/null)" | tee -a "$STDOUT_LOG"
