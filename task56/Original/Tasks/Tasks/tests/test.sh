#!/usr/bin/env bash
# Behavioral verifier for carbon-design-system__carbon-21854-mm.
# Applies the harness test additions, rebuilds @carbon/web-components against
# the currently checked-out source, runs the real Mocha suite through
# @web/test-runner in headless Chromium, and computes the reward from the
# reported per-test results. It never inspects source code for the fix.
set -uo pipefail

mkdir -p /logs/verifier
STDOUT_LOG=/logs/verifier/test-stdout.txt
STDERR_LOG=/logs/verifier/test-stderr.txt
: > "$STDOUT_LOG"
: > "$STDERR_LOG"

ensure_reward() {
  [ -f /logs/verifier/reward.txt ] || echo 0 > /logs/verifier/reward.txt
}
trap ensure_reward EXIT

cd /app || {
  echo "no /app" | tee -a "$STDERR_LOG"
  exit 1
}

# Restore test paths from harbor_base before applying the harness patch so
# candidate edits to tests cannot affect scoring. Source changes are preserved.
for _p in $(grep '^+++ b/' /tests/test.patch | sed 's#^+++ b/##'); do
  git checkout harbor_base -- "$_p" 2>/dev/null \
    || rm -f "/app/$_p" 2>/dev/null \
    || true
done

git clean -fdq -- \
  $(grep '^+++ b/' /tests/test.patch | sed 's#^+++ b/##' | xargs -r dirname | sort -u) \
  2>/dev/null || true

echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply --binary /tests/test.patch 2>>"$STDERR_LOG" \
  || git apply /tests/test.patch 2>>"$STDERR_LOG" \
  || patch -p1 -i /tests/test.patch 2>>"$STDERR_LOG" \
  || {
    echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"
    exit 1
  }

echo "== creating harness-only test-runner config ==" | tee -a "$STDOUT_LOG"

cat > /app/packages/web-components/wtr.harbor.config.mjs <<'EOF'
import fs from 'fs';
import path from 'path';
import base from './web-test-runner.config.mjs';

function flatten(suite, parents, out) {
  const label = suite.name ? [...parents, suite.name] : parents;

  for (const test of suite.tests || []) {
    out.push({
      name: [...label, test.name].join(' > '),
      passed: !!test.passed,
      skipped: !!test.skipped,
    });
  }

  for (const child of suite.suites || []) {
    flatten(child, label, out);
  }
}

function harborJsonReporter(outputPath) {
  return {
    onTestRunFinished({ sessions }) {
      const flat = [];

      for (const session of sessions) {
        if (session.testResults) {
          flatten(session.testResults, [], flat);
        }
      }

      const results = {};

      for (const result of flat) {
        results[result.name] = result.skipped
          ? 'skip'
          : result.passed
            ? 'pass'
            : 'fail';
      }

      fs.mkdirSync(path.dirname(outputPath), { recursive: true });
      fs.writeFileSync(outputPath, JSON.stringify(results, null, 2));
    },
  };
}

export default {
  ...base,
  files: [
    'src/components/content-switcher/__tests__/*.js',
    'src/components/tabs/__tests__/*.js',
  ],
  coverage: false,
  reporters: [harborJsonReporter('/logs/verifier/results.json')],
};
EOF

echo "== rebuilding @carbon/web-components against current source ==" | tee -a "$STDOUT_LOG"
yarn lerna run build --scope='@carbon/web-components' \
  >>"$STDOUT_LOG" 2>>"$STDERR_LOG"

BUILD_EXIT=$?
if [ $BUILD_EXIT -ne 0 ]; then
  echo "ERROR: @carbon/web-components build failed (exit $BUILD_EXIT)" \
    | tee -a "$STDERR_LOG"
  exit 1
fi

echo "== installing headless Chromium (test-only dependency) ==" | tee -a "$STDOUT_LOG"
apt-get update >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  && apt-get install -y --no-install-recommends chromium >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || {
    echo "ERROR: could not install chromium" | tee -a "$STDERR_LOG"
    exit 1
  }
rm -rf /var/lib/apt/lists/*

export PUPPETEER_SKIP_DOWNLOAD=true
export PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

echo "== running f2p + p2p tests (Mocha, headless Chromium via Puppeteer) ==" \
  | tee -a "$STDOUT_LOG"

# F2P:
#   cds-tabs manual selection mode >
#   should move focus without changing selection or emitting
#   cds-tabs-selected during arrow-key navigation
#
# P2P:
#   Existing content-switcher behavior plus manual-mode click and keyboard
#   selection.

cd /app/packages/web-components

yarn web-test-runner \
  --config wtr.harbor.config.mjs \
  --static-logging \
  >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || echo "(tests exited non-zero; parsing report)" | tee -a "$STDOUT_LOG"

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

python3 /tests/verifier.py --rubric "${RUBRIC:-}"

echo "reward=$(cat /logs/verifier/reward.txt 2>/dev/null)" \
  | tee -a "$STDOUT_LOG"