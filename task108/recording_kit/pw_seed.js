const fs = require('fs'); const path = require('path');
const { S, open, shot } = require('./pw_common');
(async () => {
  const { ctx, page } = await open();
  await page.goto('http://127.0.0.1:3001/accounts', { waitUntil: 'load', timeout: 120000 });
  await page.waitForFunction(() => !!window.$send, null, { timeout: 60000 });
  await page.waitForTimeout(3000);
  const out = await page.evaluate(async () => {
    const s = window.$send;
    const chk = await s('account-create', { name: 'Checking', balance: 0, offBudget: false });
    const sav = await s('account-create', { name: 'Savings', balance: 0, offBudget: false });
    const cats = await s('get-categories');
    const g = n => cats.grouped.find(x => x.name === n);
    const c = n => cats.list.find(x => x.name === n);
    const income = g('Income').id;
    const pay = await s('category-create', { name: 'Paycheck', groupId: income, isIncome: true });
    const intr = await s('category-create', { name: 'Interest', groupId: income, isIncome: true });
    const shop = await s('category-group-create', { name: 'Shopping', isIncome: false });
    const travel = await s('category-group-create', { name: 'Travel', isIncome: false });
    const shopRef = await s('category-create', { name: 'Refunds', groupId: shop, isIncome: false });
    const travRef = await s('category-create', { name: 'Refunds', groupId: travel, isIncome: false });
    const food = c('Food').id, bills = c('Bills').id;
    const P = {};
    for (const n of ['Acme Corp', 'FreshMart', 'Northwind Store', 'SkyHigh Airlines', 'ATM Withdrawal', 'City Bank', 'Landlord']) P[n] = await s('payee-create', { name: n });
    const payees = await s('payees-get');
    const xferSav = payees.find(p => p.transfer_acct === sav).id;
    let n = 0; const id = () => 'seed-' + (++n);
    const t = (date, amount, payee, category = null, notes = '') => ({ id: id(), account: chk, date, amount, payee, category, notes, cleared: true });
    const added = [
      t('2026-05-04', 6000, xferSav),
      t('2026-05-07', 125000, P['Acme Corp'], pay),
      t('2026-05-07', 10000, xferSav),
      t('2026-05-08', -4000, xferSav),
      t('2026-05-08', -8245, P['FreshMart'], food),
      t('2026-05-09', 3500, P['Northwind Store'], shopRef),
      t('2026-05-10', 7500, xferSav),
      t('2026-05-12', 12000, P['SkyHigh Airlines'], travRef),
      t('2026-05-14', -110000, P['Landlord'], bills),
      t('2026-05-15', -1500, P['ATM Withdrawal'], null),
      t('2026-05-19', 125000, P['Acme Corp'], pay),
      t('2026-05-20', 1850, P['Northwind Store'], shopRef),
      t('2026-05-21', -6410, P['FreshMart'], food),
      t('2026-05-25', 312, P['City Bank'], intr),
      t('2026-05-26', 10000, xferSav),
    ];
    await s('transactions-batch-update', { added });
    const rid = await s('report/create', {
      name: 'Weekly deposits', startDate: '2026-05-06', endDate: '2026-05-26', isDateStatic: true,
      dateRange: 'Last month', mode: 'time', groupBy: 'Category', interval: 'Weekly', balanceType: 'Deposit',
      sortBy: 'desc', showEmpty: false, showOffBudget: false, showHiddenCategories: false, includeCurrentInterval: true,
      showUncategorized: true, trimIntervals: false, showTrendLines: false, graphType: 'TableGraph',
      conditions: [{ field: 'account', op: 'is', value: chk, type: 'id' }], conditionsOp: 'and',
    });
    const savTx = await window.$query ? null : null;
    return { chk, sav, rid };
  });
  console.log(JSON.stringify(out));
  fs.writeFileSync(path.join(S, 'tools', 'seed.json'), JSON.stringify(out));
  await page.goto('http://127.0.0.1:3001/accounts/' + out.sav, { waitUntil: 'load' });
  await page.waitForTimeout(4000);
  await shot(page, 'savings.png');
  await page.goto('http://127.0.0.1:3001/reports/custom/' + out.rid, { waitUntil: 'load' });
  await page.waitForTimeout(6000);
  await shot(page, 'report_table.png');
  await ctx.close();
})().catch(e => { console.error(e); process.exit(1); });
