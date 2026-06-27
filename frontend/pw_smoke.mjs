import { chromium } from '@playwright/test';
const browser = await chromium.launch({executablePath:'/usr/bin/chromium', headless:true, args:['--no-sandbox','--disable-setuid-sandbox','--disable-dev-shm-usage']});
const page = await browser.newPage();
page.on('requestfailed', r => console.log('requestfailed', r.url(), r.failure()?.errorText));
page.on('response', r => { if (r.url().includes('4173')) console.log('response', r.status(), r.url()); });
try {
  await page.goto('http://127.0.0.1:4173/fields/map-center', { waitUntil: 'commit', timeout: 15000 });
  console.log('url', page.url());
  await page.waitForTimeout(3000);
  console.log('title', await page.title());
  console.log('body', (await page.locator('body').innerText({timeout:5000})).slice(0,1000));
  await page.screenshot({path:'/mnt/data/retry_tools_web_mobile/pw_smoke.png', fullPage:true});
} catch (e) { console.error('ERR', e); }
await browser.close();
