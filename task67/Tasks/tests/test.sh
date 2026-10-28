#!/usr/bin/env bash
# Behavioral verifier for ihhub__fheroes2-4924-mm.
#
# Applies the test patch (adds stubs.cpp + test_actionlistpressright.cpp),
# compiles the test against the CANDIDATE's dialog_selectscenario.cpp,
# links with GoogleTest, runs the test, and calls verifier.py.
#
# BEHAVIORAL: the test calls ScenarioListBox::ActionListPressRight() and checks
# whether fheroes2::showMessage was invoked — it NEVER greps source code.
#
# BASE  (no fix) : ActionListPressRight calls showMessage → test FAILS → reward 0.0
# FIXED (fix app): ActionListPressRight is a no-op → test PASSES    → reward 1.0
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

# Capture the agent's submission BEFORE anything below mutates /app -- this is the last
# moment the tree is base + agent work; the restore loop and test.patch come next.
#
# A THROWAWAY INDEX, never /app/.git/index: `git add` against the real one would leave paths
# staged and change how the `git checkout harbor_base --` and `git clean` below behave.
#
# TRACKED EDITS + A SOURCE WHITELIST, not `add -A` with a blacklist. This image builds wx
# in-tree AFTER the harbor_base commit (environment/Dockerfile), so everything the build
# emits is untracked and NOT in wx's .gitignore. A bare `add -A` captured 380MB of .o/.d/.so;
# excluding those by extension still left ~120 configure-generated files (samples/*/Makefile,
# bk-deps, version-script, lib/wx/config/*, the utils/wxrc/wxrc binary) because most have no
# extension to blacklist. Inverting it -- stage tracked modifications, then add only untracked
# files that LOOK like source -- keeps the agent's work and drops generated output by default.
_SUB=/logs/verifier/submission.patch
_SUBIDX=/tmp/.submission_index
_SUBSRC=('*.c' '*.cc' '*.cpp' '*.cxx' '*.h' '*.hh' '*.hpp' '*.hxx' '*.inl' '*.m' '*.mm'
         '*.py' '*.rb' '*.go' '*.rs' '*.java' '*.js' '*.ts' '*.tsx' '*.cs' '*.kt' '*.swift')
rm -f "$_SUBIDX"
GIT_INDEX_FILE="$_SUBIDX" git -C /app read-tree harbor_base 2>>"$STDERR_LOG" || true
GIT_INDEX_FILE="$_SUBIDX" git -C /app add -u 2>>"$STDERR_LOG" || true
# Enumerate before adding: `git add` aborts and stages NOTHING if any one pathspec matches
# no file, which silently drops the agent's new files on most tasks.
# Generated-output dirs are dropped from the UNTRACKED scan only. A project that keeps real
# source under lib/ is unaffected: those files are tracked at harbor_base, so `add -u` above
# already has them. This drops only files CREATED under a build dir during the run -- which,
# left in, break replay: they are recorded as new-file hunks and a fresh container from the
# same image already has them, so `git apply` fails with "already exists in working directory".
mapfile -t _SUBNEW < <(git -C /app ls-files --others --exclude-standard \
  -- "${_SUBSRC[@]}" ':(exclude)lib/' ':(exclude)build/' ':(exclude).deps/' 2>/dev/null)
if [ "${#_SUBNEW[@]}" -gt 0 ]; then
  GIT_INDEX_FILE="$_SUBIDX" git -C /app add -- "${_SUBNEW[@]}" 2>>"$STDERR_LOG" || true
fi
GIT_INDEX_FILE="$_SUBIDX" git -C /app diff --binary --cached harbor_base \
  > "$_SUB" 2>>"$STDERR_LOG" || true
rm -f "$_SUBIDX"

