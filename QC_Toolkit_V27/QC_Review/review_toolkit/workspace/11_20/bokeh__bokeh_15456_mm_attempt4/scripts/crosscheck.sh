#!/usr/bin/env bash
# In-container: golden fix applied, then re-break ONE part at a time (bug patch / part-1 reverse),
# run the verifier, record per-test results, restore. Never touches the CB's files.
set -u
cd /app
git apply /solution/fix.patch || exit 1
cat > /tmp/part1.patch <<'P'
diff --git a/bokehjs/src/lib/models/layouts/flex_box.ts b/bokehjs/src/lib/models/layouts/flex_box.ts
--- a/bokehjs/src/lib/models/layouts/flex_box.ts
+++ b/bokehjs/src/lib/models/layouts/flex_box.ts
@@ -22,13 +22,6 @@ export abstract class FlexBoxView extends LayoutDOMView {
     return this.model.children
   }
 
-  override measure_layout(): void {
-    if (this.layout instanceof GridAlignmentLayout) {
-      this.layout.align_borders()
-    }
-    super.measure_layout()
-  }
-
   override _update_layout(): void {
     super._update_layout()
 
P
for k in part1:/tmp/part1.patch part2:/bugs/bug_01.patch part3:/bugs/bug_02.patch part4:/bugs/bug_03.patch part5:/bugs/bug_04.patch part6:/bugs/bug_05.patch; do
  n=${k%%:*}; p=${k#*:}
  git apply "$p" || { echo "$n: apply failed" >> /out/summary.txt; continue; }
  bash /tests/test.sh > /out/$n.console.txt 2>&1
  mkdir -p /out/$n; cp /logs/verifier/junit.xml /logs/verifier/reward.txt /out/$n/ 2>/dev/null
  python3 - "$n" <<'PY' >> /out/summary.txt
import sys, json, xml.etree.ElementTree as ET
n = sys.argv[1]; cfg = json.load(open("/tests/config.json"))
res = {}
for tc in ET.parse("/logs/verifier/junit.xml").getroot().iter("testcase"):
    res[tc.get("name")] = "fail" if any(c.tag in ("failure", "error") for c in tc) else "pass"
fails = [("f2p" if t in cfg["f2p"] else "p2p") + ": " + t for t in cfg["f2p"] + cfg["p2p"] if res.get(t) != "pass"]
print(json.dumps({"state": "golden minus " + n, "reward": open("/logs/verifier/reward.txt").read().strip(), "failing": fails}))
PY
  git apply -R "$p" || { echo "$n: restore failed" >> /out/summary.txt; exit 1; }
done
echo DONE >> /out/summary.txt
