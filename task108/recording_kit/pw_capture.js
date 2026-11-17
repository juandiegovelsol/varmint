const fs = require('fs'); const path = require('path');
const { S, open, shot } = require('./pw_common');
const state = process.argv[2];
(async () => {
  const seed = JSON.parse(fs.readFileSync(path.join(S, 'tools', 'seed.json')));
  const { ctx, page } = await open();
  const url = 'http://127.0.0.1:3001/reports/custom/' + seed.rid;
  const closeToast = async () => {
    const c = page.getByRole('button', { name: 'Close', exact: true });
    if (await c.count()) { await c.first().click().catch(() => {}); await page.waitForTimeout(500); }
  };
  await page.goto(url, { waitUntil: 'load' });
  await page.waitForTimeout(6000);
  await closeToast();
  await page.getByRole('button', { name: 'Data Table' }).click();
  await page.waitForTimeout(2500);
  await page.mouse.move(5, 895);
  await shot(page, `${state}_table.png`);

  // drill into the Transfers row, first week column
  const row = page.locator('[id]').filter({ has: page.getByText('Transfers', { exact: true }) }).last();
  const cells = row.getByText(/^\d[\d,]*\.\d\d$/);
  console.log('transfers row cells', await cells.allInnerTexts());
  await cells.first().click();
  await page.waitForURL(/\/accounts/, { timeout: 15000 });
  await page.waitForTimeout(3500);
  await closeToast();
  await page.mouse.move(5, 895);
  await shot(page, `${state}_drill.png`);

  // stacked bar chart with legend, tooltip on the second week
  await page.goto(url, { waitUntil: 'load' });
  await page.waitForTimeout(5000);
  await closeToast();
  await page.getByRole('button', { name: 'Stacked Bar Graph' }).click();
  await page.waitForTimeout(2500);
  const legendBtn = page.getByRole('button', { name: 'Show Legend' });
  if (await legendBtn.count()) { await legendBtn.click(); await page.waitForTimeout(1500); }
  const labelsBtn = page.getByRole('button', { name: 'Show Labels' });
  if (await labelsBtn.count()) { await labelsBtn.click(); await page.waitForTimeout(1500); }
  await page.mouse.move(5, 895);
  await page.waitForTimeout(800);
  await shot(page, `${state}_chart.png`);
  await ctx.close();
})().catch(e => { console.error(e); process.exit(1); });