# WHAT THE WHITELIST DROPPED, listed rather than silently discarded. The split above captures
# every change to a TRACKED file (any extension, deletions included) but only NEW files that
# look like source -- so an agent adding config.yml, a .cmake module or an extensionless script
# loses it, and the patch still looks clean. That is the failure this manifest exists to expose.
#
# NEWEST FIRST, which is the useful ordering and not a cosmetic one: build output and image
# assets are created before the agent phase starts, so anything the agent made sorts to the top.
# Build artifacts are excluded by the same rules as the capture, to keep the list readable.
#
# If something here belongs in the submission, widen _SUBSRC. Do not reach for `add -A`.
_SUBSKIP=/logs/verifier/submission-skipped.txt
_SUBCAP=/tmp/.submission_captured
if [ "${#_SUBNEW[@]}" -gt 0 ]; then printf '%s\n' "${_SUBNEW[@]}" > "$_SUBCAP"; else : > "$_SUBCAP"; fi
_SUBSKIPN=$(git -C /app ls-files --others --exclude-standard -- . \
    ':(exclude)lib/' ':(exclude)build/' ':(exclude).deps/' \
    ':(exclude)*.o' ':(exclude)*.d' ':(exclude)*.a' ':(exclude)*.lo' ':(exclude)*.la' \
    ':(exclude)*.so' ':(exclude)*.so.*' ':(exclude)*.gch' ':(exclude)*.pyc' 2>/dev/null \
  | grep -vxF -f "$_SUBCAP" 2>/dev/null | wc -l)
{ echo "# Untracked files NOT captured into submission.patch, newest first."
  echo "# Anything the agent created sorts above build output, which predates the agent phase."
  echo "# total: ${_SUBSKIPN}  (showing at most 40)"
  git -C /app ls-files --others --exclude-standard -- . \
      ':(exclude)lib/' ':(exclude)build/' ':(exclude).deps/' \
      ':(exclude)*.o' ':(exclude)*.d' ':(exclude)*.a' ':(exclude)*.lo' ':(exclude)*.la' \
      ':(exclude)*.so' ':(exclude)*.so.*' ':(exclude)*.gch' ':(exclude)*.pyc' 2>/dev/null \
    | grep -vxF -f "$_SUBCAP" 2>/dev/null | head -200 \
    | while IFS= read -r _f; do
        printf '%s\t%s\t%s\n' "$(stat -c %Y "/app/$_f" 2>/dev/null || echo 0)" \
                              "$(stat -c %s "/app/$_f" 2>/dev/null || echo 0)" "$_f"
      done \
    | sort -rn | head -40 | awk -F'\t' '{printf "%s\t%s\t%s\n",$1,$2,$3}'
} > "$_SUBSKIP" 2>/dev/null || true
rm -f "$_SUBCAP"

# Size guard. The whitelist is a heuristic, so a task laying out source unusually could still
# produce something enormous. Cap it and leave a diagnosable stub: a truncated capture is
# recoverable, a full disk is not.
_SUBSZ=$(wc -c < "$_SUB" 2>/dev/null || echo 0)
if [ "$_SUBSZ" -gt 5242880 ]; then
  { echo "SUBMISSION CAPTURE SUPPRESSED: ${_SUBSZ} bytes exceeds the 5MB cap."
    echo "Directories contributing to the discarded patch:"
    grep -a "^diff --git" "$_SUB" | sed 's#^diff --git a/##; s# b/.*##; s#/[^/]*$##' \
      | sort | uniq -c | sort -rn | head -20
  } > "$_SUB.suppressed" 2>/dev/null
  : > "$_SUB"
  echo "== submission.patch SUPPRESSED (${_SUBSZ} bytes > 5MB cap) ==" | tee -a "$STDOUT_LOG"
else
  echo "== captured submission.patch (${_SUBSZ} bytes, $(grep -ac '^diff --git' "$_SUB" 2>/dev/null || echo 0) files) ==" \
    | tee -a "$STDOUT_LOG"
fi


# -----------------------------------------------------------------------
# Step 1 — reset test-patch paths from harbor_base so the apply is idempotent
# -----------------------------------------------------------------------
_patch_paths=$(
  { sed -n 's#^diff --git a/\(.*\) b/.*#\1#p' /tests/test.patch
    sed -n 's#^diff --git a/.* b/\(.*\)#\1#p' /tests/test.patch
  } | sort -u )
for _p in $_patch_paths; do
  git -C /app checkout harbor_base -- "$_p" 2>/dev/null || rm -f "/app/$_p" 2>/dev/null || true
done
git -C /app clean -fdq -- $(printf '%s\n' $_patch_paths | xargs -r -n1 dirname | sort -u) 2>/dev/null || true

# -----------------------------------------------------------------------
# Step 2 — apply test.patch (adds harbor_test_src/ test files)
# -----------------------------------------------------------------------
echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply --binary /tests/test.patch 2>>"$STDERR_LOG" \
  || git apply /tests/test.patch 2>>"$STDERR_LOG" \
  || patch -p1 -i /tests/test.patch 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }

