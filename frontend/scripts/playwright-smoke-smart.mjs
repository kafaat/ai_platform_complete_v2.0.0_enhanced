#!/usr/bin/env node
import { chromium } from '@playwright/test';
import { spawn } from 'node:child_process';
import { setTimeout as delay } from 'node:timers/promises';

const BASE_URL = process.env.PW_BASE_URL || 'http://127.0.0.1:4173';
const CHROMIUM = process.env.PW_CHROMIUM_PATH || '/usr/bin/chromium';
const START_SERVER = process.env.PW_REUSE_SERVER !== '1';
const launchArgs = [
  '--no-sandbox',
  '--disable-setuid-sandbox',
  '--disable-dev-shm-usage',
  '--disable-gpu',
  '--disable-background-networking',
  '--disable-default-apps',
];

let server;
if (START_SERVER) {
  server = spawn('npm', ['run', 'preview', '--', '--host', '127.0.0.1'], {
    stdio: 'ignore',
    env: { ...process.env, VITE_MAP_ENGINE: process.env.VITE_MAP_ENGINE || 'leaflet' },
  });
  await delay(2500);
}

const killServer = () => {
  if (server && !server.killed) { server.kill('SIGTERM'); setTimeout(() => { if (!server.killed) server.kill('SIGKILL'); }, 500).unref(); }
};
process.on('exit', killServer);
process.on('SIGINT', () => { killServer(); process.exit(130); });
process.on('SIGTERM', () => { killServer(); process.exit(143); });

const browser = await chromium.launch({ executablePath: CHROMIUM, headless: true, args: launchArgs });
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
const failedRequests = [];
const pageErrors = [];
page.on('requestfailed', (req) => failedRequests.push(`${req.url()} ${req.failure()?.errorText || ''}`));
page.on('pageerror', (err) => pageErrors.push(err.message));
page.on('console', (msg) => {
  if (msg.type() === 'error') pageErrors.push(msg.text());
});

try {
  const response = await page.goto(`${BASE_URL}/`, { waitUntil: 'commit', timeout: 10_000 });
  await page.waitForTimeout(5_000);
  const title = await page.title();
  const bodyText = await page.locator('body').innerText({ timeout: 5_000 }).catch(() => '');
  const rootExists = await page.locator('#root').count();
  const hasLogin = /تسجيل الدخول|دخول تجريبي|SAHOOL|سهول/i.test(bodyText);
  const realErrors = pageErrors.filter((e) => !/Failed to load resource|ERR_NAME_NOT_RESOLVED|ERR_ABORTED|favicon/i.test(e));
  const realFailures = failedRequests.filter((e) => !/favicon/i.test(e));

  console.log(JSON.stringify({
    ok: Boolean(response && response.ok() && rootExists && hasLogin && realErrors.length === 0 && realFailures.length === 0),
    status: response?.status() ?? null,
    title,
    rootExists: Boolean(rootExists),
    hasLogin,
    realErrors,
    realFailures,
    sampleText: bodyText.slice(0, 220),
  }, null, 2));

  if (!(response && response.ok() && rootExists && hasLogin && realErrors.length === 0 && realFailures.length === 0)) {
    process.exitCode = 1;
  }
} finally {
  await browser.close();
  killServer();
}
