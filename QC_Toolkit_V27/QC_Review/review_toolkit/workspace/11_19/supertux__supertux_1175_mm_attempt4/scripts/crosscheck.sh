#!/usr/bin/env bash
# crosscheck.sh <plan: loo|only>  -- runs inside the task image (buggy /app); /tests /solution /parts ro, /out rw
set -u
plan="$1"; cd /app
summ=/out/$plan.summary.txt; : > "$summ"
git apply /tests/test.patch || { echo "test.patch FAILED" >> "$summ"; exit 1; }
export SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy ALSOFT_DRIVERS=null
IDS=$(python3 -c "import json;c=json.load(open('/tests/config.json'));print(' '.join(t.split()[-1] for t in c['f2p']+c['p2p']))")
build_and_run() {
  local label="$1"
  if ! cmake --build /app/build -j4 --target supertux2 > "/out/$label.build.log" 2>&1; then echo "$label: BUILD FAILED" >> "$summ"; return; fi
  python3 /app/tests/run_hazard_test.py /app/build/supertux2 /app/tests/fixtures/hazards "/out/$label.xml" $IDS > /dev/null 2>&1
  python3 - "$label" "/out/$label.xml" >> "$summ" <<'PY'
import sys, xml.etree.ElementTree as ET
r = ET.parse(sys.argv[2]).getroot()
bad = [tc.get("name") for tc in r.iter("testcase") if any(c.tag in ("failure", "error") for c in tc)]
print(f"{sys.argv[1]}: tests={r.get('tests')} failed={len(bad)} {bad}")
PY
}
ap() { git apply "/parts/$1.patch" || { echo "apply $1 FAILED" >> "$summ"; return 1; }; }
rv() { git apply -R "/parts/$1.patch" || { echo "revert $1 FAILED" >> "$summ"; return 1; }; }
PARTS=$(cd /parts && ls *.patch | sed 's/\.patch$//')
case "$plan" in
  loo) for p in $PARTS; do for q in $PARTS; do [ "$q" = "$p" ] || ap "$q"; done; build_and_run "all_but_$p"; for q in $PARTS; do [ "$q" = "$p" ] || rv "$q"; done; done ;;
  only) git apply --check /solution/fix.patch && echo "git apply --check fix.patch at harbor_base: OK" >> "$summ"
        for p in $PARTS; do ap "$p" && { build_and_run "only_$p"; rv "$p"; }; done ;;
esac
echo "done $plan" >> "$summ"
