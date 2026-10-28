"""Restore upstream symbol names after `git mv collectSheetRules.ts getCSSRules.ts`.
Does not rename files — solve.sh already did that with git mv so the path stays tracked.
"""
from pathlib import Path

root = Path.cwd()
dst = root / "src/parser/getCSSRules.ts"
if not dst.exists():
    raise SystemExit("expected src/parser/getCSSRules.ts after git mv")

text = dst.read_text(encoding="utf-8")
text = text.replace(
    "export function collectSheetRules",
    "export function getCSSRules",
    1,
)
dst.write_text(text, encoding="utf-8", newline="\n")

sel = root / "src/parser/selectorMatches.ts"
if sel.exists():
    stext = sel.read_text(encoding="utf-8")
    stext = stext.replace(
        "export function ruleSelectorTest",
        "export function selectorMatches",
        1,
    )
    sel.write_text(stext, encoding="utf-8", newline="\n")

for path in root.joinpath("src").rglob("*.ts"):
    raw = path.read_text(encoding="utf-8")
    new = raw.replace("from './collectSheetRules'", "from './getCSSRules'")
    new = new.replace('from "./collectSheetRules"', 'from "./getCSSRules"')
    new = new.replace("collectSheetRules", "getCSSRules")
    new = new.replace("from './ruleSelectorTest'", "from './selectorMatches'")
    new = new.replace('from "./ruleSelectorTest"', 'from "./selectorMatches"')
    new = new.replace("ruleSelectorTest", "selectorMatches")
    if new != raw:
        path.write_text(new, encoding="utf-8", newline="\n")
        print(f"rewrote {path}")

print("unobfuscation ok")
