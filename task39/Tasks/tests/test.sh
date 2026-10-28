#!/usr/bin/env bash
# Behavioral verifier for Textualize__textual-5436-mm.
# Applies the synthetic test file (tests/test_key_panel_tooltip_alignment.py), runs the
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
# pytest + pytest-asyncio are test-only, so they are installed HERE at verify time rather
# than baked into the image, and at EXPLICIT PINS: an unpinned install would let a future
# pytest change collection behaviour and break a task that used to score correctly.
# These two pins are the versions this task's gate was reproduced against (oracle 1.0 /
# nop 0.0). Bump them deliberately, never implicitly.
#
# This is why task.toml sets `[verifier] network_mode = "public"` — the verifier phase needs
# egress to reach the index. It runs AFTER the agent phase is over and test.sh has restored
# the test files from harbor_base, so this egress cannot help a submission cheat; the AGENT
# phase stays sealed with `network_mode = "no-network"`.
#
# The synthetic test file imports only `rich`, `textual.app`, `textual.binding`,
# `textual.containers` and `textual.widgets`; the tests are `async def` and rely on the
# repo's own `asyncio_mode = "auto"` in pyproject.toml, so pytest-asyncio collects them
# with no marker.
PYTEST_PIN='pytest==8.4.2'
PYTEST_ASYNCIO_PIN='pytest-asyncio==1.4.0'
echo "== installing pinned test-only deps ($PYTEST_PIN, $PYTEST_ASYNCIO_PIN) ==" \
  | tee -a "$STDOUT_LOG"
pip install --no-cache-dir -q "$PYTEST_PIN" "$PYTEST_ASYNCIO_PIN" \
  >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not install pinned test deps" | tee -a "$STDERR_LOG"; exit 1; }
python3 -c "import pytest; print('pytest', pytest.__version__)" | tee -a "$STDOUT_LOG"
python3 -c "import pytest_asyncio; print('pytest-asyncio', pytest_asyncio.__version__)" | tee -a "$STDOUT_LOG"

# ── Run f2p + p2p tests ───────────────────────────────────────────────────────
# Only the synthetic file is run; it contains every f2p and p2p test.
# `-p no:cacheprovider` keeps /app free of .pytest_cache.
run_suite() {
  python3 -m pytest \
    "tests/test_key_panel_tooltip_alignment.py" \
    -p no:cacheprovider -q --junitxml="$REPORT" \
    >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
    || echo "(tests exited non-zero; parsing report)" | tee -a "$STDOUT_LOG"
}

report_has_testcases() {
  python3 - "$REPORT" <<'PY'
import sys, os, xml.etree.ElementTree as ET
path = sys.argv[1]
if not os.path.exists(path):
    sys.exit(1)
try:
    tree = ET.parse(path)
except Exception:
    sys.exit(1)
sys.exit(0 if next(tree.iter('testcase'), None) is not None else 1)
PY
}

echo "== running f2p + p2p tests ==" | tee -a "$STDOUT_LOG"
run_suite

# One-shot retry ONLY when the report is missing or carries ZERO <testcase> elements —
# i.e. the runner crashed or collection aborted before any test was recorded, which would
# otherwise be scored as a false 0.0. A report full of FAILURES is a real verdict and is
# never retried.
if ! report_has_testcases; then
  echo "== JUnit report has no testcases; retrying the suite once ==" | tee -a "$STDOUT_LOG"
  rm -f "$REPORT"
  run_suite
  report_has_testcases \
    && echo "== retry produced a populated report ==" | tee -a "$STDOUT_LOG" \
    || echo "== retry still produced no testcases ==" | tee -a "$STDERR_LOG"
fi

# ── Compute reward ────────────────────────────────────────────────────────────
echo "== computing reward ==" | tee -a "$STDOUT_LOG"
# Rubric judge - SUB-AGENT backend: no API key, no network. On the first pass there is no
# verdict yet, so judge.py writes a judge request under /logs/verifier/judge/ and prints
# nothing. The `|| echo ""` is load-bearing: the judge must never be able to fail the run.
RUBRIC=""
if [ -f /tests/rubrics.json ]; then
  RUBRIC=$(python3 /tests/judge.py --rubrics /tests/rubrics.json --repo /app \
             2>/logs/verifier/judge.log || echo "")
  echo "Rubric verdict: ${RUBRIC:-pending (judge request written; rescore after grading)}"
fi

python3 /tests/verifier.py --rubric "${RUBRIC:-}" 2>>"$STDERR_LOG" | tee -a "$STDOUT_LOG"
echo "reward=$(cat /logs/verifier/reward.txt 2>/dev/null)" | tee -a "$STDOUT_LOG"
