#!/usr/bin/env bash
# Behavioral verifier for fabricjs__fabric.js-10640-mm
# Resets every scored test path from harbor_base, applies test.patch
# (which carries the behavioral f2p tests), runs ONLY the f2p + p2p
# tests, computes reward from the JUnit report.
# NEVER greps source for the fix.
set -uo pipefail

# Ensure python3 is available for the reward parser (test-only dep,
# installed here rather than baked into the agent-facing image).
if ! command -v python3 >/dev/null 2>&1; then
    apt-get update >/dev/null 2>&1 \
        && apt-get install -y --no-install-recommends python3 >/dev/null 2>&1 \
        || { echo "ERROR: cannot install python3 for verifier" >&2; exit 1; }
fi

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

# Step 1: reset test files from harbor_base.
# Paths come from BOTH the test.patch headers (covers new-file, binary and
# rename diffs, which have no usable '+++ b/' line) AND config.json
# test_files, so a scored file the patch does not touch is still restored.
# Files that do not exist at harbor_base (the added spec) are deleted here
# and recreated by test.patch in step 2 — so agent edits to any scored test
# cannot affect scoring, and the reset is idempotent across re-runs.
echo "== resetting test files ==" | tee -a "$STDOUT_LOG"
_patch_paths=$(
  { sed -n 's#^diff --git a/\(.*\) b/.*#\1#p' /tests/test.patch
    sed -n 's#^diff --git a/.* b/\(.*\)#\1#p' /tests/test.patch
    python3 -c "import json,sys; print('\n'.join(json.load(open('/tests/config.json'))['test_files']))"
  } | sort -u )
for _p in $_patch_paths; do
    git -C /app checkout harbor_base -- "$_p" 2>/dev/null \
        || rm -f "/app/$_p" 2>/dev/null || true
done

# Step 2: apply test.patch (existing-file hardening + the added f2p spec)
echo "== applying test.patch ==" | tee -a "$STDOUT_LOG"
git apply --binary /tests/test.patch 2>>"$STDERR_LOG" \
    || git apply /tests/test.patch 2>>"$STDERR_LOG" \
    || patch -p1 -i /tests/test.patch 2>>"$STDERR_LOG" \
    || { echo "ERROR: could not apply test.patch" | tee -a "$STDERR_LOG"; exit 1; }

# Step 3: run ONLY the scored tests (f2p + p2p), by name.
echo "== running vitest tests ==" | tee -a "$STDOUT_LOG"
NAME_FILTER=$(python3 -c "
import json, re
c = json.load(open('/tests/config.json'))
print('|'.join(re.escape(n) for n in c['f2p'] + c['p2p']))
" 2>>"$STDERR_LOG")

if [ -n "${NAME_FILTER:-}" ]; then
    set -- -t "$NAME_FILTER"
else
    echo "WARN: empty name filter, running full test files" | tee -a "$STDERR_LOG"
    set --
fi

npx vitest run \
    --project unit-node \
    --reporter=junit \
    --outputFile.junit="$REPORT" \
    --passWithNoTests \
    "$@" \
    'src/shapes/Text/Text.spec.ts' \
    'src/shapes/Text/TextSVGExportMixin.spec.ts' \
    'src/shapes/Text/f2p_additions.spec.ts' \
    >>"$STDOUT_LOG" 2>>"$STDERR_LOG" \
    || echo "(vitest exited non-zero; parsing report)" | tee -a "$STDOUT_LOG"

# Step 4: compute reward
echo "== computing reward ==" | tee -a "$STDOUT_LOG"
python3 /tests/verifier.py 2>>"$STDERR_LOG" | tee -a "$STDOUT_LOG"
echo "reward=$(cat /logs/verifier/reward.txt 2>/dev/null)" | tee -a "$STDOUT_LOG"
