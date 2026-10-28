#!/usr/bin/env bash
# Behavioral verifier for wxWidgets__wxWidgets-23046-mm. Rebuilds wxWidgets (the fix touches
# include/wx/gtk/dc.h + src/gtk/dc.cpp, part of the core shared library test_gui links against),
# applies the PR's test additions, runs each configured f2p/p2p Catch2 SECTION *standalone*
# (the full `ClippingBoxTestCase::wxPaintDC` run terminates early after ~20 of ~50 leaf sections
# under this Catch2 build, so a combined run silently loses coverage of later sections -- each
# identifier gets its own `-c "<name>" --reporter xml` invocation instead), and computes a reward
# purely from the resulting reports. NEVER greps/matches source for the fix.
set -uo pipefail
mkdir -p /logs/verifier /logs/verifier/reports
STDOUT_LOG=/logs/verifier/test-stdout.txt
STDERR_LOG=/logs/verifier/test-stderr.txt
: > "$STDOUT_LOG"; : > "$STDERR_LOG"

ensure_reward() { [ -f /logs/verifier/reward.txt ] || echo 0 > /logs/verifier/reward.txt; }
trap ensure_reward EXIT

cd /app || { echo "no /app" | tee -a "$STDERR_LOG"; exit 1; }

# Robustness + idempotency: restore every path test.patch touches to its pristine base state
# before applying, so agent edits to tests can't change scoring and re-runs stay idempotent.
_patch_paths=$(
  { sed -n 's#^diff --git a/\(.*\) b/.*#\1#p' /tests/test.patch
    sed -n 's#^diff --git a/.* b/\(.*\)#\1#p' /tests/test.patch
  } | sort -u )
for _p in $_patch_paths; do
  git -C /app checkout harbor_base -- "$_p" 2>/dev/null || rm -f "/app/$_p" 2>/dev/null || true
done
git -C /app clean -fdq -- $(printf '%s\n' $_patch_paths | xargs -r -n1 dirname | sort -u) 2>/dev/null || true

echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git -C /app apply --binary /tests/test.patch 2>>"$STDERR_LOG" \
  || git -C /app apply /tests/test.patch 2>>"$STDERR_LOG" \
  || (cd /app && patch -p1 -i /tests/test.patch) 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not apply test.patch" | tee -a "$STDOUT_LOG" "$STDERR_LOG"; exit 1; }

# Catch2, nanosvg and the GTK3/Cairo dev headers are BAKED INTO THE IMAGE at build time --
# rebuilding the wxGTK3 library and test_gui from scratch here would risk the verifier's own
# timeout even for a correct fix, and the agent phase is offline ([agent] network_mode=
# "no-network") so those can't be fetched later anyway. xvfb/xauth, by contrast, are needed
# only to RUN test_gui headless, not to build it or the library, so they're installed here
# instead of baked in -- this phase has network_mode="public" (also how the rubric judge
# below reaches its API).
echo "== installing xvfb/xauth (test-only, run-time dep) ==" | tee -a "$STDOUT_LOG"
apt-get update >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  && apt-get install -y --no-install-recommends xvfb xauth >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not install xvfb/xauth" | tee -a "$STDOUT_LOG" "$STDERR_LOG"; exit 1; }

echo "== rebuilding wxWidgets (fix touches core library sources) ==" | tee -a "$STDOUT_LOG"
( cd /app/buildgtk && make -j"$(nproc)" ) >>"$STDOUT_LOG" 2>>"$STDERR_LOG"
BUILD_RC=$?
if [ "$BUILD_RC" -eq 0 ]; then
  ( cd /app/buildgtk/tests && make -j"$(nproc)" test_gui ) >>"$STDOUT_LOG" 2>>"$STDERR_LOG"
  BUILD_RC=$?
fi
echo "build_rc=$BUILD_RC" | tee -a "$STDOUT_LOG"

sanitize() { printf '%s' "$1" | tr -c 'A-Za-z0-9' '_'; }

if [ "$BUILD_RC" -eq 0 ] && [ -x /app/buildgtk/tests/test_gui ]; then
  TEST_CASE=$(python3 -c "import json;print(json.load(open('/tests/config.json'))['test_case'])")
  echo "== running f2p + p2p tests (test_case=$TEST_CASE) ==" | tee -a "$STDOUT_LOG"
  while IFS= read -r _name; do
    [ -z "$_name" ] && continue
    _out="/logs/verifier/reports/$(sanitize "$_name").xml"
    ( cd /app/buildgtk/tests && xvfb-run -a ./test_gui "$TEST_CASE" -c "$_name" --reporter xml --out "$_out" ) >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
      || echo "(section '$_name' exited non-zero; parsing report)" | tee -a "$STDOUT_LOG"
  done < <(python3 -c "
import json
c = json.load(open('/tests/config.json'))
for n in c['f2p'] + c['p2p']:
    print(n)
")
else
  echo "ERROR: build failed (build_rc=$BUILD_RC) or test_gui missing; skipping test run" | tee -a "$STDOUT_LOG" "$STDERR_LOG"
fi

echo "== rubric judge (sub-agent/API request or rescore) ==" | tee -a "$STDOUT_LOG"
# The `|| echo ""` is load-bearing: the judge must never be able to fail the run. On the
# first pass with no verdict yet, judge.py tries the in-band API backend, and falls back to
# writing a sub-agent judge request under /logs/verifier/judge/ (printing nothing) if that
# backend is unavailable -- scoring then falls back to tests alone until a rescore.
RUBRIC=""
if [ -f /tests/rubrics.json ]; then
  RUBRIC=$(python3 /tests/judge.py --rubrics /tests/rubrics.json --repo /app --judge-dir /logs/verifier/judge \
             2>>"$STDERR_LOG" || echo "")
fi
echo "rubric_verdict=${RUBRIC:-pending (judge request written; rescore after grading)}" | tee -a "$STDOUT_LOG"

echo "== computing reward ==" | tee -a "$STDOUT_LOG"
python3 /tests/verifier.py --rubric "${RUBRIC:-}" 2>>"$STDERR_LOG" | tee -a "$STDOUT_LOG"

echo "reward=$(cat /logs/verifier/reward.txt 2>/dev/null)" | tee -a "$STDOUT_LOG"
