#!/usr/bin/env bash
# Behavioral verifier for ClanGenOfficial__clangen-5225-mm.
# Applies the synthetic test additions (tests/test_focus_matrix.py), runs the
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
# Also clean any untracked copies in the affected directories
_patch_dirs=$(printf '%s\n' $_patch_paths | xargs -r -n1 dirname | sort -u)
git -C /app clean -fdq -- $_patch_dirs 2>/dev/null || true

echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply --binary /tests/test.patch 2>>"$STDERR_LOG" \
    || git apply /tests/test.patch 2>>"$STDERR_LOG" \
    || patch -p1 -i /tests/test.patch 2>>"$STDERR_LOG" \
    || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }

# ── Test-only deps ────────────────────────────────────────────────────────────
# pytest 8.2, pygame-ce and pygame-gui are already installed in the image
# (pinned in the Dockerfile). Nothing is installed here — the verify run is
# offline (network_mode = "no-network").
echo "== checking pinned test deps (no install) ==" | tee -a "$STDOUT_LOG"
python3 -c "import pytest; print('pytest', pytest.__version__)" \
    | tee -a "$STDOUT_LOG"
python3 -c "import pygame; print('pygame', pygame.version.ver)" \
    | tee -a "$STDOUT_LOG"

# ── Run f2p + p2p tests ───────────────────────────────────────────────────────
echo "== running f2p + p2p tests ==" | tee -a "$STDOUT_LOG"
# Run only the synthetic test file (contains all f2p + p2p tests).
# SDL dummy drivers keep this fully headless: no display, no audio device.
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
python3 -m pytest \
  "tests/test_focus_matrix.py" \
    --junitxml="$REPORT" \
    -v \
    >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
    || echo "(tests exited non-zero; parsing report)" | tee -a "$STDOUT_LOG"

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
