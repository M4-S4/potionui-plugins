const path = require('path');
const { chromium } = require(path.join('<home>/Dev/PotionUI/frontend/node_modules', 'playwright'));

const base = process.env.SHOT_BASE;
const out = process.env.SHOT_OUT;
const executablePath = path.join(process.env.LOCALAPPDATA, 'ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-win64/chrome-headless-shell.exe');

function accounts(token, user) {
  return JSON.stringify({ v: 1, activeId: user.id, accounts: [{ userId: user.id, username: user.username, role: user.role, avatar: null, token, signedInAt: Date.now(), expired: false }] });
}

async function session(browser, user) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'dark', deviceScaleFactor: 1 });
  await context.addInitScript(([t, a]) => {
    localStorage.setItem('auth_token', t);
    localStorage.setItem('potionui_accounts', a);
  }, [user.token, accounts(user.token, user)]);
  return context;
}

(async () => {
  const browser = await chromium.launch({ executablePath });
  const admin = JSON.parse(process.env.SHOT_ADMIN);
  const errors = [];
  const ctx = await session(browser, admin);
  const page = await ctx.newPage();
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

  await page.goto(`${base}/plugins/model-browser?source=civitai&q=landscape`, { waitUntil: 'networkidle' });
  await page.waitForSelector('img', { timeout: 30000 });
  await page.waitForTimeout(2500);
  await page.screenshot({ path: path.join(out, '1-search.png') });

  await page.locator('h3, [role="heading"]').filter({ hasText: /^LandscapeSuperMix$/ }).first().click().catch(async () => {
    await page.getByText('LandscapeSuperMix', { exact: true }).first().click();
  });
  await page.waitForTimeout(4000);
  await page.screenshot({ path: path.join(out, '2-detail.png') });
  await page.keyboard.press('Escape');

  await page.goto(`${base}/plugins/model-browser?source=huggingface&q=stable-diffusion-xl`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(4000);
  await page.screenshot({ path: path.join(out, '3-hugging-face.png') });

  await page.goto(`${base}/admin?tab=plugins&id=model-browser`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(3000);
  await page.getByRole('button', { name: 'Permissions', exact: true }).click();
  await page.waitForTimeout(3000);
  await page.screenshot({ path: path.join(out, '4-permissions.png') });

  console.log('console errors:', errors.filter((e) => !/service-worker|ServiceWorker|WebSocket/.test(e)));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
