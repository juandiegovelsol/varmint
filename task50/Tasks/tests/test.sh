#!/usr/bin/env bash
# Behavioral verifier for trezor__trezor-suite-30548-mm. Applies the authored test file
# (test.patch), runs the fail-to-pass + pass-to-pass jest tests of the ONE workspace under test,
# and computes a reward from the JUnit report. NEVER greps the candidate's source for the fix --
# it only runs the tests.
#
# PER-CANDIDATE KNOBS for the other trezor-suite tasks (everything else is repo-generic):
#   WORKSPACE  - the yarn workspace directory the fix under test lives in; jest's rootDir is
#                process.cwd(), so the runner MUST be started from there.
#   TEST_FILES - the workspace-relative paths of the authored/upstream test files to run.
set -uo pipefail

WORKSPACE=packages/suite
TEST_FILES=(src/components/earn/yield/__tests__/yieldWithdrawComplete.test.tsx)

mkdir -p /logs/verifier
STDOUT_LOG=/logs/verifier/test-stdout.txt
STDERR_LOG=/logs/verifier/test-stderr.txt
REPORT=/logs/verifier/report.xml
: > "$STDOUT_LOG"; : > "$STDERR_LOG"

ensure_reward() { [ -f /logs/verifier/reward.txt ] || echo 0 > /logs/verifier/reward.txt; }
trap ensure_reward EXIT

cd /app || { echo "no /app" | tee -a "$STDERR_LOG"; exit 1; }

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
# bare `git clean -fdq -- .` here: every patch path in this corpus deliberately lives inside a
# dedicated `__tests__/` sub-directory, because a repo-root dirname ('.') would wipe
# /app/.harbor_assets (the task's own bug screenshots) and any NEW file a legitimate fix created.
git -C /app clean -fdq -- $(printf '%s\n' $_patch_paths | xargs -r -n1 dirname | sort -u) 2>/dev/null || true

# Tamper targets: the jest plumbing the suite runs on, plus the shared mock roots
# packages/suite/jest.config.js pulls in (`roots` lists suite-common/test-utils/__mocks__ and
# packages/suite/__mocks__). A candidate has no legitimate reason to touch any of these, and
# rewriting one of them (e.g. adding `testPathIgnorePatterns`, neutering jest.setup.js, or
# shadowing @trezor/components with a module mock) would defeat scoring. The workspace's own
# SOURCE tree is deliberately NOT reset -- that is the candidate's fix.
git -C /app checkout harbor_base -- \
  package.json jest.config.base.js jest.config.base.swc.js jest.config.swc-transform.js \
  suite-common/test-utils \
  "$WORKSPACE/jest.config.js" "$WORKSPACE/jest.setup.js" "$WORKSPACE/package.json" \
  "$WORKSPACE/__mocks__" 2>/dev/null || true

echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply --binary /tests/test.patch 2>>"$STDERR_LOG" \
  || git apply /tests/test.patch 2>>"$STDERR_LOG" \
  || patch -p1 -i /tests/test.patch 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }

# The whole yarn workspace set (jest, @swc/jest, @testing-library/react, ...) was baked in at
# BUILD time by environment/Dockerfile -- install NOTHING from that set here.
#
# jest-junit (the JUnit reporter jest itself doesn't ship) is different: it is test-only tooling
# needed solely for grading, so it is NOT baked into the agent-visible image. It is installed here,
# at verify time, into an isolated /opt/test-deps prefix -- never into /app/node_modules, which
# would perturb `yarn.lock` / `--immutable`. The verifier run has network access for this
# (task.toml [verifier] network_mode = "public").
mkdir -p /opt/test-deps
( cd /opt/test-deps \
  && npm init -y >/dev/null \
  && npm install --no-audit --no-fund --loglevel=error jest-junit@16.0.0 \
  && npm cache clean --force >/dev/null 2>&1 || true
) >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not install jest-junit" | tee -a "$STDERR_LOG"; exit 1; }

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
rm -f "$REPORT"

# `--coverage=false` overrides packages/suite/jest.config.js's `collectCoverage: true`; the
# instrumentation costs minutes over the whole suite src tree and produces nothing the reward
# depends on.
echo "== running f2p + p2p tests (jest, JUnit report) ==" | tee -a "$STDOUT_LOG"
( cd "/app/$WORKSPACE" \
  && node /app/node_modules/.bin/jest \
       --ci --colors=false --coverage=false --runTestsByPath "${TEST_FILES[@]}" \
       --reporters=default --reporters=/opt/test-deps/node_modules/jest-junit \
) >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || echo "(tests exited non-zero; parsing report)" | tee -a "$STDOUT_LOG"

echo "== computing reward ==" | tee -a "$STDOUT_LOG"
# Rubric judge - API backend first (EVAL_* env), falling back to a sub-agent request when
# unavailable. On a sub-agent-fallback first pass there is no verdict yet, so judge.py writes a
# judge request under /logs/verifier/judge/ and prints nothing. The `|| echo ""` is load-bearing:
# the judge must never be able to fail the run.
RUBRIC=""
if [ -f /tests/rubrics.json ]; then
  RUBRIC=$(python3 /tests/judge.py --rubrics /tests/rubrics.json --repo /app \
             2>/logs/verifier/judge.log || echo "")
  echo "Rubric verdict: ${RUBRIC:-pending (judge request written; rescore after grading)}"
fi

python3 /tests/verifier.py --rubric "${RUBRIC:-}" 2>>"$STDERR_LOG" | tee -a "$STDOUT_LOG"
echo "reward=$(cat /logs/verifier/reward.txt 2>/dev/null)" | tee -a "$STDOUT_LOG"
