#!/usr/bin/env node
import { spawn } from 'node:child_process';
import { readdirSync, statSync, writeFileSync, mkdirSync } from 'node:fs';
import { join, relative } from 'node:path';

const root = process.cwd();
const outDir = join(root, 'test-results-smart');
mkdirSync(outDir, { recursive: true });

function run(cmd, args, opts = {}) {
  const started = Date.now();
  return new Promise((resolve) => {
    const child = spawn(cmd, args, { cwd: root, shell: false, env: process.env });
    let stdout = '';
    let stderr = '';
    const timeoutMs = opts.timeoutMs ?? 120_000;
    const timer = setTimeout(() => {
      child.kill('SIGTERM');
      setTimeout(() => child.kill('SIGKILL'), 2000).unref();
    }, timeoutMs);
    child.stdout.on('data', d => { stdout += d; process.stdout.write(d); });
    child.stderr.on('data', d => { stderr += d; process.stderr.write(d); });
    child.on('close', (code, signal) => {
      clearTimeout(timer);
      resolve({ cmd: [cmd, ...args].join(' '), code, signal, durationMs: Date.now() - started, stdout, stderr });
    });
  });
}

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) out.push(...walk(p));
    else if (/\.(test|spec)\.(ts|tsx)$/.test(name)) out.push(relative(root, p));
  }
  return out;
}

const results = [];
async function step(name, fn) {
  console.log(`\n=== ${name} ===`);
  const res = await fn();
  results.push({ name, ...res });
  if (res.code !== 0) process.exitCode = 1;
  return res;
}

await step('typecheck', () => run('npm', ['run', 'typecheck'], { timeoutMs: 120_000 }));

console.log('\n=== vitest: individual files with hard timeout ===');
const tests = walk(join(root, 'src')).sort();
let passed = 0;
let failed = 0;
const vitestRows = [];
for (const file of tests) {
  const res = await run('npx', ['vitest', 'run', file, '--reporter=dot'], { timeoutMs: 30_000 });
  const ok = res.code === 0;
  if (ok) passed++; else failed++;
  vitestRows.push({ file, ok, code: res.code, signal: res.signal, durationMs: res.durationMs });
  writeFileSync(join(outDir, `vitest-${file.replace(/[^a-zA-Z0-9_.-]/g, '_')}.log`), `${res.stdout}\n${res.stderr}`);
}
results.push({ name: 'vitest-individual', code: failed === 0 ? 0 : 1, passedFiles: passed, failedFiles: failed, totalFiles: tests.length });
if (failed) process.exitCode = 1;
writeFileSync(join(outDir, 'vitest-individual.json'), JSON.stringify(vitestRows, null, 2));
console.log(`Vitest files: ${passed}/${tests.length} passed, ${failed} failed`);

await step('build', () => run('npm', ['run', 'build'], { timeoutMs: 180_000 }));
await step('playwright-smoke-smart', () => run('node', ['scripts/playwright-smoke-smart.mjs'], { timeoutMs: 45_000 }));

writeFileSync(join(outDir, 'summary.json'), JSON.stringify(results, null, 2));
console.log(`\nSmart web test summary written to ${relative(root, join(outDir, 'summary.json'))}`);
process.exit(process.exitCode ?? 0);
