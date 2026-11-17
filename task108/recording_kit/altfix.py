import sys, pathlib, re
ROOT = pathlib.Path(sys.argv[1]); G='packages/desktop-client/src/components/reports/'
def ed(rel, pairs):
    p = ROOT/rel; t = p.read_text(encoding='utf-8')
    for old, new, n in pairs:
        c = t.count(old); assert c == n, (rel, c, old[:60]); t = t.replace(old, new)
    p.write_bytes(t.encode('utf-8'))
# types
ed('packages/loot-core/src/types/models/reports.ts', [
 ("  dataKey: string;\n", "  dataKey: string;\n  isTransferRow?: boolean;\n", 1),
 ("export type GroupedEntity = {\n  id: string;\n  name: string;\n", "export type GroupedEntity = {\n  id: string;\n  name: string;\n  isTransferRow?: boolean;\n", 1)])
# pipeline: bounds (alt formula), marker as boolean
ed(G+'spreadsheets/recalculate.ts', [
 ("        intervalStartDate: intervalItem,\n", "        intervalStartDate: monthUtils.isBefore(intervalItem, startDate)\n          ? startDate\n          : intervalItem,\n", 1),
 ("            : monthUtils.dayFromDate(intervals[index + 1]),\n", "            : monthUtils.addDays(intervals[index + 1], -1),\n", 1),
 ("    name: item.name,\n    totalAssets,", "    name: item.name,\n    ...(item.uncategorized_id === 'transfer' && { isTransferRow: true }),\n    totalAssets,", 1)])
ed(G+'spreadsheets/custom-spreadsheet.ts', [
 ("          intervalStartDate: intervalItem,\n", "          intervalStartDate: monthUtils.isBefore(intervalItem, startDate)\n            ? startDate\n            : intervalItem,\n", 1),
 ("              : monthUtils.dayFromDate(intervals[index + 1]),\n", "              : monthUtils.addDays(intervals[index + 1], -1),\n", 1),
 ("          stacked[item.name || item.id] = stackAmounts;\n", "          stacked[item.id ? item.id : `virtual:${item.name}`] = stackAmounts;\n", 1)])
ed(G+'spreadsheets/calculateLegend.ts', [
 ("      : calcDataFiltered.map(c => {\n          return { name: c.name, id: c.id, data: c };", "      : calcDataFiltered.map(c => {\n          return { name: c.name, id: c.id, data: c, isTransferRow: c.isTransferRow };", 1),
 ("      dataKey: item.name || item.id || '',\n", "      dataKey:\n        groupBy === 'Interval'\n          ? item.name || ''\n          : item.id\n            ? item.id\n            : `virtual:${item.name}`,\n      isTransferRow: 'isTransferRow' in item ? item.isTransferRow : undefined,\n", 1)])
ed(G+'spreadsheets/filterHiddenItems.ts', [("        return !isOffBudget && !hasCategory;\n", "        return !isOffBudget && !hasCategory && !isTransfer;\n", 1)])
ed(G+'spreadsheets/filterEmptyRows.ts', [(
"""  if (balanceTypeOp === 'netAssets' || balanceTypeOp === 'netDebts') {
    showHide = data[balanceTypeOp] !== 0;
  } else {
    showHide =
      data['totalDebts'] !== 0 ||
      data['totalAssets'] !== 0 ||
      data[balanceTypeOp] !== 0;
  }
""","""  switch (balanceTypeOp) {
    case 'totalTotals':
    case 'totalBudgeted':
      showHide =
        data.totalDebts !== 0 ||
        data.totalAssets !== 0 ||
        data[balanceTypeOp] !== 0;
      break;
    default:
      showHide = data[balanceTypeOp] !== 0;
  }
""",1)])
ed(G+'graphs/showActivity.ts', [
 ("  interval?: string;\n};", "  interval?: string;\n  transfersOnly?: boolean;\n};", 1),
 ("  interval = 'Day',\n}: showActivityProps) {", "  interval = 'Day',\n  transfersOnly = false,\n}: showActivityProps) {\n  const netLike =\n    ['netAssets', 'netDebts'].includes(balanceTypeOp) ||\n    (['totalTotals', 'totalBudgeted'].includes(balanceTypeOp) &&\n      type !== 'assets' &&\n      type !== 'debts');", 1),
 ("    id && {\n", "    transfersOnly && field === 'category'\n      ? { field: 'transfer', op: 'is', value: true }\n      : id && {\n", 1),
 ("""    !(
      ['netAssets', 'netDebts'].includes(balanceTypeOp) ||
      (['totalTotals', 'totalBudgeted'].includes(balanceTypeOp) &&
        type === 'totals') ||
      type === 'time'
    ) && {""", "    !netLike && {", 1)])
ed(G+'graphs/BarGraph.tsx', [("                    id: item.id,\n                  })\n", "                    id: item.id,\n                    transfersOnly: !!item.payload?.isTransferRow,\n                  })\n", 1)])
ed(G+'graphs/StackedBarGraph.tsx', [("                        id: entry.id,\n", "                        id: entry.id,\n                        transfersOnly: !!entry.isTransferRow,\n", 1)])
ed(G+'graphs/LineGraph.tsx', [
 ("  const onShowActivity = (item, id, payload) => {", "  const onShowActivity = (item, id, payload, transfersOnly = false) => {", 1),
 ("      id,\n      interval,\n", "      id,\n      transfersOnly,\n      interval,\n", 1),
 ("onShowActivity(e, entry.id, payload),", "onShowActivity(e, entry.id, payload, !!entry.isTransferRow),", 1)])
ed(G+'graphs/DonutGraph.tsx', [
 ("type ClickablePieItem = PieSectorDataItem & { id?: string };", "type ClickablePieItem = PieSectorDataItem & {\n  id?: string;\n  isTransferRow?: boolean;\n};", 1),
 ("                          field: 'category',\n                          id: item.id,\n", "                          field: 'category',\n                          id: item.id,\n                          transfersOnly: !!item.isTransferRow,\n", 1),
 ("                        id: groupBy === 'Group' ? groupCategoryIds : item.id,\n", "                        id: groupBy === 'Group' ? groupCategoryIds : item.id,\n                        transfersOnly: !!item.isTransferRow,\n", 1)])
ed(G+'graphs/tableGraph/ReportTableRow.tsx', [("id: item.id,\n", "id: item.id,\n                transfersOnly: !!item.isTransferRow,\n", 4)])
print('alt fix applied')
