const path = require('path');
const { chromium } = require(path.join('<home>/Dev/PotionUI/frontend/node_modules', 'playwright'));

const base = process.env.SHOT_BASE;
const out = process.env.SHOT_OUT;

function accounts(token, user) {
  return JSON.stringify({ v: 1, activeId: user.id, accounts: [{ userId: user.id, username: user.username, role: user.role, avatar: null, token, signedInAt: Date.now(), expired: false }] });
}

async function session(browser, token, user) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'dark', deviceScaleFactor: 1 });
  await context.addInitScript(([t, a]) => {
    localStorage.setItem('auth_token', t);
    localStorage.setItem('potionui_accounts', a);
  }, [token, accounts(token, user)]);
  return context;
}

(async () => {
  const browser = await chromium.launch({ executablePath: path.join(process.env.LOCALAPPDATA, 'ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-win64/chrome-headless-shell.exe') });
  const admin = JSON.parse(process.env.SHOT_ADMIN);
  const user = JSON.parse(process.env.SHOT_USER);

  const ctx = await session(browser, admin.token, admin);
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto(`${base}/plugins/model-browser?source=civitai&q=landscape`, { waitUntil: 'networkidle' });
  await page.waitForSelector('img', { timeout: 30000 });
  await page.waitForTimeout(2500);
  await page.screenshot({ path: path.join(out, '1-search-landscape.png') });
  console.log('cards:', await page.locator('a[target="_blank"]').count());

  await page.getByRole('button', { name: /Filters/ }).click();
  await page.waitForTimeout(1200);
  await page.screenshot({ path: path.join(out, '2-filters.png') });
  await page.keyboard.press('Escape');

  await page.mouse.wheel(0, 4000);
  await page.waitForTimeout(3000);
  console.log('cards after scroll:', await page.locator('a[target="_blank"]').count());
  console.log('admin console errors:', errors.filter((e) => !/service-worker|ServiceWorker|WebSocket/.test(e)));

  const uctx = await session(browser, user.token, user);
  const upage = await uctx.newPage();
  await upage.goto(`${base}/`, { waitUntil: 'networkidle' });
  await upage.waitForTimeout(2000);
  const links = await upage.locator('a[href="/plugins/model-browser"]').count();
  console.log('user sidebar links to the page:', links);
  await upage.goto(`${base}/plugins/model-browser`, { waitUntil: 'networkidle' });
  await upage.waitForTimeout(3000);
  await upage.screenshot({ path: path.join(out, '3-non-admin-direct-url.png') });
  console.log('user page text:', (await upage.locator('main').innerText()).slice(0, 200).replace(/\s+/g, ' '));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
