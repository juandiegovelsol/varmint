#!/usr/bin/env bash
# Installs the sandbox QC-FIX skill into ~/.claude/ . No API key is required to use it.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -d "$here/skills/mm-swe-qc-fix-sandbox" ] || { echo "run install.sh from inside the folder" >&2; exit 1; }

mkdir -p "$HOME/.claude/skills" "$HOME/.claude/commands"
rm -rf "$HOME/.claude/skills/mm-swe-qc-fix-sandbox"
cp -R "$here/skills/mm-swe-qc-fix-sandbox" "$HOME/.claude/skills/mm-swe-qc-fix-sandbox"
for f in "$here"/commands/*.md; do [ -s "$f" ] && install -m 644 "$f" "$HOME/.claude/commands/"; done
find "$HOME/.claude/skills/mm-swe-qc-fix-sandbox" \( -name '.DS_Store' -o -name '__pycache__' \) -exec rm -rf {} + 2>/dev/null || true
chmod a+rX "$HOME/.claude/skills/mm-swe-qc-fix-sandbox" 2>/dev/null || true
find "$HOME/.claude/skills/mm-swe-qc-fix-sandbox" -type f -exec chmod a+r {} + 2>/dev/null || true
chmod a+rx "$HOME/.claude/skills/mm-swe-qc-fix-sandbox/fix.py" \
           "$HOME/.claude/skills/mm-swe-qc-fix-sandbox/runner/mm_run.sh" 2>/dev/null || true

echo "Installed:"
echo "  skill    -> ~/.claude/skills/mm-swe-qc-fix-sandbox/"
echo "  command  -> /qc-fix-sandbox"
echo
echo "No API key needed. Harbor runs go through the MM SWE runner;"
echo "a copy WITH rescore ships in runner/ if none is installed."
