#!/usr/bin/env bash
S="C:/Users/JUANV~1/AppData/Local/Temp/claude/ba687bfd8aae2151/00e52964-f6a5-4ee6-8809-6c0db154326b/scratchpad"
echo "=== $1"
rm -f "$S"/tools/r_*.xml
for f in src/components/reports/customReport.test.tsx src/components/reports/graphs/showActivity.test.ts; do
  bash "$S/tools/vt.sh" $f "$S/tools/r_$(basename $f).xml" >/dev/null 2>&1
done
/c/Python314/python -I "$S/tools/junit.py" "$S"/tools/r_*.xml
