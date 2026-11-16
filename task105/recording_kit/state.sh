#!/bin/bash
# state.sh buggy|fixed|<list of bug patch numbers to keep, e.g. "01 03"> [orig]
set -e
cd /app
git checkout -q harbor_base -- src
case "$1" in
  buggy) for p in /tmp/bugs/*.patch; do git apply "$p"; done ;;
  fixed) git apply /tmp/fix_orig.patch ;;
  *) for n in $1; do git apply /tmp/bugs/bug_$n.patch; done; [ "${2:-}" = fixorig ] && git apply /tmp/fix_orig.patch ;;
esac
cmake --build /app/build --parallel 16 2>&1 | tail -1
