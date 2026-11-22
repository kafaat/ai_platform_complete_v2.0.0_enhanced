#!/usr/bin/env node
// Write dist/build-info.json: which commit this frontend bundle was built from.
//
// The frontend had no build identity of its own (/runtime-identity is proxied to the
// platform), so nobody outside could tie a deployed bundle to a commit. Railway passes
// RAILWAY_GIT_COMMIT_SHA (and RAILWAY_DEPLOYMENT_ID) to Dockerfile builds that declare
// them as ARG; deploy/railway/Dockerfile.frontend does, and runs this after the build.
//
// A missing or malformed SHA (a build not triggered from GitHub) is written as null,
// never guessed: the file states what the build knew. It never fails the build.
//
// Usage: GIT_SHA=<sha> BUILD_ID=<id> node scripts/write-build-info.mjs [distDir]
import { existsSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const SHA = /^[0-9a-f]{40}$/;
const BUILD_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

export function buildInfo(env) {
  const sha = (env.GIT_SHA ?? '').trim().toLowerCase();
  const id = (env.BUILD_ID ?? '').trim();
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
  writeFileSync(join(distDir, 'build-info.json'), `${JSON.stringify(info)}\n`);
  console.log(`write-build-info: ${JSON.stringify(info)}`);
  return 0;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exit(main());
}
