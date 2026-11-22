import { describe, expect, it } from 'vitest';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

// /build-info.json ties a deployed bundle to its commit (the lab could not before: the frontend
// exposed no identity of its own). Three parts must agree: the writer script, the Railway
// Dockerfile that runs it with Railway's build variables, and nginx serving it without the SPA
// fallback (a missing file must be a 404, never index.html with 200).

const root = process.cwd();
const SHA = '0123456789abcdef0123456789abcdef01234567';

function write(env: Record<string, string>): { status: number | null; info: unknown } {
  const dist = mkdtempSync(join(tmpdir(), 'build-info-'));
  try {
    writeFileSync(join(dist, 'index.html'), '<html></html>');
    const result = spawnSync(process.execPath, ['scripts/write-build-info.mjs', dist], {
      encoding: 'utf8',
      env: { PATH: process.env.PATH ?? '', ...env },
    });
    const file = join(dist, 'build-info.json');
    return { status: result.status, info: existsSync(file) ? JSON.parse(readFileSync(file, 'utf8')) : null };
  } finally {
    rmSync(dist, { recursive: true, force: true });
  }
}

describe('frontend build identity', () => {
  it('records the commit and build id Railway supplies', () => {
    expect(write({ GIT_SHA: SHA, BUILD_ID: 'railway-1234-abcd' })).toEqual({
      status: 0,
      info: { service: 'sahool-frontend', git_sha: SHA, build_id: 'railway-1234-abcd' },
    });
  });

  it.each([
    [{}],
    [{ GIT_SHA: '', BUILD_ID: '' }],
    [{ GIT_SHA: 'main', BUILD_ID: 'bad id with spaces' }],
    [{ GIT_SHA: SHA.slice(0, 12) }],
  ])('writes null, never a guess, when the values are missing or malformed (%j)', (env) => {
    expect(write(env)).toEqual({
      status: 0,
      info: { service: 'sahool-frontend', git_sha: null, build_id: null },
    });
  });

  it('the Railway Dockerfile declares the build variables and runs the writer after the build', () => {
    const dockerfile = readFileSync(join(root, '../deploy/railway/Dockerfile.frontend'), 'utf8');
    const build = dockerfile.indexOf('RUN npm run build:docker');
    const shaArg = dockerfile.indexOf('ARG RAILWAY_GIT_COMMIT_SHA');
    const writer = dockerfile.indexOf('node scripts/write-build-info.mjs');
    expect(build).toBeGreaterThan(-1);
    expect(shaArg).toBeGreaterThan(build);
    expect(writer).toBeGreaterThan(shaArg);
    expect(dockerfile).toContain('GIT_SHA="$RAILWAY_GIT_COMMIT_SHA"');
    expect(dockerfile).toContain('ARG RAILWAY_DEPLOYMENT_ID');
  });

  it('nginx serves the file exactly, with no SPA fallback, before the catch-all', () => {
    const nginx = readFileSync(join(root, 'nginx.conf'), 'utf8');
    const block = /location = \/build-info\.json \{([^}]*)\}/.exec(nginx);
    expect(block).not.toBeNull();
    expect(block![1]).toMatch(/try_files \$uri =404;/);
    expect(block![1]).not.toMatch(/index\.html/);
    expect(block![1]).not.toMatch(/add_header/);
    expect(nginx.indexOf('location = /build-info.json')).toBeLessThan(nginx.indexOf('location / {'));
  });
});
