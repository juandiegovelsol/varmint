#!/usr/bin/env bash
# Installs the mmswe-runner skill and its slash commands into ~/.claude/ (personal scope).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -d "$here/skills/mmswe-runner" ] || [ ! -d "$here/commands" ]; then
  echo "error: expected 'skills/' and 'commands/' next to install.sh." >&2
  echo "       Unzip the archive and run install.sh from inside the extracted folder." >&2
  exit 1
fi

mkdir -p "$HOME/.claude/skills" "$HOME/.claude/commands"
rm -rf "$HOME/.claude/skills/mmswe-runner"
cp -R "$here/skills/mmswe-runner" "$HOME/.claude/skills/mmswe-runner"

# Use `install -m 644` rather than `cp` for the commands. A plain cp onto a file that
# does NOT already exist creates it owned by the installing user with the source's
# mode — in a sandbox where the package is owned by `cb` but ~/.claude is owned by
# `sandbox`, that lands mode 0660/other=--- and the command loader can't read it, so
# the command silently never appears. `install -m 644` sets the mode explicitly every
# time, for new and existing files alike.
for f in "$here"/commands/*.md; do
  case "$(basename "$f")" in run-all.md) continue;; esac   # retired
  [ -s "$f" ] && install -m 644 "$f" "$HOME/.claude/commands/"
done

find "$HOME/.claude/skills/mmswe-runner" \( -name '.DS_Store' -o -name '__pycache__' \) -exec rm -rf {} + 2>/dev/null || true

# Same reasoning for the skill payload: readable by anyone, scripts executable.
chmod a+rX "$HOME/.claude/skills/mmswe-runner" 2>/dev/null || true
find "$HOME/.claude/skills/mmswe-runner" -type f -exec chmod a+r {} + 2>/dev/null || true
chmod a+rx "$HOME/.claude/skills/mmswe-runner/mm_run.sh" \
            "$HOME/.claude/skills/mmswe-runner/sandbox_proxy_bridge.py" 2>/dev/null || true

# Report anything the loader still can't read, instead of failing silently.
for f in "$HOME/.claude/commands"/run-oracle.md "$HOME/.claude/commands"/run-nop.md \
         "$HOME/.claude/commands"/run-trial.md "$HOME/.claude/commands"/run-check.md \
         "$HOME/.claude/commands"/run-analyze.md; do
  [ -f "$f" ] || continue
  case "$(stat -c '%A' "$f" 2>/dev/null || stat -f '%Sp' "$f" 2>/dev/null)" in
    *r--|*r-x|*rw-|*rwx) ;;
    *) echo "warning: $f may not be readable by the command loader ($(ls -l "$f"))" >&2;;
  esac
done

echo "Installed:"
echo "  skill    -> ~/.claude/skills/mmswe-runner/"
echo "  commands -> ~/.claude/commands/ ($(cd "$here/commands" && ls *.md | grep -v '^run-all.md$' | sed 's/\.md$//' | sed 's/^/\//' | paste -sd ' ' -))"
