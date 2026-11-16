#!/bin/bash
# mkbundle.sh CLONE KIT OUTDIR : writes OUTDIR/test.patch and OUTDIR/fix.patch (run in Git Bash; rtk-free raw git)
set -euo pipefail
C="$1"; K="$2"; O="$3"
BASE=041d67cecad21b8cea26b74d8d0faaf0f58b138b
mkdir -p "$O"
cd "$C"
git config core.autocrlf false
git checkout -q -f "$BASE"; git clean -fdq
# --- test.patch: only the hidden test files, vs base
mkdir -p tests
cp -r "$K/probe/tests/harvest_c01" tests/
git add -N tests/harvest_c01
git diff --binary "$BASE" -- tests/harvest_c01 > "$O/test.patch"
git reset -q; rm -rf tests/harvest_c01; git clean -fdq
# --- fix.patch: buggy baseline (base + bugs) -> upstream fix + every injected bug reverted
git apply --index "$K"/bugs/*.patch
git -c user.email=h@l -c user.name=h commit -qm buggy-baseline
git checkout -q "$BASE" -- src irr
git apply --index "$K/fix_orig.patch"
git diff --binary HEAD > "$O/fix.patch"
git reset -q --hard; git checkout -q -f "$BASE"; git clean -fdq
git branch -D tmp 2>/dev/null || true
echo "test.patch: $(grep -c '^diff --git' "$O/test.patch") files; fix.patch: $(grep '^diff --git' "$O/fix.patch" | sed 's#.* b/##' | tr '\n' ' ')"
