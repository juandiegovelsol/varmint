#!/usr/bin/env bash
# Behavioral verifier for ivark__antimatterdimensionssourcecode-2808-mm
#
# The milestone hover tooltip on the celestial-pelle rift bar freezes at its
# first-rendered contents: both of its lines are produced by template method
# calls inside a stable scoped slot, so nothing invalidates the slot when the
# underlying (non-reactive) values advance.
#
# NEVER greps candidate source, and asserts no property/function/file name. The
# real component is mounted together with the real CustomizeableTooltip in jsdom,
# the game tick is driven by calling update() the way GameUI does, and only the
# RENDERED tooltip text is asserted across ticks — so any fix that actually makes
# the tooltip track its sources passes, whatever its shape or location.
#
# Synthetic test: repo has no test framework; jest + custom vue-script-transformer
# (uses @babel/core already in devDeps) added via test.patch for this eval only.

set -uo pipefail

mkdir -p /logs/verifier

STDOUT_LOG=/logs/verifier/test-stdout.txt
STDERR_LOG=/logs/verifier/test-stderr.txt
REPORT=/logs/verifier/jest-results.json

: > "$STDOUT_LOG"
: > "$STDERR_LOG"

ensure_reward() {
  [ -f /logs/verifier/reward.txt ] || echo 0 > /logs/verifier/reward.txt
}
trap ensure_reward EXIT

cd /app || { echo "no /app" | tee -a "$STDERR_LOG"; exit 1; }

# ── Step 1: Reset test.patch paths from harbor_base ────────────────────────────
# Extract EVERY path from diff --git headers (text, binary, renamed, deleted).
# Restore each to pristine base state so the apply is idempotent and any agent
# edits to those paths cannot influence scoring.
_patch_paths=$(
  { sed -n 's#^diff --git a/\(.*\) b/.*#\1#p' /tests/test.patch
    sed -n 's#^diff --git a/.* b/\(.*\)#\1#p' /tests/test.patch
  } | sort -u )

for _p in $_patch_paths; do
  git -C /app checkout harbor_base -- "$_p" 2>/dev/null \
    || rm -f "/app/$_p" 2>/dev/null \
    || true
done
git -C /app clean -fdq -- $(
  printf '%s\n' $_patch_paths | xargs -r -n1 dirname | sort -u
) 2>/dev/null || true

# ── Step 2: Apply test.patch ───────────────────────────────────────────────────
echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply /tests/test.patch 2>>"$STDERR_LOG" \
  || patch -p1 -i /tests/test.patch 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }

# ── Step 3: Install pinned test-only deps ─────────────────────────────────────
# Do NOT modify package.json / package-lock.json (--no-save --no-package-lock).
#
# jest@27.5.1         — test runner; bundles jest-environment-jsdom
# babel-jest@27.5.1   — transforms .js test files (ES module → CJS for Node)
# @babel/preset-env@7 — used by both babel-jest (test file) and the custom
#                       vue-script-transformer.js (component script block)
#
# @babel/core and vue-template-compiler are already in node_modules (npm ci).
# vue-jest is NOT installed here — the custom vue-script-transformer.js avoids
# the vue-jest@4/jest@27 getCacheKey API incompatibility.
echo "== installing pinned test-only deps ==" | tee -a "$STDOUT_LOG"
npm install --no-save --no-package-lock --legacy-peer-deps \
  jest@27.5.1 \
  babel-jest@27.5.1 \
  "@babel/preset-env@7.23.5" \
  >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || { echo "ERROR: npm install for test deps failed" | tee -a "$STDERR_LOG"; exit 1; }

# ── Step 4: Run the synthetic reactivity spec ──────────────────────────────────
# --json --outputFile: produce machine-readable report for verifier.py.
# jest exits non-zero on test failure; capture code, don't abort.
echo "== running f2p test ==" | tee -a "$STDOUT_LOG"
npx jest \
  --config /app/jest.config.js \
  --json \
  --outputFile "$REPORT" \
  --testPathPattern="PelleRiftBar.reactivity.spec.js" \
  --no-coverage \
  >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || echo "(jest exited non-zero; parsing report for reward)" | tee -a "$STDOUT_LOG"

echo "== computing reward ==" | tee -a "$STDOUT_LOG"
python3 /tests/verifier.py 2>>"$STDERR_LOG" | tee -a "$STDOUT_LOG"
echo "reward=$(cat /logs/verifier/reward.txt 2>/dev/null)" | tee -a "$STDOUT_LOG"
