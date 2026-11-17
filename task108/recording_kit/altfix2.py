import sys, pathlib
ROOT = pathlib.Path(sys.argv[1]); G='packages/desktop-client/src/components/reports/'
def ed(rel, old, new):
    p = ROOT/rel; t = p.read_text(encoding='utf-8'); assert t.count(old)==1,(rel,old); p.write_bytes(t.replace(old,new).encode('utf-8'))
ed(G+'spreadsheets/recalculate.ts', "    id: item.id || '',\n", "    id: item.id || (item.uncategorized_id ? `virtual-${item.uncategorized_id}` : ''),\n")
ed(G+'graphs/showActivity.ts', "      : id && {\n", "      : id &&\n        !String(id).startsWith('virtual-') && {\n")
print('sentinel-id variant applied')
ed(G+'spreadsheets/custom-spreadsheet.ts', "          stacked[item.id ? item.id : `virtual:${item.name}`] = stackAmounts;\n",
   "          stacked[\n            item.id ||\n              (item.uncategorized_id\n                ? `virtual-${item.uncategorized_id}`\n                : `virtual:${item.name}`)\n          ] = stackAmounts;\n")
print('stacked key aligned')
