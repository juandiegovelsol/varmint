#!/bin/bash
# mkbundle.sh OUTDIR : regenerate the deliverable patches from git (never hand-edited)
#   OUTDIR/bugs/bug_0N.patch  - good -> buggy, one per injected defect (from mkbugs.py)
#   OUTDIR/fix.patch          - buggy harbor_base (base + all bugs) -> fully fixed (upstream fix + reverse bugs)
#   OUTDIR/test.patch         - base -> base + hidden test file (test files only)
set -e
OUT=$1; mkdir -p "$OUT/bugs"
pkill -x DDNet 2>/dev/null || true; pkill -x DDNet-Server 2>/dev/null || true; pkill -x Xvfb 2>/dev/null || true
cd /app
git checkout -q base -- . 2>/dev/null || true
git reset -q --hard base && git clean -fdq -e build
python3 /kitsrc/mkbugs.py "$OUT/bugs"
# buggy baseline = what harbor_base will hold
git apply --index "$OUT"/bugs/bug_0*.patch
git -c user.email=h@l -c user.name=h commit -qm buggy-baseline
# fixes on top: undo every injected bug, then the upstream fix (base-relative)
for p in $(ls -r "$OUT"/bugs/bug_0*.patch); do git apply -R --index "$p"; done
git apply --index /kitsrc/fix_orig.patch
git diff --binary HEAD > "$OUT/fix.patch"
# the fixed tree must equal base + upstream fix exactly
git stash -q && git checkout -q base -- src && git apply --check /kitsrc/fix_orig.patch && git apply /kitsrc/fix_orig.patch \
  && git diff --quiet stash@{0} -- src && echo "fixed tree == base + upstream fix" ; git checkout -q HEAD -- src; git stash drop -q
# test.patch relative to base
git reset -q --hard base && git clean -fdq -e build
cp /kitsrc/tests/test_harvest_c01_hookline.py scripts/ && chmod 644 scripts/test_harvest_c01_hookline.py
git add -N scripts/test_harvest_c01_hookline.py
git diff --binary base -- scripts/test_harvest_c01_hookline.py > "$OUT/test.patch"
git reset -q --hard base && git clean -fdq -e build
grep '^diff --git' "$OUT/fix.patch" "$OUT/test.patch"
