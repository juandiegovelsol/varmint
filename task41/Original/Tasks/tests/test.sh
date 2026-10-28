#!/usr/bin/env bash
# Behavioral verifier for ClanGenOfficial__clangen-4978-mm
# ("[UI] Other Clan Relationship eeever so slightly covered by border").
# Applies the synthetic test additions (tests_harbor_leader_den_border/), runs the
# f2p + p2p tests, and computes a reward from the JUnit XML report.
# NEVER greps source files for the fix — it runs the tests.
set -uo pipefail

mkdir -p /logs/verifier
STDOUT_LOG=/logs/verifier/test-stdout.txt
STDERR_LOG=/logs/verifier/test-stderr.txt
REPORT=/logs/verifier/report.xml

: > "$STDOUT_LOG"
: > "$STDERR_LOG"

ensure_reward() {
    [ -f /logs/verifier/reward.txt ] || echo 0 > /logs/verifier/reward.txt
}
trap ensure_reward EXIT

cd /app || { echo "no /app" | tee -a "$STDERR_LOG"; exit 1; }

# ── Robustness + idempotency ──────────────────────────────────────────────────
# Restore every path that test.patch touches to the pristine harbor_base state
# BEFORE applying, so (a) agent edits to tests can't affect scoring and (b) the
# apply stays idempotent on re-runs.  Read paths from `diff --git a/… b/…`
# headers — these are present for all entry types (text, binary, renamed, deleted)
# unlike `+++ b/` which is absent for binary and renames.
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
# Also clean any untracked copies in the affected directories.  Every path in
# test.patch lives under tests_harbor_leader_den_border/, so the dirname is never '.'
# and this can never reach /app/.harbor_assets or the solver's own new files.
_patch_dirs=$(printf '%s\n' $_patch_paths | xargs -r -n1 dirname | sort -u)
for _d in $_patch_dirs; do
    case "$_d" in
      ""|"."|".."|"/"*|".."/*|*/"../"*) echo "refusing to clean '$_d'" | tee -a "$STDERR_LOG" ;;
      *) git -C /app clean -fdq -- "$_d" 2>/dev/null || true ;;
    esac
done

echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply --binary /tests/test.patch 2>>"$STDERR_LOG" \
    || git apply /tests/test.patch 2>>"$STDERR_LOG" \
    || patch -p1 -i /tests/test.patch 2>>"$STDERR_LOG" \
    || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }

# ── Test-only deps ────────────────────────────────────────────────────────────
# pytest 8.2 and pygame-ce are already installed in the image (pinned in the
# Dockerfile).  The suite drives the leader's den head-less through the SDL
# dummy drivers, so no display, no audio device and no save state are needed.
# Nothing is installed here — the verify run is offline.
echo "== checking pinned test-only deps ==" | tee -a "$STDOUT_LOG"
python3 -c "import pytest; print('pytest', pytest.__version__)" \
    | tee -a "$STDOUT_LOG"

# ── Run f2p + p2p tests ───────────────────────────────────────────────────────
# Run only the synthetic test package (contains all f2p + p2p tests).
# --confcutdir keeps pytest from loading any conftest.py above the suite's own
# directory, so a conftest planted at the repo root cannot influence scoring.
# The repo imports pygame at module scope, so SDL is forced to the dummy
# video/audio backends — no display, no audio device, no save state.
# `-p no:cacheprovider` keeps /app free of .pytest_cache.
run_suite() {
  SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
  python3 -m pytest \
    "tests_harbor_leader_den_border/test_other_clan_box_border.py" \
    -p no:cacheprovider --confcutdir=/app/tests_harbor_leader_den_border \
    --junitxml="$REPORT" -v \
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
