#!/usr/bin/env bash
# usage: vt.sh <test path relative to desktop-client> [junit-out]
S="C:/Users/JUANV~1/AppData/Local/Temp/claude/ba687bfd8aae2151/00e52964-f6a5-4ee6-8809-6c0db154326b/scratchpad"
cd "$S/actual/packages/desktop-client" || exit 1
OUT="${2:-$S/tools/report.xml}"
PATH="$S/tools/stub:$PATH" node ../../node_modules/vitest/vitest.mjs run --reporter=default --reporter=junit --outputFile.junit="$OUT" "$1" 2>&1 | tail -60
