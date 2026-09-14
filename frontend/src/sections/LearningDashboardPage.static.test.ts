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
  it('every consumer of the shared EvidenceLevel renders field_sample_complete', () => {
    // Copilot على #1001: LineagePage/CalibrationPage كانتا تعرضان المفتاح الخام بلون افتراضيّ.
    for (const page of ['LineagePage.tsx', 'CalibrationPage.tsx']) {
      const src = readFileSync(resolve(__dirname, page), 'utf8');
      expect(src, page).toMatch(/field_sample_complete:\s*'عيّنة مكتملة/);
      expect(src, page).toContain("case 'field_sample_complete':");
    }
    const lib = readFileSync(resolve(__dirname, '../lib/learningEvidence.ts'), 'utf8');
    expect(lib).toContain("{ key: 'field_sample_complete'");
  });
  it('reads the aggregate counters from summary.overall, not the response root', () => {
    // Copilot على #1001: العقد يضع الإجماليّ تحت `overall`؛ القراءة من الجذر تعرض «—» على بيانات موجودة.
    expect(SRC).toContain('summary?.overall?.outcome_count');
    expect(SRC).toContain('summary?.overall?.success_rate');
    expect(SRC).not.toContain('summary?.outcome_count');
    expect(SRC).not.toContain('summary?.success_rate');
    expect(SRC).not.toContain('regions_verified');
    expect(SRC).toContain("r.evidence_level === 'field_verified'");
    const API = readFileSync(resolve(__dirname, '../services/api.ts'), 'utf8');
    const block = API.slice(API.indexOf('export interface LearningSummary {'));
    const body = block.slice(0, block.indexOf('}'));
    expect(body).toContain('overall?:');
    expect(body).toContain('region_count?:');
    expect(body).not.toContain('regions_verified');
  });
  it('types the new evidence fields on PersistedEvidence', () => {
    expect(TYPES).toContain('review_status?:');
    expect(TYPES).toContain('independence?:');
    expect(TYPES).toContain('unknown_unit_samples: number');
    expect(TYPES).toMatch(/EvidenceLevel =[\s\S]*'field_sample_complete'/);
  });
});
