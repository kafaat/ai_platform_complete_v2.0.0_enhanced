import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

// FE-07 (مراجعة 22bd27e): لا تلفيق مستأجِر 'default' في مفاتيح كاش React Query. غياب
// الهويّة ⇒ مفتاح صنميّ غير قابل للتصادم (UNAUTH_TENANT_KEY) فلا يشترك حالٌ غير مُصادَق
// كاشَ مستأجِرٍ حقيقيّ. هذا الحارس يمنع رجوع الـfail-open.
const root = join(__dirname, '..');
const FILES = [
  'hooks/useApi.ts',
  'hooks/useIndicators.ts',
  'sections/MapHub.tsx',
  'sections/SetupCabin.tsx',
];

describe('FE-07 — no fabricated default tenant in cache keys', () => {
  it('UNAUTH_TENANT_KEY is a non-colliding sentinel exported from useAuth', () => {
    const auth = readFileSync(join(root, 'hooks/useAuth.ts'), 'utf8');
    expect(auth).toContain("export const UNAUTH_TENANT_KEY = '__unauthenticated__'");
  });

  it('no fabricated default tenant fallback remains in cache-key files', () => {
    for (const rel of FILES) {
      const src = readFileSync(join(root, rel), 'utf8');
      expect(src, `${rel} still fabricates a 'default' tenant`).not.toMatch(
        /tenant_?[Ii]d\s*\?\?\s*'default'/,
      );
      // ويستعمل السنتينل بدلاً منه.
      expect(src, `${rel} does not use UNAUTH_TENANT_KEY`).toContain('UNAUTH_TENANT_KEY');
    }
  });
});
