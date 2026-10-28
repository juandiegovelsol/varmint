#!/usr/bin/env bash
# Behavioral verifier for CesiumGS__cesium-12521-mm. Patches in a new, dedicated spec file
# (packages/widgets/Specs/VoxelInspector/__tests__/VoxelInspectorViewModelSpec.js) that drives
# the real, current VoxelInspectorViewModel class (base/fixed/candidate) with a lightweight mock
# scene + mock voxel primitive, runs f2p+p2p through Cesium's own Karma/Jasmine spec harness
# (headless Chromium), and computes a reward from the JUnit report. NEVER greps source for the
# fix -- it runs the tests.
set -uo pipefail
mkdir -p /logs/verifier
STDOUT_LOG=/logs/verifier/test-stdout.txt
STDERR_LOG=/logs/verifier/test-stderr.txt
REPORT=/logs/verifier/karma-junit.xml       # MUST match verifier.py / run_karma.mjs
: > "$STDOUT_LOG"; : > "$STDERR_LOG"

ensure_reward() { [ -f /logs/verifier/reward.txt ] || echo 0 > /logs/verifier/reward.txt; }
trap ensure_reward EXIT

cd /app || { echo "no /app" | tee -a "$STDERR_LOG"; exit 1; }

# --- MM SWE submission capture -----------------------------------------------------------------
# Canonical block: must run immediately after `cd /app` and BEFORE the restore loop below, since
# this is the last moment /app is base + agent work. Captures tracked edits plus untracked
# source-like new files into /logs/verifier/submission.patch so a recorded trial can be
# re-scored against edited tests later without paying for another agent run.
_SUB=/logs/verifier/submission.patch
_SUBIDX=/tmp/.submission_index
_SUBSRC=('*.c' '*.cc' '*.cpp' '*.cxx' '*.h' '*.hh' '*.hpp' '*.hxx' '*.inl' '*.m' '*.mm'
         '*.py' '*.rb' '*.go' '*.rs' '*.java' '*.js' '*.ts' '*.tsx' '*.cs' '*.kt' '*.swift')
rm -f "$_SUBIDX"
GIT_INDEX_FILE="$_SUBIDX" git -C /app read-tree harbor_base 2>>"$STDERR_LOG" || true
GIT_INDEX_FILE="$_SUBIDX" git -C /app add -u 2>>"$STDERR_LOG" || true
mapfile -t _SUBNEW < <(git -C /app ls-files --others --exclude-standard \
  -- "${_SUBSRC[@]}" ':(exclude)lib/' ':(exclude)build/' ':(exclude).deps/' 2>/dev/null)
if [ "${#_SUBNEW[@]}" -gt 0 ]; then
  GIT_INDEX_FILE="$_SUBIDX" git -C /app add -- "${_SUBNEW[@]}" 2>>"$STDERR_LOG" || true
fi
GIT_INDEX_FILE="$_SUBIDX" git -C /app diff --binary --cached harbor_base \
  > "$_SUB" 2>>"$STDERR_LOG" || true
rm -f "$_SUBIDX"

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

# Robustness + idempotency: restore EVERY path test.patch touches to its pristine base state BEFORE
# applying, so (a) agent edits to tests can't change scoring and (b) the apply stays idempotent on
# re-runs. Read paths from the `diff --git a/... b/...` headers (present for text, BINARY, renamed,
# and deleted entries) -- NOT `+++ b/`, which is ABSENT for binary and renames.
_patch_paths=$(
  { sed -n 's#^diff --git a/\(.*\) b/.*#\1#p' /tests/test.patch
    sed -n 's#^diff --git a/.* b/\(.*\)#\1#p' /tests/test.patch
  } | sort -u )
for _p in $_patch_paths; do
  git -C /app checkout harbor_base -- "$_p" 2>/dev/null || rm -f "/app/$_p" 2>/dev/null || true
done
git -C /app clean -fdq -- $(printf '%s\n' $_patch_paths | xargs -r -n1 dirname | sort -u) 2>/dev/null || true

# Anti-tamper: the whole run depends on the repo's own spec plumbing (Specs/karma.conf.cjs,
# gulpfile.js, packages/widgets/Specs/**, packages/engine/Specs/**). Restore every tracked file
# under both spec trees to harbor_base so a candidate cannot weaken or delete a guard test, or
# redefine a matcher, on its way to a green run. Tracked files only -- nothing the candidate
# legitimately added under Source/ is touched.
git -C /app checkout harbor_base -- Specs packages/engine/Specs packages/widgets/Specs 2>/dev/null || true
# ...and delete anything UNTRACKED that a candidate dropped into either spec tree. Without this
# a candidate could plant e.g. packages/widgets/Specs/VoxelInspector/__tests__/
# VoxelInspectorViewModelSpec.js full of trivially green `it`s carrying this task's identifiers;
# the isolation step below moves aside every OTHER spec file, but a planted file at the exact
# target path is still cheap to delete outright before test.patch re-creates it. Scoped to the
# spec directories only -- /app/.harbor_assets and the candidate's own source files are never
# touched.
git -C /app clean -fdq -- Specs packages/engine/Specs packages/widgets/Specs 2>/dev/null || true

echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply --binary /tests/test.patch 2>>"$STDERR_LOG" \
  || git apply /tests/test.patch 2>>"$STDERR_LOG" \
  || patch -p1 -i /tests/test.patch 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }

