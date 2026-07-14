import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { pageForPath } from './routes';

// F-UI-40: كل مسار بديل (alias) مُسجَّل في App.tsx ويعرض pageContent يجب أن يُحلّ عبر
// pageForPath إلى PageId معروف — وإلّا يقع على 'dashboard' صامتاً فيعرض الصفحة الخطأ.
const appSrc = readFileSync(join(process.cwd(), 'src/App.tsx'), 'utf8');

// المسارات الثابتة (لا ديناميكيّة :param) التي تعرض pageContent.
const aliasPaths = Array.from(
  appSrc.matchAll(/<Route\s+path="(\/[^"]+)"\s+element=\{pageContent\}\s*\/>/g),
  (m) => m[1],
).filter((p) => !p.includes(':'));

describe('F-UI-40 — every static alias route resolves to a known page', () => {
  it('extracted a meaningful set of alias routes', () => {
    expect(aliasPaths.length).toBeGreaterThan(10);
  });

  it('no alias silently falls back to dashboard (pageForPath !== null)', () => {
    const unresolved = aliasPaths.filter((p) => pageForPath(p) === null);
    expect(unresolved, `aliases not mapped in pageForPath: ${unresolved.join(', ')}`).toEqual([]);
  });
});
