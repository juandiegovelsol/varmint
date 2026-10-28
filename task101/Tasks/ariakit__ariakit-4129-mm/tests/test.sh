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
  npx vitest run \
    examples/toolbar-active-id-disabled/test.ts \
    examples/toolbar-active-id-stale/test.ts \
    examples/composite/test.ts \
    examples/toolbar/test.ts \
    examples/tab/test.ts \
    examples/radio/test.ts \
    examples/combobox-textarea/test.ts \
    examples/select-listbox/test.ts \
    examples/combobox-multiple-select/test.ts \
    --reporter=junit --outputFile="$JUNIT_OUT"
}
# Directories holding the repo's test plumbing (configs, helpers) that must also be restored so a
# candidate cannot replace the harness. Space-separated, relative to /app; '' if none.
PROTECTED_DIRS='examples/composite/test.ts examples/toolbar/test.ts examples/tab/test.ts examples/radio/test.ts examples/combobox-textarea/test.ts examples/select-listbox/test.ts examples/combobox-multiple-select/test.ts vitest.config.ts vitest.setup.ts package.json packages/ariakit-test'
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
# TRACKED EDITS + A SOURCE WHITELIST, not `add -A` with a blacklist. This image builds wx
# in-tree AFTER the harbor_base commit (environment/Dockerfile), so everything the build
# emits is untracked and NOT in wx's .gitignore. A bare `add -A` captured 380MB of .o/.d/.so;
# excluding those by extension still left ~120 configure-generated files (samples/*/Makefile,
# bk-deps, version-script, lib/wx/config/*, the utils/wxrc/wxrc binary) because most have no
# extension to blacklist. Inverting it -- stage tracked modifications, then add only untracked
# files that LOOK like source -- keeps the agent's work and drops generated output by default.
_SUB=/logs/verifier/submission.patch
_SUBIDX=/tmp/.submission_index
_SUBSRC=('*.c' '*.cc' '*.cpp' '*.cxx' '*.h' '*.hh' '*.hpp' '*.hxx' '*.inl' '*.m' '*.mm'
         '*.py' '*.rb' '*.go' '*.rs' '*.java' '*.js' '*.ts' '*.tsx' '*.cs' '*.kt' '*.swift')
rm -f "$_SUBIDX"
GIT_INDEX_FILE="$_SUBIDX" git -C /app read-tree harbor_base 2>>"$STDERR_LOG" || true
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

python3 /tests/verifier.py "${REPORTS[@]}" --rubric "${RUBRIC:-}"

echo "reward=$(cat /logs/verifier/reward.txt 2>/dev/null)" | tee -a "$STDOUT_LOG"
