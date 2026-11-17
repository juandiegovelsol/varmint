import json, sys, re
T = sys.argv[1]
V = 'custom report drilldowns from every view (#7999) > '
D = 'custom report data (weekly deposits by category) > '
G = 'custom report (regression guards) > '
I = 'showActivity invariants (regression guards) > '
F2P = [V + n for n in [
  'bar chart: the Transfers bar opens only the transfers of the report period',
  'donut chart: the Transfers slice opens only the transfers of the report period',
  'category+group donut: the Transfers slice opens only the transfers of the report period',
  'stacked bar chart: a Transfers segment opens only the transfers of that week',
  'line chart: a Transfers point opens only the transfers of that week',
  'table: a Transfers cell opens only the transfers of that week, and its total the whole period',
  'table built from category groups: a Transfers cell opens only the transfers of that week',
  'net report table: the Transfers deposits and payments cells open only incoming and outgoing transfers',
  'payment report: the Transfers bar opens only the outgoing transfers',
  'the Transfers row is recognised whatever its label reads',
]] + [D + n for n in [
  'counts every deposit exactly once, in the rows and in the report totals',
  'table grouped by category group: counts every deposit exactly once',
  'lists only rows that have an amount for the selected report type',
  'table grouped by category group: lists only rows that have an amount for the selected report type',
  'draws every chart series from its own row, even when categories share a name',
  'drills a weekly table cell into exactly that week, inside the report range',
  'drills a weekly chart segment into exactly that week, inside the report range',
  'keeps the deposit criterion on a weekly drilldown of a deposit report',
  'keeps the payment criterion on a weekly drilldown of a payment report',
]]
P2P = [G + n for n in [
  'every view still drills a regular category into that category',
  'still lists empty rows when the report asks for them',
  'still lists every row with any activity in a net report',
  'adds no amount criterion to a weekly drilldown of a net report',
]] + [I + n for n in [
  'keeps the category filter for regular categories',
  'does not add a transfer filter for the other virtual categories (Uncategorized/Off budget)',
  'does not add a transfer filter when the drilldown field is not category',
  'still supports array ids with the oneOf operator for regular categories',
  'keeps the hidden-category and off-budget guards, and adds no amount criterion where the report type has none',
  'keeps sending a budgeted report to the budget view',
  'keeps the interval-based date handling for time reports',
]]
allnames = F2P + P2P
assert len(set(allnames)) == len(allnames)
for a in allnames:
    for b in allnames:
        assert a == b or a not in b, (a, b)
cfg = json.load(open(f'{T}/tests/config.json', encoding='utf-8'))
cfg['test_files'] = [
  'packages/desktop-client/src/components/reports/customReport.test.tsx',
  'packages/desktop-client/src/components/reports/graphs/showActivity.test.ts',
]
cfg['f2p'] = F2P; cfg['p2p'] = P2P
open(f'{T}/tests/config.json', 'w', encoding='utf-8', newline='\n').write(json.dumps(cfg, indent=2) + '\n')
t = open(f'{T}/task.toml', encoding='utf-8').read()
def arr(xs): return '[\n' + ''.join('  ' + json.dumps(x) + ',\n' for x in xs).rstrip(',\n') + '\n]'
t = re.sub(r'(?ms)^f2p = \[.*?^\]', lambda m: 'f2p = ' + arr(F2P), t)
t = re.sub(r'(?ms)^p2p = \[.*?^\]', lambda m: 'p2p = ' + arr(P2P), t)
open(f'{T}/task.toml', 'w', encoding='utf-8', newline='\n').write(t)
print(len(F2P), len(P2P))
