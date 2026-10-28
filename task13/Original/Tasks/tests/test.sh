#!/usr/bin/env bash
# Behavioral verifier for IvarK__AntimatterDimensionsSourceCode-2613-mm.
#
# Applies the PR's synthetic visual test (tests/test.patch), runs it under headful
# Chromium via Xvfb (virtual framebuffer), and scores the reward from the JUnit XML.
#
# Why Xvfb?  Headless Chrome 112+ uses overlay scrollbars regardless of custom
# ::-webkit-scrollbar CSS, so the corner widget never appears — the fix is unobservable.
# Headful Chrome with a virtual display forces traditional scrollbars and renders the
# white corner widget on the base commit, which disappears after the fix.
#
# The tests observe rendered pixel output and DOM-measured geometry — they NEVER
# grep the candidate's source for the CSS fix or any keyword.
#
# Three tests run from the single script (see tests/test.patch for details):
#   f2p  scrollbar_corner::test_corner_not_white                        (dark container)
#   f2p  scrollbar_corner_edge::test_corner_matches_container_background (rejects a
#        hard-coded corner colour and partial suppression)
#   p2p  scrollbar_chrome::test_custom_scrollbar_metrics_and_thumb_preserved
#        (custom scrollbar width + thumb colour survive the fix; holds on base too)
#
# Reward policy:
#   1.0 — all f2p pass AND p2p passes          (fix present, no regressions)
#   0.5 — some f2p pass, or a p2p regressed    (partial / shallow fix)
#   0.0 — no f2p passes, or suite crashed      (fix absent or broken)
#
# Harbor reads the reward from /logs/verifier/reward.txt.

set -uo pipefail

mkdir -p /logs/verifier
STDOUT_LOG=/logs/verifier/test-stdout.txt
STDERR_LOG=/logs/verifier/test-stderr.txt
REPORT=/logs/verifier/report.xml       # JUnit XML; must match verifier.py
: > "$STDOUT_LOG"; : > "$STDERR_LOG"

# Guarantee reward.txt always exists (even on crash).
ensure_reward() {
  [ -f /logs/verifier/reward.txt ] || echo 0 > /logs/verifier/reward.txt
  # Kill Xvfb if we started it.
  [ -n "${XVFB_PID:-}" ] && kill "$XVFB_PID" 2>/dev/null || true
}
trap ensure_reward EXIT

cd /app || { echo "no /app" | tee -a "$STDERR_LOG"; exit 1; }

# ── Step 1: Reset test files to the immutable harbor_base state ───────────────
# Read every path touched by test.patch from "diff --git a/... b/..." headers
# (covers text additions, binary files, renames, and deletions — unlike +++ lines
# which are absent for binaries and renames).
echo "== resetting test files from harbor_base ==" | tee -a "$STDOUT_LOG"
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
# Clean any untracked files left under the same directories (e.g. previously applied new-file entries).
_dirs=$(printf '%s\n' $_patch_paths | xargs -r -n1 dirname | sort -u)
[ -n "$_dirs" ] && git -C /app clean -fdq -- $_dirs 2>/dev/null || true
echo "Reset complete." | tee -a "$STDOUT_LOG"

# ── Step 2: Apply test.patch (idempotent) ─────────────────────────────────────
echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply --binary /tests/test.patch 2>>"$STDERR_LOG" \
  || git apply /tests/test.patch    2>>"$STDERR_LOG" \
  || patch -p1 -i /tests/test.patch 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }
echo "test.patch applied." | tee -a "$STDOUT_LOG"

