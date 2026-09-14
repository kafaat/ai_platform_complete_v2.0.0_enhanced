import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

// U01 (التدقيق الموحَّد 2026-09-13 + Copilot على #1001): بطاقة المنطقة يجب أن تعرض حالة
// المراجعة وأعداد الوحدات المستقلّة والعيّنات مجهولة الوحدة، لا العدَّ الخام وحدَه.
const SRC = readFileSync(resolve(__dirname, 'LearningDashboardPage.tsx'), 'utf8');
const TYPES = readFileSync(resolve(__dirname, '../services/api/calibration.ts'), 'utf8');

describe('LearningDashboardPage — evidence quality is rendered, not only counted', () => {
  it('renders review_status and the independence counts per region card', () => {
    expect(SRC).toContain('ev.review_status');
    expect(SRC).toContain('ev.independence.fields');
    expect(SRC).toContain('ev.independence.seasons');
    expect(SRC).toContain('ev.independence.farms');
    expect(SRC).toContain('unknown_unit_samples');
    expect(SRC).toContain('evidence-quality-');
  });
  it('labels the sample-complete level distinctly from field_verified', () => {
    expect(SRC).toContain('field_sample_complete');
    expect(SRC).toMatch(/field_sample_complete:\s*'عيّنة مكتملة/);
  });
  it('types the new evidence fields on PersistedEvidence', () => {
    expect(TYPES).toContain('review_status?:');
    expect(TYPES).toContain('independence?:');
    expect(TYPES).toContain('unknown_unit_samples: number');
  });
});
