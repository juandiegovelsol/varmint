#!/usr/bin/env bash
# Behavioral verifier for trezor__trezor-suite-30020-mm. Applies the authored test file
# (test.patch), runs the fail-to-pass + pass-to-pass jest tests of the ONE workspace under test,
# and computes a reward from the JUnit report. NEVER greps the candidate's source for the fix --
# it only runs the tests.
#
# PER-CANDIDATE KNOBS for the other trezor-suite tasks (everything else is repo-generic):
#   WORKSPACE  - the yarn workspace directory the fix under test lives in; jest's rootDir is
#                process.cwd(), so the runner MUST be started from there.
#   TEST_FILES - the workspace-relative paths of the authored test files to run.
#
# This candidate lives in suite/backup (the "suite/*" workspace family), whose jest.config.js is
# self-contained (it extends jest.config.base.swc.js by require, not by preset). `-c` is
# therefore NOT passed: jest picks up suite/backup/jest.config.js from the cwd on its own, which
# is what makes moduleNameMapper (@suite-common/*, @trezor/*, @suite/*) resolve.
set -uo pipefail

WORKSPACE=suite/backup
TEST_FILES=(src/__tests__/multiShareBackupAvailability.test.tsx)

mkdir -p /logs/verifier
STDOUT_LOG=/logs/verifier/test-stdout.txt
STDERR_LOG=/logs/verifier/test-stderr.txt
REPORT=/logs/verifier/report.xml
: > "$STDOUT_LOG"; : > "$STDERR_LOG"

ensure_reward() { [ -f /logs/verifier/reward.txt ] || echo 0 > /logs/verifier/reward.txt; }
trap ensure_reward EXIT

cd /app || { echo "no /app" | tee -a "$STDERR_LOG"; exit 1; }

# A git process that was killed mid-write (the container is memory-capped and the agent may have
# been running git when its turn ended) leaves /app/.git/index.lock behind, and EVERY later
# `git checkout` then fails with rc 128 while printing to stderr only -- i.e. the resets below
# would silently do nothing and the run would be scored against a tampered tree. The verifier
# phase owns the repository exclusively, so clearing a stale lock here is safe.
rm -f /app/.git/index.lock 2>/dev/null || true

# Robustness + idempotency: restore EVERY path test.patch touches to its pristine base state
# BEFORE applying, so (a) agent edits to the tests can't change scoring and (b) re-applying the
# patch on a second run stays idempotent. Paths are read from the `diff --git a/... b/...`
# headers (present for text, binary, renamed and deleted entries) -- not `+++ b/`, which some of
# those entry types omit.
_patch_paths=$(
  { sed -n 's#^diff --git a/\(.*\) b/.*#\1#p' /tests/test.patch
    sed -n 's#^diff --git a/.* b/\(.*\)#\1#p' /tests/test.patch
  } | sort -u )
for _p in $_patch_paths; do
  git -C /app checkout harbor_base -- "$_p" 2>/dev/null || rm -f "/app/$_p" 2>/dev/null || true
done
# `git clean` is scoped to the DIRECTORIES the patch itself owns and nothing else. Never run a
# bare `git clean -fdq -- .` here: the patch path deliberately lives inside a dedicated
# `__tests__/` sub-directory, because a repo-root dirname ('.') would wipe /app/.harbor_assets
# (the task's own bug screenshots) and any NEW file a legitimate fix created.
git -C /app clean -fdq -- $(printf '%s\n' $_patch_paths | xargs -r -n1 dirname | sort -u) 2>/dev/null || true

# Tamper targets: the jest plumbing this suite runs on, plus the shared test-harness pieces this
# workspace's jest.config.js pulls in through `roots`, and the repo's own intl test provider other
# suites render through. A candidate has no legitimate reason to touch any of these, and rewriting
# one (adding `testPathIgnorePatterns`, neutering a setup file, or making the intl provider return
# a constant) would defeat scoring. suite-common/message-system/files is the GENERATED, force-added
# config.v1 artefact every suite/* and packages/suite jest suite imports at module load; deleting
# it breaks the runner outright.
#
# The candidate's own SOURCE tree -- suite/backup/src (INCLUDING index.ts, a legitimate
# alternative-fix location: it is the workspace's own export barrel, not test infra) -- is
# deliberately NOT reset: that is where a fix lives.
#
# The reset is a PER-PATH loop on purpose: `git checkout harbor_base -- a b c` is all-or-nothing,
# so ONE path that does not exist at this base commit would silently restore NOTHING at all.
for _t in package.json jest.config.base.js jest.config.base.swc.js jest.config.swc-transform.js \
          suite-common/test-utils suite-common/tx-simulation/src/jestSetup.ts \
          suite-common/message-system/files \
          suite/intl/src/IntlProviderForTests.tsx \
          "$WORKSPACE/jest.config.js" "$WORKSPACE/jest.setup.js" \
          "$WORKSPACE/package.json" "$WORKSPACE/__mocks__"; do
  git -C /app checkout harbor_base -- "$_t" 2>/dev/null || true
