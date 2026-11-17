import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import importlib.util
spec = importlib.util.spec_from_file_location('lib', pathlib.Path(__file__).parent/'inject_lib.py')
ROOT = pathlib.Path(sys.argv[1]); which = sys.argv[2:]
sys.argv = [sys.argv[0], str(ROOT)]
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
E = lib._UNUSED
R = 'packages/desktop-client/src/components/reports/'
CS = R+'spreadsheets/custom-spreadsheet.ts'
BUGS = {
 '01': [(R+'spreadsheets/recalculate.ts', E[R+'spreadsheets/recalculate.ts'][0]), (CS, E[CS][0])],
 '02': [(R+'spreadsheets/filterHiddenItems.ts', E[R+'spreadsheets/filterHiddenItems.ts'][0])],
 '03': [(R+'spreadsheets/filterEmptyRows.ts', E[R+'spreadsheets/filterEmptyRows.ts'][0])],
 '04': [(R+'graphs/showActivity.ts', E[R+'graphs/showActivity.ts'][0])],
 '05': [(R+'spreadsheets/calculateLegend.ts', E[R+'spreadsheets/calculateLegend.ts'][0]), (CS, E[CS][1]),
        ('packages/loot-core/src/types/models/reports.ts', E['packages/loot-core/src/types/models/reports.ts'][0])],
}
for b in which:
    for rel,(old,new) in BUGS[b]:
        p = ROOT/rel; t = p.read_text(encoding='utf-8')
        assert t.count(old)==1, (b, rel)
        p.write_bytes(t.replace(old,new).encode('utf-8'))
    print('applied bug', b)
