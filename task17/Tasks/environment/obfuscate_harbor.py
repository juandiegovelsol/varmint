"""Harbor-base localization hardening. Runs once during image build; deleted after.
Reversible by solution/solve.sh so upstream fix.patch still applies.
Expects CWD /app (Docker WORKDIR).
"""
from pathlib import Path

root = Path.cwd()
src = root / "src/parser/getCSSRules.ts"
dst = root / "src/parser/collectSheetRules.ts"
text = src.read_text(encoding="utf-8")
old = """/**
 * Returns CSS rules for a given SVG document
 * @param {HTMLElement} doc SVG document to parse
 * @return {Object} CSS rules of this document
 */
export function getCSSRules"""
new = """/**
 * Build a selector-to-declaration map from the document.
 * @param {Document} doc
 * @return {Object}
 */
export function collectSheetRules"""
if old not in text:
    raise SystemExit("expected getCSSRules JSDoc/export not found")
dst.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
src.unlink()

ep = root / "src/parser/elements_parser.ts"
et = ep.read_text(encoding="utf-8")
et = et.replace(
    "import { getCSSRules } from './getCSSRules';",
    "import { collectSheetRules } from './collectSheetRules';",
)
et = et.replace(
    "this.cssRules = getCSSRules(doc);",
    "this.cssRules = collectSheetRules(doc);",
)
if "collectSheetRules" not in et:
    raise SystemExit("elements_parser rewrite failed")
ep.write_text(et, encoding="utf-8", newline="\n")

ep.rename(root / "src/parser/svgTreeRead.ts")

psd = root / "src/parser/parseSVGDocument.ts"
ps = psd.read_text(encoding="utf-8")
ps = ps.replace(
    "import { ElementsParser } from './elements_parser';",
    "import { ElementsParser } from './svgTreeRead';",
)
if "./svgTreeRead" not in ps:
    raise SystemExit("parseSVGDocument rewrite failed")
psd.write_text(ps, encoding="utf-8", newline="\n")

# Rename the selector-test helper (selectorMatches) so the multi-class matching
# path can't be fingerprinted by name. File + symbol + importers all move.
sm = root / "src/parser/selectorMatches.ts"
smt = sm.read_text(encoding="utf-8")
smt = smt.replace(
    "export function selectorMatches",
    "export function ruleSelectorTest",
    1,
)
if "ruleSelectorTest" not in smt:
    raise SystemExit("selectorMatches symbol rename failed")
(root / "src/parser/ruleSelectorTest.ts").write_text(
    smt, encoding="utf-8", newline="\n"
)
sm.unlink()

for name in ("elementMatchesRule.ts", "doesSomeParentMatch.ts"):
    p = root / "src/parser" / name
    t = p.read_text(encoding="utf-8")
    t = t.replace(
        "import { selectorMatches } from './selectorMatches';",
        "import { ruleSelectorTest } from './ruleSelectorTest';",
    )
    t = t.replace("selectorMatches(", "ruleSelectorTest(")
    if "ruleSelectorTest" not in t:
        raise SystemExit(f"{name} rewrite failed")
    p.write_text(t, encoding="utf-8", newline="\n")

print("obfuscation ok")
