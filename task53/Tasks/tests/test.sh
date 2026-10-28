#!/usr/bin/env bash
# Behavioral verifier for SR5-FoundryVTT__SR5-FoundryVTT-1462-mm.
#
# Applies the synthetic test patch, then runs a standalone node script that drives every side
# of the sprite power round trip against the candidate's own tree:
#   1. It compiles and RENDERS the candidate's own Handlebars templates with the candidate's
#      own registered helpers -- once with no powers, to scrape the real .list-header elements
#      and whatever discriminator they carry under whatever attribute name, and once with one
#      power per optional state, to see which section each row lands under and which controls
#      its markup offers.
#   2. It transpiles the repo's real SR5BaseActorSheet.ts / SR5SpriteActorSheet.ts (plus any
#      real or off-file helper modules they import, from ANY source directory) with the
#      image's own pinned TypeScript compiler, and hands those real rendered headers to each
#      sheet's stable, pre-existing entry point (_onItemCreate) against hand-built FoundryVTT
#      Actor fixtures.
#   3. It drives the sheet's other stable, pre-existing entry point (_onListItemToggleEnabled)
#      against item fixtures and scores the resulting item state, applying whatever update the
#      sheet issued (flat dotted keys or a nested system object, actor.updateEmbeddedDocuments
#      or item.update -- all accepted).
# Scoring comes from observable app behaviour: the item data the (fake) createEmbeddedDocuments
# call receives, the markup the templates really produce, and the item state a toggle leaves
# behind. The candidate source is NEVER grepped, and no new-in-a-fix helper name, attribute
# name, update-call shape or file location is required to exist. Because the templates are
# really rendered, a submission that wires up only part of the round trip fails, which is
# correct: in the running app it fixes nothing.
#
# f2p: sprite_power_enabled_section_create_tags_new_item_enabled_option
#      sprite_power_disabled_section_create_tags_new_item_disabled_option
#      sprite_power_sections_bucket_independently_not_all_into_general
#      sprite_power_sections_all_create_sprite_power_typed_items
#      sprite_power_rows_render_under_the_section_matching_their_optional_state
#      sprite_power_enable_toggle_offered_only_for_optional_powers
#      sprite_power_enable_toggle_swaps_section_and_enabled_state_together
# p2p: actor_sheet_generic_item_create_unaffected_by_sprite_specific_data
#      sprite_sheet_non_sprite_power_item_create_stays_unaffected
#      item_create_still_unhides_its_inventory_section
#      item_create_still_adds_to_selected_non_default_inventory
#      sprite_power_section_headers_still_carry_an_item_type_id
#      enable_toggle_still_ignores_standard_powers_and_non_power_items
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
# The repo's own TypeScript compiler is already baked into the image by the Dockerfile's
# `npm install --ignore-scripts` -- it's a real build-time dependency of the cloned repo
# itself, not test-only. Handlebars IS test-only (used solely by this harness to render
# the candidate's own templates), so it is installed here, at verify time, pinned to an
# exact version. This phase's network_mode is "public" (see task.toml), so the install
# can reach the registry; --no-save keeps package.json byte-for-byte identical to
# harbor_base, so the agent never sees this dependency.
echo "== installing pinned test-only deps ==" | tee -a "$STDOUT_LOG"
npm install --ignore-scripts --no-save handlebars@4.7.8 \
    >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
    || { echo "ERROR: failed to install handlebars" | tee -a "$STDERR_LOG"; exit 1; }

echo "== checking pinned test-only deps ==" | tee -a "$STDOUT_LOG"
node -e "console.log('typescript', require('/app/node_modules/typescript').version)" \
    >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
    || echo "WARNING: /app/node_modules/typescript missing" | tee -a "$STDERR_LOG"
node -e "console.log('handlebars', require('/app/node_modules/handlebars').VERSION)" \
    >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
    || echo "WARNING: /app/node_modules/handlebars missing" | tee -a "$STDERR_LOG"

# ── Run f2p + p2p tests ───────────────────────────────────────────────────────
# The script writes $REPORT (JUnit XML) itself and exits non-zero on any failure.
echo "== running f2p + p2p tests ==" | tee -a "$STDOUT_LOG"
node /app/tests/test_sprite_power_sections.mjs \
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

python3 /tests/verifier.py --rubric "$RUBRIC" 2>>"$STDERR_LOG" | tee -a "$STDOUT_LOG"
echo "reward=$(cat /logs/verifier/reward.txt 2>/dev/null)" | tee -a "$STDOUT_LOG"
