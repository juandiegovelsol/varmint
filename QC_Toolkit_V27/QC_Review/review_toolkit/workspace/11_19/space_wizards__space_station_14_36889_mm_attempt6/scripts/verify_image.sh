#!/usr/bin/env bash
# Runs in a throwaway container: proves the image's /app = base commit + exactly the Attempt6 bugs.
cd /app
echo "harbor_base tag: $(git rev-parse --short harbor_base 2>&1)"; echo "status lines: $(git status --porcelain | wc -l)"
echo "asset sha256: $(sha256sum /app/.harbor_assets/recording.mp4 | cut -c1-16)"
for p in $(ls /bugs/*.patch | sort -r); do
  if git apply -R "$p" 2>/tmp/e; then echo "reverse OK  $(basename $p)"; else echo "reverse FAIL $(basename $p): $(cat /tmp/e)"; fi
done
# After reversing all bugs, every touched file must hash to the upstream 'index <old>' blob of the first bug touching it
for p in $(ls /bugs/*.patch | sort); do
  f=$(sed -n 's#^diff --git a/\(.*\) b/.*#\1#p' "$p" | head -1); old=$(sed -n 's/^index \([0-9a-f]*\)\.\..*/\1/p' "$p" | head -1)
  echo "$(basename $p) $f upstream=$old now=$(git hash-object "$f" | cut -c1-${#old})"
done
git apply --check /solution/fix.patch 2>&1 && echo "NOTE: fix applies on fully-reverted tree (unexpected)" || true