# ── Step 3: Resolve pinned test-only deps (OFFLINE — no registry access) ──────
# pngjs@6 is used by the test script to decode the PNG screenshot.  It is baked
# into the image at build time (see environment/Dockerfile), because this
# verifier runs with network_mode="no-network" — any registry round-trip here
# fails with ECONNRESET and takes the whole run to reward 0.
#
# /opt/test-deps/node_modules is the authoritative copy; /app/node_modules is
# also honoured (Node walks up from /app/tests), so a locally-installed copy
# still works.  Never contact the network.
echo "== resolving test-only deps (offline) ==" | tee -a "$STDOUT_LOG"
export NODE_PATH="${TEST_DEPS_DIR:-/opt/test-deps}/node_modules${NODE_PATH:+:$NODE_PATH}"
if node -e "require('pngjs')" 2>>"$STDERR_LOG"; then
  echo "pngjs resolved from image (NODE_PATH=$NODE_PATH)." | tee -a "$STDOUT_LOG"
else
  # Last resort: the local npm cache only.  --offline never opens a socket, so
  # this fails fast instead of hanging or throwing ECONNRESET.
  echo "WARN: pngjs not preinstalled; trying offline npm cache" | tee -a "$STDERR_LOG"
  npm install --no-save --offline --no-audit --no-fund pngjs@6.0.0 \
    >>"$STDOUT_LOG" 2>>"$STDERR_LOG" || true
  node -e "require('pngjs')" 2>>"$STDERR_LOG" \
    || { echo "ERROR: pngjs unavailable offline — rebuild the image so it is baked in" \
           | tee -a "$STDERR_LOG"; exit 1; }
  echo "pngjs resolved from npm cache." | tee -a "$STDOUT_LOG"
fi

# ── Step 4: Start virtual X11 framebuffer ─────────────────────────────────────
# Headless Chrome 112+ uses overlay scrollbars regardless of ::-webkit-scrollbar CSS,
# so the corner widget never appears — the fix is unobservable.  Headful Chrome with
# a virtual X11 display forces traditional scrollbars and renders the white corner
# widget on the base commit.
#
# Xvfb is launched with -ac (access control disabled) so xauth is not required.
# We kill any stale process on :99 first, then start a fresh one.
echo "== starting Xvfb virtual display :99 ==" | tee -a "$STDOUT_LOG"
pkill -f "Xvfb :99" 2>/dev/null || true
sleep 0.3
Xvfb :99 -screen 0 1280x1024x24 -ac 2>>"$STDERR_LOG" &
XVFB_PID=$!
export DISPLAY=:99
# Wait for Xvfb to actually be ready (up to 10 s) by polling for its X11 socket.
# NOTE: do not probe with `node -e "process.exit(0)"` — Node never opens the
# display, so that exits 0 immediately and the loop becomes a no-op, letting
# Chromium launch against a display that is not listening yet.
_xvfb_ready=0
for _i in $(seq 1 20); do
  if [ -S /tmp/.X11-unix/X99 ]; then _xvfb_ready=1; break; fi
  kill -0 "$XVFB_PID" 2>/dev/null || break   # Xvfb died; stop waiting
  sleep 0.5
done
if [ "$_xvfb_ready" = 1 ]; then
  echo "Xvfb ready (PID=$XVFB_PID, DISPLAY=:99)." | tee -a "$STDOUT_LOG"
else
  echo "ERROR: Xvfb :99 did not come up" | tee -a "$STDERR_LOG"; exit 1
fi

# ── Step 5: Run the f2p test ──────────────────────────────────────────────────
echo "== running scrollbar-corner test (headful Chrome via Xvfb) ==" | tee -a "$STDOUT_LOG"
node /app/tests/scrollbar-corner-test.js \
  >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || echo "(test exited non-zero; verifier will score from report)" | tee -a "$STDOUT_LOG"

# ── Step 6: Score the reward ──────────────────────────────────────────────────
echo "== computing reward ==" | tee -a "$STDOUT_LOG"
python3 /tests/verifier.py 2>>"$STDERR_LOG" | tee -a "$STDOUT_LOG"
echo "reward=$(cat /logs/verifier/reward.txt 2>/dev/null)" | tee -a "$STDOUT_LOG"
