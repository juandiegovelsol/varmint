#!/usr/bin/env bash
# Oracle solution: apply the reference fix (source files only; never test files).
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
