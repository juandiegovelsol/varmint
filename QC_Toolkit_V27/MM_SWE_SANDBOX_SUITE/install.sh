#!/usr/bin/env bash
# Install BOTH MM SWE sandbox skills and all six slash commands into ~/.claude/.
#
#   bash install.sh                  # install to $HOME/.claude
#   CLAUDE_DIR=/path bash install.sh
#
# The two are designed to work together: `mm_run.sh <task> check` runs the QC audit as a
# pre-flight before spending a credentialed run. Installing both is what makes that gate live.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${CLAUDE_DIR:-$HOME/.claude}"
[ -d "$HERE/skills/mm-swe-qc-fix-sandbox" ] && [ -d "$HERE/skills/mmswe-runner" ] \
  || { echo "run install.sh from inside the suite folder" >&2; exit 1; }

mkdir -p "$DEST/skills" "$DEST/commands"
for s in mm-swe-qc-fix-sandbox mmswe-runner; do
  rm -rf "$DEST/skills/$s"
  cp -R "$HERE/skills/$s" "$DEST/skills/"
done
# skip empty command stubs rather than installing a 0-byte slash command
for f in "$HERE"/commands/*.md; do [ -s "$f" ] && install -m 644 "$f" "$DEST/commands/"; done

find "$DEST/skills/mm-swe-qc-fix-sandbox" "$DEST/skills/mmswe-runner" \
     \( -name '__pycache__' -o -name '*.pyc' -o -name '.DS_Store' \) -exec rm -rf {} + 2>/dev/null || true
chmod +x "$DEST/skills/mm-swe-qc-fix-sandbox/fix.py" \
         "$DEST/skills/mm-swe-qc-fix-sandbox/checks/qc_env_probe.sh" \
         "$DEST/skills/mmswe-runner/mm_run.sh" \
         "$DEST/skills/mmswe-runner/sandbox_proxy_bridge.py" 2>/dev/null || true
find "$DEST/skills/mm-swe-qc-fix-sandbox" "$DEST/skills/mmswe-runner" -type f -exec chmod a+r {} + 2>/dev/null || true

echo "installed:"
echo "  $DEST/skills/mm-swe-qc-fix-sandbox/     -> /qc-fix-sandbox"
echo "  $DEST/skills/mmswe-runner/              -> /run-{oracle,nop,trial,pseudo-trial,check,analyze}"
echo
echo "  /run-pseudo-trial re-scores a recorded trial's submission against edited tests,"
echo "  with no model call. It needs the submission-capture block in tests/test.sh --"
echo "  /run-check reports when a task lacks it and fix.py wires it in."
echo
echo "No API key needed for the audit, oracle or nop. The trial, check and analyze need"
echo "credentials and go through the anonymizer proxy. The audit's instruction read uses the"
echo "proxy too when it is up, and falls back to a phrase scan when it is not (MM_QC_LLM=0 forces that)."
echo
echo "smoke test:"
echo "  python3 $DEST/skills/mm-swe-qc-fix-sandbox/fix.py qc /home/sandbox"
echo "  bash    $DEST/skills/mmswe-runner/mm_run.sh --help"
