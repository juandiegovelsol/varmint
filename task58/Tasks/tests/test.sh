#!/usr/bin/env bash
# Behavioral verifier for SR5-FoundryVTT__SR5-FoundryVTT-1831-mm.
#
# Applies the synthetic test patch, then runs a standalone node script that transpiles the
# repo's real src/module/migrator/Migrator.ts (plus whatever real or off-file sibling modules it
# imports from within src/module/migrator/) with the image's own pinned TypeScript compiler, and
# calls the stable, pre-existing entry point Migrator.migrate('ActiveEffect', data) directly
# against hand-built plain-object ActiveEffect fixtures. Scoring comes from the actual mutated
# fixture data (which `changes[].key` survives migration) exactly as this repo's own
# maintainer-authored Quench suite (src/unittests/Migrators.spec.ts) already asserts on
# Migrator.migrate()/handlesActiveEffect() output -- the candidate source is NEVER grepped, and
# no new-in-the-fix symbol name (Version0_33_1, its private helper methods) is required to exist.
#
# f2p: legacy_data_modifiers_key_migrates_to_pool_on_test_all_effect
#      legacy_data_modifiers_mod_key_migrates_to_pool_on_test_item_effect
#      legacy_test_modifier_migration_matches_full_applyto_and_key_matrix
#      migration_preserves_sibling_changes_and_effect_identity
#      migration_handles_effect_with_multiple_legacy_test_modifier_changes
# p2p: non_test_effect_data_modifiers_key_is_left_alone
#      effect_with_similar_but_non_matching_applyto_value_is_left_alone
#      unrelated_change_key_on_test_effect_is_left_alone
#      effect_already_at_current_system_version_is_not_touched_at_all
#      older_effect_still_receives_pre_existing_version_migrations
#      test_scoped_effect_with_no_changes_is_left_alone_without_erroring
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
# BEFORE applying, so (a) agent edits to the test can't affect scoring and (b) the
# apply stays idempotent on re-runs.  Read paths from `diff --git a/… b/…`
# headers — present for all entry types (text, binary, renamed, deleted) unlike
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

# ── Test-only deps ────────────────────────────────────────────────────────────
# NOTHING is installed here — the verify run is offline. The only dependency
# is the repo's own TypeScript compiler, already baked into the image by the
# Dockerfile's `npm install --ignore-scripts`.
echo "== checking pinned test-only deps ==" | tee -a "$STDOUT_LOG"
node -e "console.log('typescript', require('/app/node_modules/typescript').version)" \
    >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
    || echo "WARNING: /app/node_modules/typescript missing" | tee -a "$STDERR_LOG"

# ── Run f2p + p2p tests ───────────────────────────────────────────────────────
# The script writes $REPORT (JUnit XML) itself and exits non-zero on any failure.
echo "== running f2p + p2p tests ==" | tee -a "$STDOUT_LOG"
node /app/tests/test_migrator_test_modifier_key.mjs \
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
