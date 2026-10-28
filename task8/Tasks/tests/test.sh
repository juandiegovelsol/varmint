#!/usr/bin/env bash
# Behavioral verifier for textualize__textual-5550-mm. Resets test files from harbor_base,
# applies test.patch (which includes SVG baselines from the fixed rendering),
# runs f2p+p2p snap_compare tests, and computes reward. Never greps source.
set -uo pipefail
STDOUT_LOG=/logs/verifier/test-stdout.txt
STDERR_LOG=/logs/verifier/test-stderr.txt
REPORT=/logs/verifier/report.xml
mkdir -p /logs/verifier
: > "$STDOUT_LOG"; : > "$STDERR_LOG"

ensure_reward() { [ -f /logs/verifier/reward.txt ] || echo 0 > /logs/verifier/reward.txt; }
trap ensure_reward EXIT

cd /app || { echo "no /app" | tee -a "$STDERR_LOG"; exit 1; }

# Reset every path touched by test.patch to pristine harbor_base state.
# Read diff --git headers (present for ALL entry types incl. binary/renamed/deleted).
_patch_paths=$(
  { sed -n 's#^diff --git a/\(.*\) b/.*#\1#p' /tests/test.patch
     sed -n 's#^diff --git a/.* b/\(.*\)#\1#p' /tests/test.patch
  } | sort -u )
for _p in $_patch_paths; do
  git -C /app checkout harbor_base -- "$_p" 2>/dev/null || rm -f "/app/$_p" 2>/dev/null || true
done
# Restore the whole tracked test tree and the pytest configuration, then drop any
# untracked file added under tests/ (e.g. a conftest.py that neuters snap_compare).
# The submission is graded on source behavior, never on a harness it can edit.
git -C /app checkout harbor_base -- tests/ pyproject.toml 2>/dev/null || true
git -C /app clean -fdq tests/ 2>/dev/null || true

echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply --binary /tests/test.patch 2>>"$STDERR_LOG" \
  || git apply /tests/test.patch 2>>"$STDERR_LOG" \
  || patch -p1 -i /tests/test.patch 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }



echo "== installing pinned test dependencies (offline) ==" | tee -a "$STDOUT_LOG"
# Test-only tooling is staged in the image as pinned wheels but NOT installed there: an
# importable pytest / snapshot plugin would hint at how the fix is graded. Install it now,
# in the test stage only. --no-index is mandatory: verify time has no network.
python3 -m pip install -q --no-index --find-links=/opt/verifier-deps \
  pytest==8.4.2 \
  pytest-asyncio==1.4.0 \
  pytest-textual-snapshot==1.1.0 \
  syrupy==4.8.0 \
  jinja2==3.1.6 \
  >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not install pinned test dependencies from /opt/verifier-deps" \
         | tee -a "$STDERR_LOG"; exit 1; }

# pytest-textual-snapshot declares `textual>=0.28.0`, which the editable /app install
# already satisfies, so pip leaves it alone. Assert that rather than trust it: if a
# resolver ever swapped in the PyPI wheel, the suite would silently test the wrong
# textual and the snapshot mismatch would be unexplainable.
python3 -c "import textual,os,sys; sys.exit(0 if os.path.realpath(textual.__file__).startswith('/app') else 1)" \
  || { echo "ERROR: the imported 'textual' is not the /app working tree - a dependency install replaced it" \
         | tee -a "$STDERR_LOG"; exit 1; }

echo "== running tests ==" | tee -a "$STDOUT_LOG"
# TEXTUAL_HEADLESS=1 disables the alternate-screen driver so Textual renders headlessly.
TEXTUAL_HEADLESS=1 PYTEST_ADDOPTS="" python -m pytest "tests/snapshot_tests/test_snapshots.py::test_auto_in_auto" tests/test_align_min.py tests/test_arrange.py tests/test_box_model.py \
  --junitxml="$REPORT" --tb=short -q --no-header \
  >>"$STDOUT_LOG" 2>>"$STDERR_LOG" || echo "(tests exited non-zero; parsing report)" | tee -a "$STDOUT_LOG"

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

python3 /tests/verifier.py "$REPORT" --rubric "${RUBRIC:-}" 2>>"$STDERR_LOG" | tee -a "$STDOUT_LOG"
echo "reward=$(cat /logs/verifier/reward.txt 2>/dev/null)" | tee -a "$STDOUT_LOG"
