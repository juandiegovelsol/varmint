#!/usr/bin/env bash
# Behavioral verifier for Textualize__textual-5099-mm.
# Applies the synthetic test file (tests/test_scroll_frame_updates.py), runs the
# f2p + p2p tests and computes a reward from the JUnit XML report. NEVER greps source
# files for the fix — it runs the tests. No snapshot/SVG baseline is involved, so there
# is nothing an agent can regenerate.
set -uo pipefail

mkdir -p /logs/verifier
STDOUT_LOG=/logs/verifier/test-stdout.txt
STDERR_LOG=/logs/verifier/test-stderr.txt
REPORT=/logs/verifier/report.xml

: > "$STDOUT_LOG"
: > "$STDERR_LOG"

ensure_reward() { [ -f /logs/verifier/reward.txt ] || echo 0 > /logs/verifier/reward.txt; }
trap ensure_reward EXIT

cd /app || { echo "no /app" | tee -a "$STDERR_LOG"; exit 1; }

# ── Robustness + idempotency ──────────────────────────────────────────────────
# Restore EVERY path test.patch touches to the pristine harbor_base state BEFORE applying,
# so (a) agent edits to test files cannot affect scoring and (b) the apply stays idempotent
# on re-runs. Paths are read from `diff --git a/... b/...` headers, which are present for all
# entry types (text, binary, renamed, deleted) unlike `+++ b/`.
_patch_paths=$(
  { sed -n 's#^diff --git a/\(.*\) b/.*#\1#p' /tests/test.patch
    sed -n 's#^diff --git a/.* b/\(.*\)#\1#p' /tests/test.patch
  } | sort -u
)
for _p in $_patch_paths; do
  git -C /app checkout harbor_base -- "$_p" 2>/dev/null \
    || rm -f "/app/$_p" 2>/dev/null \
    || true
done
git -C /app clean -fdq -- $(printf '%s\n' $_patch_paths | xargs -r -n1 dirname | sort -u) 2>/dev/null || true

echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply --binary /tests/test.patch 2>>"$STDERR_LOG" \
  || git apply /tests/test.patch 2>>"$STDERR_LOG" \
  || patch -p1 -i /tests/test.patch 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }

# ── Test-only deps ────────────────────────────────────────────────────────────
# pytest + pytest-asyncio + pytest-textual-snapshot are installed HERE, at verify time,
# not baked into environment/Dockerfile — [verifier] network_mode is "public" for exactly
# this purpose. The synthetic test file imports only `textual.app`, `textual.containers`,
# `textual.geometry` and `textual.widgets` (plus `rich.control`); the tests are `async def`
# and rely on the repo's own `asyncio_mode = "auto"` in pyproject.toml, so pytest-asyncio
# collects them with no marker.
echo "== installing pinned test-only deps ==" | tee -a "$STDOUT_LOG"
pip install -q \
  pytest==8.4.2 \
  pytest-asyncio==1.4.0 \
  pytest-textual-snapshot==1.1.0 \
  >>"$STDOUT_LOG" 2>>"$STDERR_LOG"
python3 -c "import pytest; print('pytest', pytest.__version__)" | tee -a "$STDOUT_LOG"
python3 -c "import pytest_asyncio; print('pytest-asyncio', pytest_asyncio.__version__)" | tee -a "$STDOUT_LOG"

# ── Run f2p + p2p tests ───────────────────────────────────────────────────────
# Only the synthetic file is run; it contains every f2p and p2p test.
# `-p no:cacheprovider` keeps /app free of .pytest_cache.
echo "== running f2p + p2p tests ==" | tee -a "$STDOUT_LOG"
python3 -m pytest \
  "tests/test_scroll_frame_updates.py" \
  -p no:cacheprovider -q --junitxml="$REPORT" \
  >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || echo "(tests exited non-zero; parsing report)" | tee -a "$STDOUT_LOG"

# ── Compute reward ────────────────────────────────────────────────────────────
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

python3 /tests/verifier.py "${REPORT[@]}" --rubric "${RUBRIC:-}"

echo "reward=$(cat /logs/verifier/reward.txt 2>/dev/null)" | tee -a "$STDOUT_LOG"
