#!/usr/bin/env bash
# Behavioral verifier for SR5-FoundryVTT__SR5-FoundryVTT-1746-mm.
#
# Applies the synthetic test patch, then runs a standalone node script that transpiles the
# repo's real src/module/types/template/Base.ts (plus whatever real or off-file sibling modules
# it imports from within src/module/types/template/) with the image's own pinned TypeScript
# compiler, and drives the stable, pre-existing entry point every real call site already uses --
# ModifiableValueLinked() called bare, exactly as Action.ts's `ap: new
# ModifiableField(ModifiableValueLinked())` and `limit: new ModifiableField(ModifiableValueLinked())`
# both call it. Scoring comes from the actual cleaned/rounded field values, never from grepping
# the candidate source for the reference fix's own parameter-threading shape.
#
# f2p: ap_value_field_survives_fractional_input_unrounded
#      ap_base_field_survives_fractional_input_unrounded
#      linked_ap_schemafield_cleans_fractional_damage_ap_payload_intact
#      modifiable_value_total_rounds_up_not_truncated
#      modifiable_value_changes_apply_in_priority_order
#      reduce_damage_by_hits_does_not_mutate_original
# p2p: unrelated_value_field_bare_call_still_rounds_to_integer
#      value_max_pair_sibling_factory_still_integer_only
#      change_entry_numeric_fields_still_integer_only
#      threshold_bare_base_value_pair_call_still_integer_only
#      modifiable_value_min_max_enforcement_still_applies
#      modifiable_value_same_mode_changes_still_accumulate
#      modify_damage_by_hits_raising_path_still_adds_correctly
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

# Capture the agent's submission BEFORE anything below mutates /app -- this is the last
# moment the tree is base + agent work; the restore loop and test.patch come next.
#
# A THROWAWAY INDEX, never /app/.git/index: `git add` against the real one would leave paths
# staged and change how the `git checkout harbor_base --` and `git clean` below behave.
#
# TRACKED EDITS + A SOURCE WHITELIST, not `add -A` with a blacklist. The image's own `npm
# install` runs AFTER the harbor_base commit (environment/Dockerfile), so node_modules/ and
# any TypeScript build output are untracked. A bare `add -A` would capture all of that;
# inverting it -- stage tracked modifications, then add only untracked files that LOOK like
# source -- keeps the agent's work and drops generated output by default.
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


# -- Robustness + idempotency ---------------------------------------------------
# Restore every path that test.patch touches to the pristine harbor_base state
# BEFORE applying, so (a) agent edits to the test can't affect scoring and (b) the
# apply stays idempotent on re-runs.  Read paths from `diff --git a/... b/...`
# headers -- present for all entry types (text, binary, renamed, deleted) unlike
# `+++ b/`, which is absent for binary entries and renames.
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
mkdir -p /app/tests
git apply --binary /tests/test.patch 2>>"$STDERR_LOG" \
    || git apply /tests/test.patch 2>>"$STDERR_LOG" \
    || patch -p1 -i /tests/test.patch 2>>"$STDERR_LOG" \
    || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }

# -- Test-only deps ---------------------------------------------------------------
# NOTHING is installed here -- the verify run is offline. The only dependency
# is the repo's own TypeScript compiler, already baked into the image by the
# Dockerfile's `npm install --ignore-scripts`.
echo "== checking pinned test-only deps ==" | tee -a "$STDOUT_LOG"
node -e "console.log('typescript', require('/app/node_modules/typescript').version)" \
    >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
    || echo "WARNING: /app/node_modules/typescript missing" | tee -a "$STDERR_LOG"

# -- Run f2p + p2p tests ---------------------------------------------------------
# The script writes $REPORT (JUnit XML) itself and exits non-zero on any failure.
echo "== running f2p + p2p tests ==" | tee -a "$STDOUT_LOG"
node /app/tests/test_modifiable_value_linked.mjs \
    >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
    || echo "(tests exited non-zero; parsing report)" | tee -a "$STDOUT_LOG"

# -- Compute reward ----------------------------------------------------------------
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
