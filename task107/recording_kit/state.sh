#!/bin/bash
# state.sh "<bug numbers>|all|none" [fixorig] : reset src/, apply the chosen bug patches from /kit/bugs,
# optionally the upstream fix (fix_orig.patch, base-relative), and rebuild DDNet + DDNet-Server.
set -e
cd /app
git checkout -q -- src
SEL="$1"
for p in /kit/bugs/bug_*.patch; do
  n=$(basename "$p" .patch); n=${n#bug_0}
  if [ "$SEL" = all ] || [[ " $SEL " == *" $n "* ]]; then git apply "$p"; echo "applied $p"; fi
done
if [ "$2" = fixorig ]; then
  # the upstream fix is relative to base; undo the bug hunks it overlaps first (bugs 3+4 live in
  # the function it rewrites), then apply it
  for p in /kit/bugs/bug_03.patch /kit/bugs/bug_04.patch; do git apply -R --check "$p" 2>/dev/null && git apply -R "$p" && echo "reverted $p for fix"; done
  git apply /kitsrc/fix_orig.patch && echo "applied upstream fix"
fi
cd build && ninja DDNet DDNet-Server 2>&1 | grep -E "error|FAILED|Linking" | head -20
