#!/usr/bin/env bash
# Installs the mm-swe-qc-fix skill and its slash command into ~/.claude/ (personal scope).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -d "$here/skills/mm-swe-qc-fix" ] && [ -d "$here/commands" ] || {
  echo "error: run install.sh from inside the extracted folder." >&2; exit 1; }

mkdir -p "$HOME/.claude/skills" "$HOME/.claude/commands"
rm -rf "$HOME/.claude/skills/mm-swe-qc-fix"
cp -R "$here/skills/mm-swe-qc-fix" "$HOME/.claude/skills/mm-swe-qc-fix"
for f in "$here"/commands/*.md; do
  [ -s "$f" ] && install -m 644 "$f" "$HOME/.claude/commands/"
done
find "$HOME/.claude/skills/mm-swe-qc-fix" \( -name '.DS_Store' -o -name '__pycache__' \) -exec rm -rf {} + 2>/dev/null || true
chmod a+rX "$HOME/.claude/skills/mm-swe-qc-fix" 2>/dev/null || true
find "$HOME/.claude/skills/mm-swe-qc-fix" -type f -exec chmod a+r {} + 2>/dev/null || true
chmod a+rx "$HOME/.claude/skills/mm-swe-qc-fix/fix.py" 2>/dev/null || true

echo "Installed:"
echo "  skill    -> ~/.claude/skills/mm-swe-qc-fix/"
echo "  commands -> ~/.claude/commands/ (/qc-fix)"
echo
echo "Self-contained: the QC checks ship in checks/, so nothing else is required."
