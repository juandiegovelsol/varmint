#!/usr/bin/env bash
# Oracle solution: apply the human developer's fix (source files only; no test files).
# Fixes ihhub/fheroes2 issue #4924: right-click on icon areas in the scenario selection
# dialog incorrectly triggers the file-location/map-type popup instead of being a no-op.
# PR #4929: adds mapNames rect, makes ActionListPressRight a no-op, reorders event handlers.
set -euxo pipefail
cd /app

apply_if_nonempty() {
    local p="$1"
    if [ -f "$p" ] && grep -q '[^[:space:]]' "$p"; then
        git apply "$p" 2>/dev/null || patch -p1 < "$p"
    fi
}

apply_if_nonempty /solution/fix.patch
echo "Applied fix.patch."
