#!/usr/bin/env bash
# Behavioral verifier for carbon-design-system__carbon-22307-mm.
#
# Runs four jest test files from one JUnit report:
#   duration-test.js          f2p  - the new duration format (upstream PR tests +
#                                    a synthetic index-wiring check)
#   defaults-test.js          f2p  - documented conventions of the existing
#                                    formatters: default-option output and locale
#                                    pass-through (all expectations derived from
#                                    Intl at runtime, never hardcoded)
#   overflow-behavior-test.js f2p  - the overflow handler's contract when a
#                                    container overflows
#   relative-test.js          p2p  - pre-existing, untouched regression pool
#   absolute-test.js          p2p  - pre-existing, untouched regression pool
# NEVER greps source for the fix - it runs the tests.
set -uo pipefail
mkdir -p /logs/verifier
STDOUT_LOG=/logs/verifier/test-stdout.txt
STDERR_LOG=/logs/verifier/test-stderr.txt
REPORT=/logs/verifier/report.xml
: > "$STDOUT_LOG"; : > "$STDERR_LOG"

ensure_reward() { [ -f /logs/verifier/reward.txt ] || echo 0 > /logs/verifier/reward.txt; }
trap ensure_reward EXIT

cd /app || { echo "no /app" | tee -a "$STDERR_LOG"; exit 1; }

# ── Step 1: restore any test paths the agent may have edited ─────────────────
# Paths come from the `diff --git` headers, not `+++ b/`: the latter is absent
# for binary, renamed and deleted entries. New-file paths (absent from
# harbor_base) fall through to `rm -f`, so vandalized copies are removed before
# test.patch recreates them.
echo "== restoring test files to harbor_base ==" | tee -a "$STDOUT_LOG"
_patch_paths=$(
  { sed -n 's#^diff --git a/\(.*\) b/.*#\1#p' /tests/test.patch
    sed -n 's#^diff --git a/.* b/\(.*\)#\1#p' /tests/test.patch
  } | sort -u )
for _p in $_patch_paths; do
  git -C /app checkout harbor_base -- "$_p" 2>/dev/null || rm -f "/app/$_p" 2>/dev/null || true
  rm -f "/app/$_p.orig" "/app/$_p.rej" 2>/dev/null || true
done
# The two p2p pools are pre-existing files NOT in test.patch, so they are
# restored explicitly - otherwise an agent could edit them to force their
# regression tests to trivially pass regardless of the real fix.
for _p in packages/utilities/src/dateTimeFormat/relative-test.js \
          packages/utilities/src/dateTimeFormat/absolute-test.js; do
  git -C /app checkout harbor_base -- "$_p" 2>/dev/null || true
  rm -f "/app/$_p.orig" "/app/$_p.rej" 2>/dev/null || true
done

echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply --binary /tests/test.patch 2>>"$STDERR_LOG" \
  || git apply /tests/test.patch 2>>"$STDERR_LOG" \
  || patch -p1 -i /tests/test.patch 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }

echo "== creating jest config ==" | tee -a "$STDOUT_LOG"
# Everything jest needs (jest, babel-jest, jest-junit, @testing-library/jest-dom,
# the babel presets) is a root devDependency of the repo itself, installed into
# the image by its normal `yarn workspaces focus` - no test-only tooling is
# fetched at verify time. moduleFileExtensions lists 'tsx' before 'ts' so an
# off-file alternative fix that shadows a .ts module with a .tsx sibling
# resolves correctly.
cat > /tmp/jest-verifier.config.cjs << 'JESTEOF'
module.exports = {
  rootDir: '/app',
  testEnvironment: 'jsdom',
  setupFilesAfterEnv: ['/app/node_modules/@testing-library/jest-dom'],
  testMatch: [
    '<rootDir>/packages/utilities/src/dateTimeFormat/duration-test.js',
    '<rootDir>/packages/utilities/src/dateTimeFormat/defaults-test.js',
    '<rootDir>/packages/utilities/src/dateTimeFormat/relative-test.js',
    '<rootDir>/packages/utilities/src/dateTimeFormat/absolute-test.js',
    '<rootDir>/packages/utilities/src/overflowHandler/overflow-behavior-test.js',
  ],
  transform: {
    '^.+\\.(mjs|cjs|js|jsx|ts|tsx)$': ['babel-jest', {
      presets: [
        ['@babel/preset-env', { targets: { node: 'current' } }],
        '@babel/preset-typescript',
      ],
      plugins: [
        '@babel/plugin-proposal-export-default-from',
        '@babel/plugin-transform-class-properties',
        '@babel/plugin-transform-export-namespace-from',
      ],
    }],
  },
  reporters: ['default', 'jest-junit'],
  moduleFileExtensions: ['tsx', 'ts', 'js', 'jsx', 'json', 'node'],
  transformIgnorePatterns: [
    '/node_modules/(?!lodash-es|nanoid|chalk)',
  ],
};
JESTEOF

echo "== running f2p + p2p tests ==" | tee -a "$STDOUT_LOG"
JEST_JUNIT_OUTPUT_DIR=/logs/verifier \
JEST_JUNIT_OUTPUT_NAME=report.xml \
BABEL_ENV=test \
  ./node_modules/.bin/jest \
  --config /tmp/jest-verifier.config.cjs \
  --no-coverage --forceExit --runInBand \
  >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || echo "(tests exited non-zero; parsing report)" | tee -a "$STDOUT_LOG"

echo "== computing reward ==" | tee -a "$STDOUT_LOG"
# This task ships no rubric layer: every requirement is covered by behavioural
# tests, so tests/rubrics.json and tests/judge.py are both intentionally absent.
# The call below is guarded on rubrics.json rather than deleted: the wiring
# stays visible and correct, while the branch cannot fire in a bundle that
# ships no rubric file. Guarding on the rubric file (not on judge.py) makes
# adding a rubric layer later a pure addition.
RUBRIC=""
if [ -f /tests/rubrics.json ]; then
  RUBRIC=$(python3 /tests/judge.py --rubrics /tests/rubrics.json --repo /app \
             2>/logs/verifier/judge.log || echo "")
fi

# verifier.py always accepts --rubric; an empty or missing path records
# rubric_passed = -1 ("not graded"), which never withholds a reward - only an
# explicit 0 does.
python3 /tests/verifier.py --rubric "${RUBRIC:-}" 2>>"$STDERR_LOG" | tee -a "$STDOUT_LOG"
echo "reward=$(cat /logs/verifier/reward.txt 2>/dev/null)" | tee -a "$STDOUT_LOG"
