// F-U01: the season simulation run (POST /api/v1/seasons/{id}/simulate) had one caller in the
// web app, FieldManagementPage, and App.tsx no longer mounts that section, so sim_* shown on
// mounted screens could not be filled from the web app. This reads the source tree: at least one
// section that App.tsx renders must reach a component that calls useSimulateSeason.
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const SRC = join(process.cwd(), 'src');
const read = (p: string) => readFileSync(p, 'utf8');

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return sourceFiles(full);
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [full] : [];
  });
}

function resolveImport(from: string, spec: string): string | null {
  const base = spec.startsWith('@/') ? join(SRC, spec.slice(2))
    : spec.startsWith('.') ? resolve(dirname(from), spec) : null;
  if (!base) return null;
  for (const ext of ['.tsx', '.ts', '/index.tsx', '/index.ts']) {
    try { if (statSync(base + ext).isFile()) return base + ext; } catch { /* next */ }
  }
  return null;
}

const importsOf = (file: string): string[] =>
  [...read(file).matchAll(/from\s+'([^']+)'/g)]
    .map((m) => resolveImport(file, m[1]))
    .filter((p): p is string => p !== null);

describe('season simulation has a mounted entry point (F-U01)', () => {
  const app = join(SRC, 'App.tsx');
  const appSource = read(app);
  const lazySections = [...appSource.matchAll(/const\s+(\w+)\s*=\s*lazy\(\(\)\s*=>\s*import\('([^']+)'\)/g)]
    .map((m) => ({ name: m[1], file: resolveImport(app, m[2]) }));
  const mounted = lazySections
    .filter((s) => s.file && new RegExp(`return <${s.name}[\\s/>]`).test(appSource))
    .map((s) => s.file as string);
  const callers = sourceFiles(SRC).filter(
    (f) => /\buseSimulateSeason\(\)/.test(read(f)) && !f.endsWith(join('hooks', 'useApi.ts')),
  );

  it('finds the sections App.tsx renders and the callers of the run', () => {
    expect(mounted.length).toBeGreaterThan(20);
    expect(callers.length).toBeGreaterThan(0);
  });

  it('at least one mounted section calls the run itself or imports a component that does', () => {
    const reaching = mounted.filter(
      (section) => callers.includes(section) || importsOf(section).some((dep) => callers.includes(dep)),
    );
    expect(reaching.map((f) => f.slice(SRC.length + 1))).not.toEqual([]);
  });

  it('App.tsx does not claim the legacy fields section is still imported', () => {
    expect(appSource).not.toMatch(/import\('\.\/sections\/FieldManagementPage'\)/);
    expect(appSource).not.toMatch(/FieldManagementPage السابق يبقى مُستورَداً/);
  });
});
