/** Actual production nginx configuration and Chromium permissions checks.
 * Capture lifecycle runs actual CallApp/controller and actual SDK microphone,
 * with an explicitly synthetic room transport (no claim of real SFU acceptance).
 */
import assert from 'node:assert/strict';
import { readFile, writeFile, mkdtemp, mkdir, rm } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import { tmpdir } from 'node:os';
import path from 'node:path';
import net from 'node:net';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
import { build } from 'vite';
import react from '@vitejs/plugin-react';
const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const nginx = process.env.NGINX_BINARY;
assert(nginx, 'NGINX_BINARY must name nginx >=1.27.3 with auth_request');
const temporary = await mkdtemp(path.join(tmpdir(), 'sahool-realtime-browser-'));
const server = net.createServer(); await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const port = server.address().port; await new Promise(resolve => server.close(resolve));
const origin = `http://127.0.0.1:${port}`;
let browser; let processNginx; const groups = [];
try {
  const original = await readFile(path.join(frontend, 'nginx.conf'), 'utf8');
  const configured = original.replace(/listen 8080;/, `listen 127.0.0.1:${port};`)
    .replace('listen [::]:8080;', '').replace('root /usr/share/nginx/html;', `root "${path.join(frontend, 'dist')}";`);
  await mkdir(path.join(temporary, 'logs'));
  const config = path.join(temporary, 'nginx.conf');
  await writeFile(config, `${process.getuid?.() === 0 ? 'user root;\n' : ''}pid ${temporary}/nginx.pid;\nerror_log ${temporary}/error.log;\nevents{}\nhttp {\ninclude ${path.dirname(path.dirname(nginx))}/conf/mime.types;\naccess_log off;\n${configured}\n}\n`);
  processNginx = spawn(nginx, ['-p', temporary, '-c', config, '-g', 'daemon off;'], { stdio: ['ignore', 'ignore', 'pipe'] });
  let startupError = ''; processNginx.stderr.on('data', data => { startupError += data.toString(); });
  let ready = false;
  for (let i = 0; i < 80; i++) {
    try { if ((await fetch(`${origin}/healthz`)).ok) { ready = true; break; } } catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  assert(ready, `nginx did not become ready: ${startupError}`);
  const spa = await fetch(`${origin}/index.html`);
  assert.equal(spa.status, 200); assert.match(spa.headers.get('permissions-policy'), /microphone=\(\)/);
  groups.push('ordinary_document_denies_capture');
  const call = await fetch(`${origin}/realtime-call/`);
  assert.equal(call.status, 200); assert.equal(call.headers.get('permissions-policy'), 'geolocation=(), camera=(), microphone=(self)');
  assert.equal(call.headers.get('x-frame-options'), 'DENY'); assert.match(call.headers.get('content-security-policy'), /frame-ancestors 'none'/);
  assert.equal(call.headers.get('cache-control'), 'no-store');
  const html = await call.text(); assert.match(html, /<title>سهول/);
  groups.push('canonical_document_has_scoped_headers');
  for (const route of ['/realtime-call/?q=1', '/realtime-call/index.html', '/realtime-call/nested', '/realtime-call/%69ndex.html', '/%72ealtime-call/', '/realtime-call%2f']) {
    const result = await fetch(`${origin}${route}`); assert.equal(result.status, 404, route);
    assert(!result.headers.get('permissions-policy')?.includes('microphone=(self)'), route);
  }
  groups.push('alternate_raw_paths_rejected');
  assert.equal((await fetch(`${origin}/api/v1/realtime/internal/jobs/test`)).status, 404);
  groups.push('worker_context_not_public');
  browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } : {}), args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] });
  const context = await browser.newContext({ permissions: ['microphone', 'camera'] });
  const page = await context.newPage();
  await page.goto(`${origin}/index.html`);
  const denied = await page.evaluate(async () => { try { const stream = await navigator.mediaDevices.getUserMedia({ audio: true }); stream.getTracks().forEach(track => track.stop()); return false; } catch (error) { return error.name === 'NotAllowedError'; } });
  assert(denied); groups.push('browser_denies_microphone_on_spa');
  await page.goto(`${origin}/realtime-call/`);
  const canonical = await page.evaluate(async () => { const stream = await navigator.mediaDevices.getUserMedia({ audio: true }); const state = stream.getAudioTracks()[0].readyState; stream.getTracks().forEach(track => track.stop()); try { const camera = await navigator.mediaDevices.getUserMedia({ video: true }); camera.getTracks().forEach(track => track.stop()); return { state, cameraDenied: false }; } catch (error) { return { state, cameraDenied: error.name === 'NotAllowedError' }; } });
  assert.deepEqual(canonical, { state: 'live', cameraDenied: true }); groups.push('browser_allows_only_microphone_on_canonical_document');
  await page.goto(`${origin}/index.html`);
  await page.evaluate(url => { const frame = document.createElement('iframe'); frame.src = url; document.body.append(frame); }, `${origin}/realtime-call/`);
  await page.waitForTimeout(300);
  assert.equal(await page.locator('iframe').evaluate(frame => { try { return frame.contentDocument?.querySelector('title')?.textContent ?? ''; } catch { return ''; } }), '');
  groups.push('browser_blocks_embedded_call_document');

  // Build a test-only bundle outside source with the real UI and physical capture
  // code. Replace only SFU transport so this scenario needs no room server.
  const adapter = path.join(temporary, 'media-fixture.ts');
  const sdk = path.join(frontend, 'node_modules/livekit-client/dist/livekit-client.esm.mjs');
  await writeFile(adapter, `import {createLocalAudioTrack} from ${JSON.stringify(sdk)};\nexport const livekitMedia={room:()=>({connect:async()=>{},disconnect:async()=>{},publish:async()=>{},onDisconnected:()=>{},onReconnecting:()=>{}}),microphone:async()=>{const track=await createLocalAudioTrack();window.__callTestTrack=track.mediaStreamTrack;const stop=track.stop.bind(track);track.stop=()=>{stop();console.info('SAHOOL_TEST_CAPTURE:'+track.mediaStreamTrack.readyState);navigator.sendBeacon('/__sahool_capture_test',track.mediaStreamTrack.readyState);};return track;}};`);
  const bundle = await build({ configFile: false, root: frontend, plugins: [react()], resolve: { alias: [{ find: './livekit-room', replacement: adapter }] }, define: { 'import.meta.env.VITE_REALTIME_CALL_ENABLED': '"true"', 'process.env.NODE_ENV': '"production"' }, logLevel: 'error', build: { write: false, lib: { entry: path.join(frontend, 'src/realtime-call/main.tsx'), name: 'SahoolCallTest', formats: ['iife'] }, rollupOptions: { output: { inlineDynamicImports: true } } } });
  const outputs = Array.isArray(bundle) ? bundle.flatMap(item => item.output) : bundle.output;
  const fixture = outputs.find(item => item.type === 'chunk').code;
  const entry = html.match(/<script[^>]+src="([^"]+)"/)[1];
  const capture = await context.newPage(); const trackEvents = []; const pageErrors = [];
  capture.on('pageerror', error => { pageErrors.push(error.message); });
  await capture.route('**/__sahool_capture_test', route => { trackEvents.push('SAHOOL_TEST_CAPTURE:'+route.request().postData()); return route.fulfill({status:204}); });
  capture.on('console', message => { if (message.text().startsWith('SAHOOL_TEST_CAPTURE:')) trackEvents.push(message.text()); });
  await capture.route(`**${entry}`, route => route.fulfill({ contentType: 'application/javascript', body: fixture }));
  await capture.route('**/auth/login', route => route.fulfill({ json: { access_token: 'synthetic-browser-fixture-bearer' } }));
  await capture.route('**/api/v1/realtime/sessions', route => route.fulfill({ status: 201, json: { session_id: 'browser-fixture', field_id: 'field-fixture', status: 'ACTIVE', url: 'wss://synthetic-sfu.invalid', participant_token: 'synthetic-room-token', expires_at: Math.floor(Date.now()/1000)+250, token_expires_at: Math.floor(Date.now()/1000)+50 } }));
  await capture.route('**/api/v1/realtime/sessions/browser-fixture', route => route.fulfill({ status: 202, json: { status: 'CLOSING' } }));
  await capture.goto(`${origin}/realtime-call/`);
  await capture.waitForTimeout(200);
  assert.deepEqual(pageErrors, [], 'capture fixture must render the actual UI');
  assert.match(await capture.locator('body').innerText(), /سجّل الدخول لهذه الصفحة/);
  await capture.getByLabel('البريد الإلكتروني').fill('farmer@example.test'); await capture.getByLabel('كلمة المرور').fill('synthetic-password');
  await capture.getByRole('button', { name: 'تسجيل الدخول' }).click();
  await capture.waitForTimeout(100);
  assert.deepEqual(pageErrors, [], 'login must not raise browser runtime errors');
  assert.equal(await capture.getByRole('status').innerText(), 'تم تسجيل الدخول');
  await capture.getByLabel('معرّف الحقل').fill('field-fixture'); await capture.getByRole('checkbox').check();
  await capture.getByRole('button', { name: /إنشاء جلسة/ }).click();
  await capture.getByRole('button', { name: 'تشغيل الميكروفون' }).waitFor();
  assert.equal(await capture.evaluate(() => window.__callTestTrack?.readyState ?? 'absent'), 'absent');
  await capture.getByRole('button', { name: 'تشغيل الميكروفون' }).click();
  await capture.waitForFunction(() => window.__callTestTrack?.readyState === 'live');
  await capture.waitForFunction(() => document.querySelector('[role=status]')?.textContent === 'الميكروفون يعمل');
  await Promise.all([capture.waitForURL(`${origin}/`), capture.getByRole('link', { name: 'العودة إلى سهول وإنهاء المكالمة' }).click()]);
  for (let i=0;i<50 && !trackEvents.includes('SAHOOL_TEST_CAPTURE:ended');i++) await new Promise(resolve => setTimeout(resolve, 100));
  assert(trackEvents.includes('SAHOOL_TEST_CAPTURE:ended'), 'actual CallApp navigation must stop actual SDK track: '+JSON.stringify({trackEvents,pageErrors}));
  groups.push('actual_ui_sdk_capture_requires_second_click_and_ends_on_navigation_with_fake_room');
  const receipt = { status: 'PASS', nginx: 'production configuration with only listener/root adapted', browser: browser.version(), groups, group_count: groups.length, capture_transport: 'synthetic room adapter; actual CallApp/controller and LiveKit microphone track', real_sfu_acceptance: false };
  const output = process.env.REALTIME_BROWSER_RECEIPT;
  if (output) await writeFile(output, JSON.stringify(receipt, null, 2)+'\n');
  console.log(JSON.stringify(receipt, null, 2));
} finally {
  await browser?.close(); processNginx?.kill('SIGTERM'); await rm(temporary, { recursive: true, force: true });
}
