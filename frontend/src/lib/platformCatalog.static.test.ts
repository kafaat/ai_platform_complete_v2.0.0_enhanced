import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import {
  PLATFORM_CATALOG_COMPONENTS,
  PLATFORM_CATALOG_COUNTS,
  PLATFORM_CATALOG_FINGERPRINT,
} from './platformCatalog.generated';

// U6: البيان المولَّد مستهلَك حقيقيّ في AdminRuntimePage، ويحمل حدود الصدق —
// لا يُصدِّر configured/activated، والواجهة تتدهور على /readyz الحيّ لا عليه.
describe('platform catalog generated manifest (U6)', () => {
  it('exposes deterministic fingerprint + component list', () => {
    expect(PLATFORM_CATALOG_FINGERPRINT).toMatch(/^[0-9a-f]{64}$/);
    expect(PLATFORM_CATALOG_COMPONENTS.length).toBe(PLATFORM_CATALOG_COUNTS.components);
    expect(PLATFORM_CATALOG_COUNTS.backend_components).toBeGreaterThan(0);
  });

  it('never carries configured/activated runtime claims', () => {
    for (const c of PLATFORM_CATALOG_COMPONENTS) {
      expect(c).not.toHaveProperty('configured');
      expect(c).not.toHaveProperty('activated');
      // wired is static-derived: boolean or null (job/unknown), never a runtime string
      expect(['boolean', 'object']).toContain(typeof c.wired);
    }
  });

  it('is consumed by AdminRuntimePage (no orphan scaffolding)', () => {
    const page = readFileSync(
      join(__dirname, '..', 'sections', 'AdminRuntimePage.tsx'),
      'utf-8',
    );
    expect(page).toContain('platformCatalog.generated');
    expect(page).toContain('PLATFORM_CATALOG_COMPONENTS');
  });
});