# Test-only dep, installed HERE rather than baked into the image build: a JUnit reporter for
# karma, since the repo's own karma.conf.cjs only wires up "spec"/"longest" reporters. Internal
# to the test harness, unaffected by whatever the candidate's fix touches. The verifier phase has
# network_mode="public" per task.toml (only the agent/solve phase is sealed with "no-network"),
# so it's safe to install at verify time instead of shipping it in the agent-visible image.
echo "== installing test-only dep: karma-junit-reporter ==" | tee -a "$STDOUT_LOG"
npm install --no-audit --no-fund --no-save "karma-junit-reporter@2.0.1" \
  >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || { echo "ERROR: could not install karma-junit-reporter" | tee -a "$STDERR_LOG"; exit 1; }

# --- Isolate the target spec file --------------------------------------------------------------
# Cesium's widgets spec bundle (packages/widgets/Build/Specs/*) is regenerated on every
# `gulp build --workspace @cesium/widgets` from a glob over ALL packages/widgets/Specs/**/*Spec.js
# files. Temporarily relocate every OTHER *Spec.js file so the rebuilt bundle -- and therefore the
# karma run -- covers ONLY packages/widgets/Specs/VoxelInspector/__tests__/
# VoxelInspectorViewModelSpec.js (where every f2p/p2p identifier lives; matched by full PATH, not
# by basename, so a planted same-named file elsewhere in the tree is relocated like any other
# spec), instead of the whole widgets suite. Restored unconditionally on exit; this only changes
# which spec files get bundled/run, never any test's own behavior or source.
STAGE="$(mktemp -d)"
restore_specs() {
  if [ -d "$STAGE" ]; then
    ( cd "$STAGE" && find . -type f -print0 | while IFS= read -r -d '' f; do
        rel="${f#./}"
        mkdir -p "/app/packages/widgets/Specs/$(dirname "$rel")"
        mv "$f" "/app/packages/widgets/Specs/$rel"
      done )
    rm -rf "$STAGE"
  fi
  ensure_reward
}
trap restore_specs EXIT

while IFS= read -r -d '' f; do
  rel="${f#packages/widgets/Specs/}"
  mkdir -p "$STAGE/$(dirname "$rel")"
  mv "$f" "$STAGE/$rel"
done < <(find packages/widgets/Specs -iname "*Spec.js" \
           ! -path "packages/widgets/Specs/VoxelInspector/__tests__/VoxelInspectorViewModelSpec.js" -print0)

echo "== building engine index/exports (widgets imports @cesium/engine) ==" | tee -a "$STDOUT_LOG"
npx gulp build --workspace @cesium/engine >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || { echo "ERROR: gulp build (engine) failed" | tee -a "$STDERR_LOG"; exit 1; }

echo "== building widgets spec bundle (isolated to VoxelInspectorViewModelSpec.js) ==" | tee -a "$STDOUT_LOG"
npx gulp build --workspace @cesium/widgets >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
  || { echo "ERROR: gulp build (widgets) failed" | tee -a "$STDERR_LOG"; exit 1; }

echo "== running f2p + p2p tests (karma/jasmine) ==" | tee -a "$STDOUT_LOG"
# Node's ESM resolver walks up from the SCRIPT's own directory looking for node_modules --
# it never consults cwd or NODE_PATH for `import` (unlike CJS `require`). /tests is not
# inside /app, so `node /tests/run_karma.mjs` can't see /app/node_modules/karma. Copy the
# script into /app (where node_modules lives) before running it.
cp /tests/run_karma.mjs /app/.harbor_run_karma.mjs

run_suite() {
  node /app/.harbor_run_karma.mjs >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
    || echo "(tests exited non-zero; parsing report)" | tee -a "$STDOUT_LOG"
}

# A runner-level crash (browser failed to launch, karma died before the first spec) produces
# either no JUnit report at all or one with zero <testcase> elements. The verifier cannot tell
# that apart from a genuine all-red base run, so it would silently report 0.0. Retry ONCE, and
# ONLY on an empty/absent report -- never on test failures, which must stay red.
report_has_testcases() {
  [ -s "$REPORT" ] && grep -q "<testcase" "$REPORT"
}

run_suite
if ! report_has_testcases; then
  echo "== JUnit report empty or missing; retrying the suite once ==" | tee -a "$STDOUT_LOG"
  rm -f "$REPORT"
  run_suite
fi
rm -f /app/.harbor_run_karma.mjs

# Put the relocated *Spec.js files back BEFORE the judge computes its `git diff harbor_base`.
# Otherwise the diff spuriously shows every other widgets spec file as deleted (they're sitting
# in $STAGE, not on disk) -- the trap-based restore below only fires on script EXIT, which is
# too late.
restore_specs

echo "== running rubric judge (sub-agent request/rescore; never fatal) ==" | tee -a "$STDOUT_LOG"
RUBRIC=""
if [ -f /tests/rubrics.json ]; then
  RUBRIC=$(python3 /tests/judge.py --rubrics /tests/rubrics.json --repo /app 2>/logs/verifier/judge.log || echo "")
fi

echo "== computing reward ==" | tee -a "$STDOUT_LOG"
python3 /tests/verifier.py --rubric "${RUBRIC:-}" 2>>"$STDERR_LOG" | tee -a "$STDOUT_LOG"
echo "reward=$(cat /logs/verifier/reward.txt 2>/dev/null)" | tee -a "$STDOUT_LOG"
