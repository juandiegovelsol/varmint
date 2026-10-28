#!/usr/bin/env bash
# Behavioral verifier for OpenCTI-Platform__opencti-16540-mm.
#
# Applies the synthetic test.patch (a vitest + @testing-library/react jsdom spec under
# opencti-platform/opencti-front/harbor_tests/ -- the repo has no test for the draft overview at
# base_commit), runs it, and computes a reward from the vitest JUnit report.
#
# NEVER greps source for the fix: it renders the REAL DraftRoot page (the draft overview, fed a
# draft fixture across the relay boundary) and the REAL ConnectorWorks list (the connectors
# screen), both of which render the REAL ConnectorWorkLine through the REAL Label / TaskStatus /
# Tag components. Each work line is read back from the DOM as {label, value} pairs; the state
# field is located by its VALUE (the work state on display) and the assertion is made on that
# field's LABEL, so what is scored is the mapping "call site -> wording of the state field", not
# a string copied out of the fix. The set of work states is read live from the GraphQL schema.
set -uo pipefail

APP="${HARBOR_APP_DIR:-/app}"
TESTS="${HARBOR_TESTS_DIR:-/tests}"
LOGS="${HARBOR_LOGS_DIR:-/logs/verifier}"
FRONT="$APP/opencti-platform/opencti-front"

mkdir -p "$LOGS"
STDOUT_LOG="$LOGS/test-stdout.txt"
STDERR_LOG="$LOGS/test-stderr.txt"
REPORT="$LOGS/report.xml"          # keep in sync with verifier.py
: > "$STDOUT_LOG"; : > "$STDERR_LOG"

ensure_reward() { [ -f "$LOGS/reward.txt" ] || echo 0 > "$LOGS/reward.txt"; }
trap ensure_reward EXIT

cd "$APP" || { echo "no $APP" | tee -a "$STDERR_LOG"; exit 1; }

# Robustness + idempotency: restore EVERY path test.patch touches to its pristine base state
# BEFORE applying, so (a) agent edits to the test files cannot change scoring and (b) the apply
# stays idempotent across re-runs. Paths are read from the `diff --git a/... b/...` headers
# (present even for new files), not from `+++ b/`. Every path this patch adds is a NEW file, so
# `git checkout harbor_base -- <p>` fails and the fallback `rm -f` is what actually cleans up.
#
# The whole harbor_tests/ directory is additionally removed, because 100% of its contents come
# from this patch: that also disposes of any file an agent may have PLANTED there (a fake,
# trivially passing spec would otherwise be picked up by the config's `harbor_tests/**` include).
# The directory names are derived from the patch headers, never hard-coded, and we deliberately
# do NOT `git clean` -- that would delete /app/.harbor_assets and the agent's own new source files.
_patch_paths=$(
  { sed -n 's#^diff --git a/\(.*\) b/.*#\1#p' "$TESTS/test.patch"
    sed -n 's#^diff --git a/.* b/\(.*\)#\1#p' "$TESTS/test.patch"
  } | sort -u )
_harbor_dirs=$(printf '%s\n' $_patch_paths | sed -n 's#^\(.*/harbor_tests\)/.*#\1#p' | sort -u)
for _d in $_harbor_dirs; do
  [ -n "$_d" ] && rm -rf "$APP/$_d"
done
for _p in $_patch_paths; do
  git -C "$APP" checkout harbor_base -- "$_p" 2>/dev/null || rm -f "$APP/$_p" 2>/dev/null || true
done

echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply --binary "$TESTS/test.patch" 2>>"$STDERR_LOG" \
  || git apply "$TESTS/test.patch" 2>>"$STDERR_LOG" \
  || patch -p1 -i "$TESTS/test.patch" 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }

