#!/usr/bin/env bash
# Oracle solution: apply the human developer's fix (source files only; no test files).
set -euxo pipefail
cd /app

apply_if_nonempty() {
  local p="$1"
  if [ ! -f "$p" ] || ! grep -q '[^[:space:]]' "$p"; then
    return 0
  fi

  if ! git apply "$p" 2>/dev/null; then
    # `patch` is kept as a whitespace-tolerant fallback, but unlike `git apply`
    # it is NOT atomic: it can apply some hunks and reject others, leaving a
    # half-fixed tree whose reward is indistinguishable from a genuine failure.
    # The post-condition below is what actually decides success.
    patch -p1 --forward < "$p" || true
  fi

  # `git apply --reverse --check` succeeds only when EVERY hunk is already
  # present, so it is an exact test for "the patch applied completely".
  if ! git apply --reverse --check "$p" 2>/dev/null; then
    set +x
    echo "FATAL: $p did not apply completely."
    echo "The working tree does not match the state this patch expects."
    echo "fix.patch and environment/assets/bugs/*.patch are a matched pair, regenerated"
    echo "together: the bug patch's 'index a..b' must mirror the fix patch's 'index b..a'"
    echo "for the same file. If only one was synced they disagree about harbor_base."
    echo "Sync the stale one, rebuilding the image only if it is the bug patch that moved."
    find /app -name '*.rej' -print 2>/dev/null || true
    exit 1
  fi
}

apply_if_nonempty /solution/fix.patch
echo "Applied fix.patch."