done

echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply --binary /tests/test.patch 2>>"$STDERR_LOG" \
  || git apply /tests/test.patch 2>>"$STDERR_LOG" \
  || patch -p1 -i /tests/test.patch 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }

# The run is OFFLINE -- install NOTHING here. The whole yarn workspace set (jest, @swc/jest,
# @testing-library/react, @testing-library/jest-dom, ...) was baked in at BUILD time by
# environment/Dockerfile, and jest-junit lives in the isolated /opt/test-deps prefix that same
# Dockerfile created.

# JUnit identifiers are "<classname> > <name>". These templates make
#   classname = the test file path as jest reports it (workspace-relative)
#   name      = the full ' > '-joined describe/it chain
# which is the shape tests/verifier.py + tests/config.json expect (confirmed empirically against
# a real report.xml produced by this very command).
export JEST_JUNIT_OUTPUT_FILE="$REPORT"
export JEST_JUNIT_CLASSNAME="{filepath}"
export JEST_JUNIT_TITLE="{classname} > {title}"
export JEST_JUNIT_ANCESTOR_SEPARATOR=" > "
export JEST_JUNIT_SUITE_NAME="{filepath}"
export JEST_JUNIT_ADD_FILE_ATTRIBUTE=true

run_suite() {
  rm -f "$REPORT"
  ( cd "/app/$WORKSPACE" \
    && node /app/node_modules/.bin/jest \
         --ci --colors=false --coverage=false --runTestsByPath "${TEST_FILES[@]}" \
         --reporters=default --reporters=/opt/test-deps/node_modules/jest-junit \
  ) >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
    || echo "(tests exited non-zero; parsing report)" | tee -a "$STDOUT_LOG"
}

# A runner-level crash (this VM has a global kernel OOM killer that reaps whatever it likes) can
# leave a report with NO <testcase> elements at all, which the verifier then reads as "every
# scored id is missing" -- a legitimate-looking 0.0. Retry ONCE, and ONLY when the report has no
# testcases; never retry on test FAILURES, which would mask genuine red.
report_has_testcases() {
  [ -s "$REPORT" ] && grep -q '<testcase' "$REPORT"
}

echo "== running f2p + p2p tests (jest, JUnit report) ==" | tee -a "$STDOUT_LOG"
run_suite
if ! report_has_testcases; then
  echo "== JUnit report contains no testcase; runner crashed -- retrying once ==" | tee -a "$STDOUT_LOG"
  run_suite
fi

echo "== computing reward ==" | tee -a "$STDOUT_LOG"
# Rubric judge. This task ships NO rubric layer -- its behavioral tests fully cover the fix, so
# there is nothing a code-reading judge could add that the f2p/p2p suite does not already gate.
# The guarded block below is kept verbatim anyway so ONE test.sh serves both shapes: with no
# rubrics.json on disk the guard is false, RUBRIC stays empty, and verifier.py records
# rubric_passed = -1 ("not graded"), which is the correct record. The `|| echo ""` is
# load-bearing: the judge must never be able to fail the run.
RUBRIC=""
if [ -f /tests/rubrics.json ] && [ -f /tests/judge.py ]; then
  RUBRIC=$(python3 /tests/judge.py --rubrics /tests/rubrics.json --repo /app \
             2>/logs/verifier/judge.log || echo "")
  echo "Rubric verdict: ${RUBRIC:-pending (judge request written; rescore after grading)}"
fi

python3 /tests/verifier.py --rubric "$RUBRIC" 2>>"$STDERR_LOG" | tee -a "$STDOUT_LOG"
echo "reward=$(cat /logs/verifier/reward.txt 2>/dev/null)" | tee -a "$STDOUT_LOG"