# Test-only deps (vitest 4.1.8, @vitejs/plugin-react, @testing-library/*, jsdom, react,
# @mui/material 6.5.0, emotion) are installed HERE, at verify time, not baked into the
# image -- keeps test-only tooling out of the environment stage. `[verifier] network_mode
# = "public"` in task.toml is what makes this reachable.
#
# Same "hide/install/restore" trick as an image-build install would use: temporarily swap
# in a minimal package.json so npm installs only the ~17 packages the spec needs instead
# of the full 1611-package workspace (which would also exceed the sandbox's disk budget).
echo "== installing test deps into $FRONT/node_modules ==" | tee -a "$STDOUT_LOG"
(
  cd "$FRONT" || exit 1
  mv package.json package.json.full
  printf '{"name":"opencti-front","private":true,"type":"module"}\n' > package.json
  npm install --no-audit --no-fund --legacy-peer-deps \
    "vitest@4.1.8" \
    "vite@8.0.16" \
    "@vitejs/plugin-react@6.0.2" \
    "vite-plugin-relay@2.1.0" \
    "@testing-library/react@16.3.2" \
    "@testing-library/jest-dom@6.9.1" \
    "@testing-library/dom@10.4.1" \
    "@testing-library/user-event@14.6.1" \
    "jsdom@29.1.1" \
    "react@19.2.7" \
    "react-dom@19.2.7" \
    "@types/react@19.2.17" \
    "@types/react-dom@19.2.3" \
    "@mui/material@6.5.0" \
    "@emotion/react@11.14.0" \
    "@emotion/styled@11.14.0" \
    "@mui/system@6.5.0"
  rc=$?
  mv package.json.full package.json
  rm -f package-lock.json
  exit $rc
) >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || { echo "ERROR: test dep install failed" | tee -a "$STDERR_LOG"; exit 1; }

echo "== running f2p + p2p tests (vitest, jsdom) ==" | tee -a "$STDOUT_LOG"
# --config harbor_tests/vitest.config.mts is essential: the project's own vite.config.ts pulls in
# a plugin stack that is not installed in the slim verifier image. Our config sets root to
# opencti-front, restricts `include` to harbor_tests/**, maps @components/* to
# src/private/components/* the way the app's tsconfig does, and swaps offline-impossible LEAF
# modules for stand-ins (never ConnectorWorkLine, DraftRoot, ConnectorWorks, Label or TaskStatus).
# vitest exits non-zero when tests fail, which is EXPECTED on the base run; the JUnit report is
# still written and verifier.py parses it for partial results.
cd "$FRONT" || { echo "no $FRONT" | tee -a "$STDERR_LOG"; exit 1; }
./node_modules/.bin/vitest run \
  --config harbor_tests/vitest.config.mts \
  --reporter=junit \
  --outputFile="$REPORT" \
  >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || echo "(vitest exited non-zero; parsing report for partial results)" | tee -a "$STDOUT_LOG"

cd "$APP"
echo "== computing reward ==" | tee -a "$STDOUT_LOG"
# Rubric judge. This task ships NO rubric (Mode B), so the guard below is false and the block
# no-ops: verifier.py receives an empty --rubric and records rubric_passed = -1 ("not graded"),
# which never lowers the reward. The plumbing stays wired so the shape matches the rubric tasks
# in the corpus -- if a rubrics.json is ever added, judge.py alongside it is all that is needed.
# The `|| echo ""` is load-bearing: the judge must never be able to fail the run.
# The guard uses the literal in-container paths (rather than $TESTS/$LOGS) to match the
# corpus-wide golden block byte-for-byte; harbor always mounts these at /tests and
# /logs/verifier, and in Mode B the block no-ops regardless.
RUBRIC=""
if [ -f /tests/rubrics.json ]; then
  RUBRIC=$(python3 /tests/judge.py --rubrics /tests/rubrics.json --repo /app \
             2>/logs/verifier/judge.log || echo "")
  echo "Rubric verdict: ${RUBRIC:-pending (judge request written; rescore after grading)}" | tee -a "$STDOUT_LOG"
fi

python3 "$TESTS/verifier.py" --rubric "${RUBRIC:-}" 2>>"$STDERR_LOG" | tee -a "$STDOUT_LOG"
echo "reward=$(cat "$LOGS/reward.txt" 2>/dev/null)" | tee -a "$STDOUT_LOG"
