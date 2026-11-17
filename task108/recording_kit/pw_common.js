const path = require('path');
const S = 'C:/Users/JUANV~1/AppData/Local/Temp/claude/ba687bfd8aae2151/00e52964-f6a5-4ee6-8809-6c0db154326b/scratchpad';
const { chromium } = require(path.join(S, 'actual/node_modules/playwright'));
async function open() {
  const ctx = await chromium.launchPersistentContext(path.join(S, 'profile'), {
    headless: true, executablePath: 'C:/Users/Juan V/AppData/Local/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-win64/chrome-headless-shell.exe', viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1,
    locale: 'en-US', timezoneId: 'America/Toronto', colorScheme: 'light',
  });
  const page = ctx.pages()[0] || (await ctx.newPage());
  page.on('pageerror', e => console.log('PAGEERROR', e.message));
  return { ctx, page };
}
module.exports = { S, open, shot: (p, n) => p.screenshot({ path: path.join(S, 'shots', n) }) };