# -----------------------------------------------------------------------
# Step 3 — build gtest from the source vendored under /tests/vendor (offline,
# no network: this is plain GoogleTest source, not a Debian package, and it
# is never baked into the agent-visible image -- only /tests/ carries it,
# supplied fresh at verify time).
# -----------------------------------------------------------------------
echo "== building test deps ==" | tee -a "$STDOUT_LOG"
if [ ! -f /usr/local/lib/libgtest.a ]; then
  GTEST_BUILD_DIR=/tmp/gtest-build
  cmake -S /tests/vendor/googletest -B "$GTEST_BUILD_DIR" \
        -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local -DBUILD_GMOCK=OFF \
    >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
    && cmake --build "$GTEST_BUILD_DIR" --parallel 4 >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
    && cmake --install "$GTEST_BUILD_DIR" >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
    && rm -rf "$GTEST_BUILD_DIR" \
    || { echo "ERROR: could not build libgtest.a from /tests/vendor/googletest" | tee -a "$STDERR_LOG"; exit 1; }
fi
ls /usr/local/lib/libgtest.a >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || { echo "ERROR: libgtest.a not found" | tee -a "$STDERR_LOG"; exit 1; }

# -----------------------------------------------------------------------
# Step 4 — compile and link the test
# -----------------------------------------------------------------------
echo "== compiling test ==" | tee -a "$STDOUT_LOG"

IFLAGS="
  -I /app/src/fheroes2/agg
  -I /app/src/fheroes2/ai
  -I /app/src/fheroes2/army
  -I /app/src/fheroes2/battle
  -I /app/src/fheroes2/campaign
  -I /app/src/fheroes2/castle
  -I /app/src/fheroes2/dialog
  -I /app/src/fheroes2/game
  -I /app/src/fheroes2/gui
  -I /app/src/fheroes2/h2d
  -I /app/src/fheroes2/heroes
  -I /app/src/fheroes2/image
  -I /app/src/fheroes2/kingdom
  -I /app/src/fheroes2/maps
  -I /app/src/fheroes2/monster
  -I /app/src/fheroes2/objects
  -I /app/src/fheroes2/pocketpc
  -I /app/src/fheroes2/resource
  -I /app/src/fheroes2/spell
  -I /app/src/fheroes2/system
  -I /app/src/fheroes2/world
  -I /app/src/engine"

SDL_CFLAGS=$(sdl2-config --cflags 2>/dev/null || echo "-I/usr/include/SDL2 -D_REENTRANT")
CFLAGS="-std=c++11 ${SDL_CFLAGS}"

BUILD_DIR=/tmp/harbor_test_build
mkdir -p "$BUILD_DIR"

g++ $CFLAGS -c /app/harbor_test_src/stubs.cpp            $IFLAGS -o "$BUILD_DIR/stubs.o"     2>>"$STDERR_LOG" || { echo "ERROR: stubs.cpp compile failed"  | tee -a "$STDERR_LOG"; exit 1; }
g++ $CFLAGS -c /app/src/fheroes2/dialog/dialog_selectscenario.cpp $IFLAGS -o "$BUILD_DIR/dialog.o" 2>>"$STDERR_LOG" || { echo "ERROR: dialog.cpp compile failed"  | tee -a "$STDERR_LOG"; exit 1; }
g++ $CFLAGS -c /app/harbor_test_src/test_actionlistpressright.cpp $IFLAGS -o "$BUILD_DIR/test_main.o" 2>>"$STDERR_LOG" || { echo "ERROR: test.cpp compile failed"    | tee -a "$STDERR_LOG"; exit 1; }

g++ -std=c++11 "$BUILD_DIR/stubs.o" "$BUILD_DIR/dialog.o" "$BUILD_DIR/test_main.o" \
    -lgtest -lpthread -lSDL2 \
    -o "$BUILD_DIR/test_selectscenario" 2>>"$STDERR_LOG" \
  || { echo "ERROR: link failed" | tee -a "$STDERR_LOG"; exit 1; }

echo "== build succeeded ==" | tee -a "$STDOUT_LOG"

# -----------------------------------------------------------------------
# Step 5 — run test with JUnit XML output
# -----------------------------------------------------------------------
echo "== running f2p tests ==" | tee -a "$STDOUT_LOG"
"$BUILD_DIR/test_selectscenario" \
    --gtest_output="xml:${REPORT}" \
    >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || echo "(test process exited non-zero; parsing report)" | tee -a "$STDOUT_LOG"

# -----------------------------------------------------------------------
# Step 6 — compute reward
# -----------------------------------------------------------------------
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
