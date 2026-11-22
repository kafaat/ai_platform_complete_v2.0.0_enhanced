import { describe, expect, it } from 'vitest';
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

// /build-info.json ties a deployed bundle to its commit (the lab could not before: the frontend
// exposed no identity of its own). Three parts must agree: the writer script, the Railway
// Dockerfile that runs it with Railway's build variables, and nginx serving it without the SPA
// fallback (a missing file must be a 404, never index.html with 200).

const root = process.cwd();
const SHA = '0123456789abcdef0123456789abcdef01234567';

type Run = { status: number | null; info: unknown; stderr: string };

function write(env: Record<string, string>, prepare?: (dist: string) => void): Run {
  const dist = mkdtempSync(join(tmpdir(), 'build-info-'));
  try {
    writeFileSync(join(dist, 'index.html'), '<html></html>');
    prepare?.(dist);
    const result = spawnSync(process.execPath, ['scripts/write-build-info.mjs', dist], {
      encoding: 'utf8',
      env: { PATH: process.env.PATH ?? '', ...env },
    });
    const file = join(dist, 'build-info.json');
    let info: unknown = null;
    try {
      info = JSON.parse(readFileSync(file, 'utf8'));
    } catch {
      info = null;
    }
    return { status: result.status, info, stderr: result.stderr };
  } finally {
    rmSync(dist, { recursive: true, force: true });
  }
}

const ok = (git_sha: string | null, build_id: string | null) => ({
  status: 0,
  info: { service: 'sahool-frontend', git_sha, build_id },
});

describe('frontend build identity', () => {
  it('on Railway, derives build_id from the built commit, since the deployment id is empty at build time', () => {
    expect(write({ RAILWAY_GIT_COMMIT_SHA: SHA, RAILWAY_DEPLOYMENT_ID: '' })).toMatchObject(
      ok(SHA, `railway-${SHA.slice(0, 12)}`),
    );
  });

  it('uses the Railway deployment id when Railway does supply one', () => {
    expect(write({ RAILWAY_GIT_COMMIT_SHA: SHA, RAILWAY_DEPLOYMENT_ID: '1234-abcd' })).toMatchObject(
      ok(SHA, 'railway-1234-abcd'),
    );
  });

  it('an explicit GIT_SHA/BUILD_ID (a build outside Railway) takes precedence', () => {
    expect(write({ GIT_SHA: SHA, BUILD_ID: 'local-7', RAILWAY_GIT_COMMIT_SHA: '' })).toMatchObject(ok(SHA, 'local-7'));
  });

  it.each([
    [{}],
    [{ GIT_SHA: '', BUILD_ID: '' }],
    [{ RAILWAY_GIT_COMMIT_SHA: '', RAILWAY_DEPLOYMENT_ID: '' }],
    [{ GIT_SHA: 'main', BUILD_ID: 'bad id with spaces' }],
    [{ GIT_SHA: SHA.slice(0, 12) }],
    [{ RAILWAY_GIT_COMMIT_SHA: 'not-a-sha' }],
    [{ RAILWAY_GIT_COMMIT_SHA: SHA.toUpperCase() }],
  ])('writes null, never a guess, when the values are missing or malformed (%j)', (env) => {
    expect(write(env)).toMatchObject(ok(null, null));
  });

  it('without a built dist/index.html it exits 2 and writes nothing', () => {
    const dist = mkdtempSync(join(tmpdir(), 'build-info-empty-'));
    try {
      const result = spawnSync(process.execPath, ['scripts/write-build-info.mjs', dist], {
        encoding: 'utf8',
        env: { PATH: process.env.PATH ?? '', RAILWAY_GIT_COMMIT_SHA: SHA },
      });
      expect(result.status).toBe(2);
      expect(existsSync(join(dist, 'build-info.json'))).toBe(false);
    } finally {
      rmSync(dist, { recursive: true, force: true });
    }
  });

  it('a write error is logged and does not fail the build', () => {
    // build-info.json already exists as a directory, so the write itself throws.
    const run = write({ RAILWAY_GIT_COMMIT_SHA: SHA }, (dist) => mkdirSync(join(dist, 'build-info.json')));
    expect(run.status).toBe(0);
    expect(run.info).toBeNull();
    expect(run.stderr).toMatch(/could not write build-info\.json/);
  });

  it('the Railway Dockerfile declares the build variables and runs the writer after the build, without overrides', () => {
    const dockerfile = readFileSync(join(root, '../deploy/railway/Dockerfile.frontend'), 'utf8');
    const build = dockerfile.indexOf('RUN npm run build:docker');
    const shaArg = dockerfile.indexOf('ARG RAILWAY_GIT_COMMIT_SHA');
    const idArg = dockerfile.indexOf('ARG RAILWAY_DEPLOYMENT_ID');
    const writer = dockerfile.indexOf('RUN node scripts/write-build-info.mjs');
    expect(build).toBeGreaterThan(-1);
    expect(shaArg).toBeGreaterThan(build);
    expect(idArg).toBeGreaterThan(build);
    expect(writer).toBeGreaterThan(Math.max(shaArg, idArg));
    // The writer reads the Railway ARGs itself; an inline GIT_SHA/BUILD_ID would override them.
    const runLine = dockerfile.slice(writer, dockerfile.indexOf('\n', writer));
    expect(runLine).toBe('RUN node scripts/write-build-info.mjs');
  });

  it('nginx serves the file exactly, uncached, with no SPA fallback, before the catch-all', () => {
    const nginx = readFileSync(join(root, 'nginx.conf'), 'utf8');
    const block = /location = \/build-info\.json \{([^}]*)\}/.exec(nginx);
    expect(block).not.toBeNull();
    expect(block![1]).toMatch(/try_files \$uri =404;/);
    expect(block![1]).toMatch(/expires epoch;/);
    expect(block![1]).not.toMatch(/index\.html/);
    expect(block![1]).not.toMatch(/add_header/);
    expect(nginx.indexOf('location = /build-info.json')).toBeLessThan(nginx.indexOf('location / {'));
  });
});
