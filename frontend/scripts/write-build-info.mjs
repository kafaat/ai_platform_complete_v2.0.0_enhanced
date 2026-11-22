#!/usr/bin/env node
// Write dist/build-info.json: which commit this frontend bundle was built from.
//
// The frontend had no build identity of its own (/runtime-identity is proxied to the
// platform), so nobody outside could tie a deployed bundle to a commit. Railway passes
// RAILWAY_GIT_COMMIT_SHA to Dockerfile builds that declare it as ARG, and
// deploy/railway/Dockerfile.frontend runs this script after the build with both Railway
// ARGs in its environment.
//
// build_id, like the platform's (services/sahool-platform/Dockerfile): RAILWAY_DEPLOYMENT_ID
// arrives empty at build time (measured 2026-09-21, and again on this service on
// 2026-11-22), so it falls back to railway-<built commit[:12]>. An explicit GIT_SHA/BUILD_ID
// (a build outside Railway) takes precedence over the Railway values.
//
// A missing or malformed value is written as null, never guessed: the file states what the
// build knew. Once dist/index.html exists (the build ran), this script never fails the build:
// a write error is logged and the file is left out, so nginx answers 404 for it.
//
// Usage: node scripts/write-build-info.mjs [distDir]
//   env: RAILWAY_GIT_COMMIT_SHA, RAILWAY_DEPLOYMENT_ID, or GIT_SHA / BUILD_ID overrides.
import { existsSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const SHA = /^[0-9a-f]{40}$/;
const BUILD_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

const clean = (value) => (value ?? '').trim();

export function buildInfo(env) {
  const railwaySha = clean(env.RAILWAY_GIT_COMMIT_SHA);
  const deploymentId = clean(env.RAILWAY_DEPLOYMENT_ID);
  const sha = clean(env.GIT_SHA) || railwaySha;
  let id = clean(env.BUILD_ID);
  if (!id && deploymentId) id = `railway-${deploymentId}`;
  if (!id && SHA.test(railwaySha)) id = `railway-${railwaySha.slice(0, 12)}`;
  return {
    service: 'sahool-frontend',
    git_sha: SHA.test(sha) ? sha : null,
    build_id: BUILD_ID.test(id) ? id : null,
  };
}

function main() {
  const here = dirname(fileURLToPath(import.meta.url));
  const distDir = resolve(process.argv[2] ?? join(here, '..', 'dist'));
  if (!existsSync(join(distDir, 'index.html'))) {
    console.error(`write-build-info: ${distDir}/index.html not found; run the build first`);
    return 2;
  }
  const info = buildInfo(process.env);
  try {
    writeFileSync(join(distDir, 'build-info.json'), `${JSON.stringify(info)}\n`);
  } catch (error) {
    console.error(`write-build-info: could not write build-info.json (${error.code ?? error.message}); left out`);
    return 0;
  }
  console.log(`write-build-info: ${JSON.stringify(info)}`);
  return 0;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exit(main());
}
