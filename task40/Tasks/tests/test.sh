#!/usr/bin/env bash
# Behavioral verifier for ClanGenOfficial__clangen-4837-mm.
# Applies the synthetic tests, runs them, and computes a binary reward.
set -uo pipefail

mkdir -p /logs/verifier
STDOUT_LOG=/logs/verifier/test-stdout.txt
STDERR_LOG=/logs/verifier/test-stderr.txt
REPORT=/logs/verifier/report.xml

: > "$STDOUT_LOG"
: > "$STDERR_LOG"

ensure_reward() {
    [ -f /logs/verifier/reward.txt ] || echo 0 > /logs/verifier/reward.txt
    if [ ! -f /logs/verifier/reward.json ]; then
        printf '{"reward":0.0,"tests_passed":0.0,"f2p_passed":0,"f2p_total":0,"p2p_passed":0,"p2p_total":0,"rubric_passed":-1}' > /logs/verifier/reward.json
    fi
}
trap ensure_reward EXIT

cd /app || { echo "no /app" | tee -a "$STDERR_LOG"; exit 1; }

# Restore every path touched by test.patch to harbor_base before applying it.
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
_patch_dirs=$(printf '%s\n' $_patch_paths | xargs -r -n1 dirname | sort -u)
git -C /app clean -fdq -- $_patch_dirs 2>/dev/null || true

echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply --binary /tests/test.patch 2>>"$STDERR_LOG" \
    || git apply /tests/test.patch 2>>"$STDERR_LOG" \
    || patch -p1 -i /tests/test.patch 2>>"$STDERR_LOG" \
    || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }

echo "== installing pinned test-only deps ==" | tee -a "$STDOUT_LOG"
pip install --break-system-packages --no-cache-dir "pytest~=8.2" \
    >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
    || { echo "ERROR: could not install pytest" | tee -a "$STDERR_LOG"; exit 1; }
python3 -c "import pytest; print('pytest', pytest.__version__)" \
    | tee -a "$STDOUT_LOG"

echo "== running f2p + p2p tests ==" | tee -a "$STDOUT_LOG"
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
python3 -m pytest \
  "tests/test_unset_adoptive_parent.py" \
    --junitxml="$REPORT" \
    -v \
    >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
    || echo "(tests exited non-zero; parsing report)" | tee -a "$STDOUT_LOG"

echo "== computing reward ==" | tee -a "$STDOUT_LOG"
RUBRIC=""
if [ -f /tests/rubrics.json ] && [ -f /tests/judge.py ]; then
  RUBRIC=$(python3 /tests/judge.py --rubrics /tests/rubrics.json --repo /app \
             2>/logs/verifier/judge.log || echo "")
  echo "Rubric verdict: ${RUBRIC:-pending (judge request written; rescore after grading)}" \
      | tee -a "$STDOUT_LOG"
fi

python3 /tests/verifier.py --rubric "$RUBRIC" 2>>"$STDERR_LOG" | tee -a "$STDOUT_LOG"
echo "reward=$(cat /logs/verifier/reward.txt 2>/dev/null)" | tee -a "$STDOUT_LOG"
