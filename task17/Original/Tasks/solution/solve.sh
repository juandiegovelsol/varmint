#!/usr/bin/env bash
# Oracle solution: apply the human developer's fix (source files only; no test files).
# If the image applied Appendix-I rename (collectSheetRules), reverse it with git mv
# so the rename stays tracked and judge `git diff harbor_base` still sees the fix.
set -euxo pipefail
cd /app

if [ -f src/parser/collectSheetRules.ts ] && [ ! -f src/parser/getCSSRules.ts ]; then
  git mv src/parser/collectSheetRules.ts src/parser/getCSSRules.ts
  if [ -f src/parser/ruleSelectorTest.ts ] && [ ! -f src/parser/selectorMatches.ts ]; then
    git mv src/parser/ruleSelectorTest.ts src/parser/selectorMatches.ts
  fi
  python3 /solution/unobfuscate_for_fix.py
fi

apply_if_nonempty() {
  local p="$1"
  if [ -f "$p" ] && grep -q '[^[:space:]]' "$p"; then
    git apply "$p" 2>/dev/null || patch -p1 < "$p"
  fi
}

apply_if_nonempty /solution/fix.patch
echo "Applied fix.patch."
