#!/usr/bin/env node
import { readdir, stat } from 'node:fs/promises';
import path from 'node:path';

const assetsDir = path.resolve('dist/assets');
const assetNames = await readdir(assetsDir);
const files = assetNames.filter((name) => name.endsWith('.js'));
const wasmFiles = assetNames.filter((name) => name.endsWith('.wasm'));
if (files.length === 0) throw new Error('Bundle budget: dist/assets has no JavaScript files; run the production build first.');

const limits = {
  any: 1_050_000,
  entry: 400_000,
  mapHub: 800_000,
  worker: 900_000,
  wasmEach: 42_000_000,
  wasmTotal: 80_000_000,
};

const measured = await Promise.all(files.map(async (name) => ({
  name,
  bytes: (await stat(path.join(assetsDir, name))).size,
})));
const measuredWasm = await Promise.all(wasmFiles.map(async (name) => ({
  name,
  bytes: (await stat(path.join(assetsDir, name))).size,
})));

const violations = [];
for (const item of measured) {
  let limit = limits.any;
  if (/^index-.*\.js$/.test(item.name)) limit = Math.min(limit, limits.entry);
  if (/^MapHub-.*\.js$/.test(item.name)) limit = Math.min(limit, limits.mapHub);
  if (/\.worker-.*\.js$/.test(item.name)) limit = Math.min(limit, limits.worker);
  if (item.bytes > limit) violations.push({ ...item, limit });
}
for (const item of measuredWasm) {
  if (item.bytes > limits.wasmEach) violations.push({ ...item, limit: limits.wasmEach });
}
const wasmTotal = measuredWasm.reduce((total, item) => total + item.bytes, 0);
if (wasmTotal > limits.wasmTotal) {
  violations.push({ name: 'all WASM assets', bytes: wasmTotal, limit: limits.wasmTotal });
}

const largest = [...measured].sort((a, b) => b.bytes - a.bytes).slice(0, 8);
console.log('Bundle budget — largest JavaScript assets:');
for (const item of largest) console.log(`  ${item.name}: ${item.bytes} bytes`);

if (violations.length) {
  for (const item of violations) console.error(`BUDGET EXCEEDED: ${item.name} (${item.bytes} > ${item.limit})`);
  process.exit(1);
}

console.log(`Bundle budget passed: ${files.length} JavaScript assets; entry <= ${limits.entry} bytes; global <= ${limits.any} bytes.`);
console.log(`WASM budget passed: ${measuredWasm.length} assets; each <= ${limits.wasmEach} bytes; total ${wasmTotal} <= ${limits.wasmTotal} bytes.`);
