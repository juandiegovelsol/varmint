#!/usr/bin/env bash
# Behavioural verifier for textualize__textual-5826-mm.
#
# Restores the whole test tree from the immutable harbor_base tag, applies the discriminating
# tests from test.patch, runs them, and computes a BINARY reward (1.0 only when every f2p and
# every p2p passes).
#
# NEVER greps candidate source for the fix -- it runs the tests.
#
# Two test files carry the scored tests:
#   tests/test_markup.py          -- the repository's own markup suite, extended by the upstream
#     fix with new parameter sets. Only its two implementation-neutral cases are scored as p2p
#     (an unrelated markup case, and the unbalanced-markup error path). Its remaining cases
#     compare the exact list of styled ranges, which a correct fix that describes the same
#     rendered result with a different arrangement of ranges would not reproduce, so they are
#     deliberately left unscored: they run, but they cannot cause an invalid failure.
#   tests/test_markup_nesting.py  -- the scored tests. They assert the effective style of every
#     rendered character through the public rendering API, so any implementation that paints the
#     same picture passes, whatever ranges it builds internally.
set -uo pipefail

mkdir -p /logs/verifier
STDOUT_LOG=/logs/verifier/test-stdout.txt
STDERR_LOG=/logs/verifier/test-stderr.txt
REPORT=/logs/verifier/report.xml
: > "$STDOUT_LOG"; : > "$STDERR_LOG"; rm -f "$REPORT"

# Anti-cheat: the agent runs before the verifier and shares /logs. A reward file planted there
# would survive the ensure_reward trap below (which only writes when the file is ABSENT) if the
# verifier died early, and a verdict.json planted in the judge dir wins outright over the API
# backend (judge.py resolves an existing verdict first, which is what makes a rescore
# idempotent), handing out a rubric pass with nothing graded. Clear all of it before scoring.
rm -f /logs/verifier/reward.txt /logs/verifier/reward.json
rm -rf /logs/verifier/judge

ensure_reward() { [ -f /logs/verifier/reward.txt ] || echo 0 > /logs/verifier/reward.txt; }
trap ensure_reward EXIT

cd /app || { echo "no /app" | tee -a "$STDERR_LOG"; exit 1; }

# ── Restore the ENTIRE test tree from harbor_base ────────────────────────────────────────────
# Everything under tests/ is writable by the agent, so resetting only the two files test.patch
# touches would still leave a planted tests/conftest.py able to stub out to_content or the
# rendering API for the whole run. Resetting the tree, then cleaning untracked leftovers, closes
# that at once; --noconftest below closes the same hole for a conftest planted outside tests/.
echo "== restoring tests/ from harbor_base ==" | tee -a "$STDOUT_LOG"
git -C /app checkout harbor_base -- tests/ 2>>"$STDERR_LOG" || {
    echo "ERROR: could not restore tests/ from harbor_base" | tee -a "$STDERR_LOG"; exit 1; }
git -C /app clean -fdq -- tests/ 2>/dev/null || true

# Robustness + idempotency for anything test.patch touches outside tests/ (nothing today).
# Read paths from `diff --git a/... b/...` headers, which are present for text, BINARY, renamed
# and deleted entries -- NOT from `+++ b/`, which is ABSENT for binary and renamed entries.
_patch_paths=$(
  { sed -n 's#^diff --git a/\(.*\) b/.*#\1#p' /tests/test.patch
    sed -n 's#^diff --git a/.* b/\(.*\)#\1#p' /tests/test.patch
  } | sort -u )
for _p in $_patch_paths; do
  git -C /app checkout harbor_base -- "$_p" 2>/dev/null || rm -f "/app/$_p" 2>/dev/null || true
done

echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply /tests/test.patch 2>>"$STDERR_LOG" \
  || patch -p1 -i /tests/test.patch 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }

# ── Install the test runner, at verify time and offline ──────────────────────────────────────
# The image ships no test tooling, so the agent's environment carries nothing it would not need
# to write the fix. The wheels were resolved and frozen into the image at build time, so this
# install is pinned, offline and identical on every run: no registry is contacted here, and a
# registry outage cannot turn a correct fix into a reward of 0.0.
echo "== installing pinned test runner from the offline wheel cache ==" | tee -a "$STDOUT_LOG"
python -m pip install --no-index --find-links=/opt/test-wheels --quiet pytest==8.3.4 \
  >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not install pytest from /opt/test-wheels" | tee -a "$STDERR_LOG"; exit 1; }

# ── Run the suite ────────────────────────────────────────────────────────────────────────────
# --noconftest      : neither test file needs a conftest, so none is loaded -- a planted one
#                     (at the repository root, where the base tree has none) cannot run.
# -o addopts=       : neutralises any addopts injected into the project's pytest configuration.
# -p no:cacheprovider : no .pytest_cache is written into the checkout between runs.
echo "== running markup tests ==" | tee -a "$STDOUT_LOG"
python -m pytest tests/test_markup.py tests/test_markup_nesting.py \
  --noconftest -o addopts= -p no:cacheprovider \
  --junitxml="$REPORT" --tb=short -q --no-header \
  >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || echo "(tests exited non-zero; parsing report)" | tee -a "$STDOUT_LOG"

echo "== rubric judge (graded in band when the API backend is reachable; never fatal) ==" | tee -a "$STDOUT_LOG"
RUBRIC=""
if [ -f /tests/rubrics.json ]; then
  RUBRIC=$(python3 /tests/judge.py --rubrics /tests/rubrics.json --repo /app 2>/logs/verifier/judge.log || echo "")
  echo "Rubric verdict: ${RUBRIC:-pending (judge request written; rescore after grading)}" | tee -a "$STDOUT_LOG"
fi

echo "== computing reward ==" | tee -a "$STDOUT_LOG"
python3 /tests/verifier.py --rubric "${RUBRIC:-}" 2>>"$STDERR_LOG" | tee -a "$STDOUT_LOG"
echo "reward=$(cat /logs/verifier/reward.txt 2>/dev/null)" | tee -a "$STDOUT_LOG"
