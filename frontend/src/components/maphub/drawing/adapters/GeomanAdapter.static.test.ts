// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const srcDir = join(root, 'src');
const geomanAdapterRel = 'components/maphub/drawing/adapters/LeafletGeomanAdapter.ts';
const geomanSrc = readFileSync(join(srcDir, geomanAdapterRel), 'utf8');

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walk(full));
    else if (/\.(ts|tsx|js|jsx)$/.test(entry.name)) out.push(full);
  }
  return out;
}

describe('Geoman adapter — containment + wiring (static)', () => {
  it('imports @geoman-io ONLY inside LeafletGeomanAdapter.ts', () => {
    // Detect real ES import statements of @geoman-io (ignore comments / test scans).
    const importRe = /import\s+(?:[^'"]*\s+from\s+)?['"]@geoman-io[^'"]*['"]/;
    const offenders: string[] = [];
    for (const file of walk(srcDir)) {
      if (file.endsWith(geomanAdapterRel.replace(/\//g, '/'))) continue;
      const content = readFileSync(file, 'utf8');
      if (importRe.test(content)) offenders.push(file.slice(root.length + 1));
    }
    expect(offenders).toEqual([]);
  });

  it('the geoman adapter actually imports @geoman-io', () => {
    expect(geomanSrc).toContain('@geoman-io/leaflet-geoman-free');
  });

  it('the geoman adapter drives drawing through map.pm + pm:create', () => {
    expect(geomanSrc).toContain('map.pm');
    expect(geomanSrc).toContain('enableDraw');
    expect(geomanSrc).toContain('pm:create');
  });
});
