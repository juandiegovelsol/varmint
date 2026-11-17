import sys, pathlib
ROOT = pathlib.Path(sys.argv[1])
R = 'packages/desktop-client/src/components/reports/'
EDITS = {
 # bug_01: weekly interval bounds (table rows + chart intervals)
 R+'spreadsheets/recalculate.ts': [(
"""        intervalStartDate: index === 0 ? startDate : intervalItem,
        intervalEndDate:
          index + 1 === intervals.length
            ? endDate
            : monthUtils.subDays(intervals[index + 1], 1),
""",
"""        intervalStartDate: intervalItem,
        intervalEndDate:
          index + 1 === intervals.length
            ? endDate
            : monthUtils.dayFromDate(intervals[index + 1]),
""")],
 R+'spreadsheets/custom-spreadsheet.ts': [(
"""          intervalStartDate: index === 0 ? startDate : intervalItem,
          intervalEndDate:
            index + 1 === intervals.length
              ? endDate
              : monthUtils.subDays(intervals[index + 1], 1),
""",
"""          intervalStartDate: intervalItem,
          intervalEndDate:
            index + 1 === intervals.length
              ? endDate
              : monthUtils.dayFromDate(intervals[index + 1]),
"""),
 # bug_05 (part): per-interval series keyed by display name
 (
"""          // Use id as key to prevent collisions when categories have the same name
          stacked[item.id || item.name] = stackAmounts;
""",
"""          stacked[item.name || item.id] = stackAmounts;
""")],
 # bug_02: Uncategorized row also absorbs uncategorized transfers
 R+'spreadsheets/filterHiddenItems.ts': [(
"""      case 'other':
        return !isOffBudget && !isTransfer;
""",
"""      case 'other':
        return !isOffBudget && !hasCategory;
""")],
 # bug_03: empty-row filter looks at any activity instead of the chosen balance type
 R+'spreadsheets/filterEmptyRows.ts': [(
"""  if (balanceTypeOp === 'totalTotals' || balanceTypeOp === 'totalBudgeted') {
    showHide =
      data['totalDebts'] !== 0 ||
      data['totalAssets'] !== 0 ||
      data[balanceTypeOp] !== 0;
  } else {
    showHide = data[balanceTypeOp] !== 0;
  }
""",
"""  if (balanceTypeOp === 'netAssets' || balanceTypeOp === 'netDebts') {
    showHide = data[balanceTypeOp] !== 0;
  } else {
    showHide =
      data['totalDebts'] !== 0 ||
      data['totalAssets'] !== 0 ||
      data[balanceTypeOp] !== 0;
  }
""")],
 # bug_04: time-mode drilldowns lose the inflow/outflow criterion
 R+'graphs/showActivity.ts': [(
"""    !(
      ['netAssets', 'netDebts'].includes(balanceTypeOp) ||
      (['totalTotals', 'totalBudgeted'].includes(balanceTypeOp) &&
        (type === 'totals' || type === 'time'))
    ) && {
""",
"""    !(
      ['netAssets', 'netDebts'].includes(balanceTypeOp) ||
      (['totalTotals', 'totalBudgeted'].includes(balanceTypeOp) &&
        type === 'totals') ||
      type === 'time'
    ) && {
""")],
 # bug_05 (part): legend series key
 R+'spreadsheets/calculateLegend.ts': [(
"""      dataKey: item.id || item.name || '', // Use id for unique data lookup
""",
"""      dataKey: item.name || item.id || '',
""")],
 'packages/loot-core/src/types/models/reports.ts': [(
"""  dataKey: string; // Uses id for unique data lookup when categories have same name
""",
"""  dataKey: string;
""")],
}
for rel, pairs in EDITS.items():
    p = ROOT / rel
    t = p.read_text(encoding='utf-8')
    for old, new in pairs:
        n = t.count(old)
        assert n == 1, (rel, n, old[:60])
        t = t.replace(old, new)
    p.write_bytes(t.encode('utf-8'))
    print('ok', rel)
