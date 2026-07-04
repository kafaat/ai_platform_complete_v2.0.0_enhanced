import { describe, expect, it } from 'vitest';
import { buildTraceabilityReport, traceabilityToMarkdown } from './fieldTraceability';

describe('buildTraceabilityReport', () => {
  it('has no data for an empty field (honest)', () => {
    const r = buildTraceabilityReport({ fieldName: 'حقل' });
    expect(r.hasData).toBe(false);
    expect(r.facts).toEqual([]);
    expect(traceabilityToMarkdown(r)).toContain('لا سجلّ');
  });

  it('consolidates field + season + water + prescriptions + ops from real values', () => {
    const r = buildTraceabilityReport({
      fieldName: 'حقل الشمال',
      crop: 'قمح',
      areaHa: 12.4,
      season: { crops: ['قمح'], cultivar: 'صنف محلّيّ', sowing_date: '2026-03-01', plowing_date: '2026-02-15', irrigation_type: 'تنقيط', status: 'active' },
      completedOps: [{ label: 'ريّ', date: '2026-04-10' }, { label: 'تسميد', date: '2026-05-02' }],
      irrigationMm: 180,
      prescriptionCount: 2,
    });
    expect(r.hasData).toBe(true);
    expect(r.title).toContain('حقل الشمال');
    const labels = r.facts.map((f) => f.label);
    expect(labels).toContain('المحصول');
    expect(labels).toContain('البذار');
    expect(labels).toContain('الماء المُطبَّق');
    expect(labels).toContain('وصفات التطبيق المتغيّر');
    expect(r.operations).toHaveLength(2);

    const md = traceabilityToMarkdown(r);
    expect(md).toContain('# سجلّ حقل الشمال');
    expect(md).toContain('- **المحصول:** قمح');
    expect(md).toContain('2026-04-10 — ريّ');
  });

  it('omits missing/zero values instead of fabricating them', () => {
    const r = buildTraceabilityReport({ fieldName: 'حقل', crop: 'ذرة', areaHa: 0, irrigationMm: 0, prescriptionCount: 0 });
    const labels = r.facts.map((f) => f.label);
    expect(labels).toContain('المحصول');
    expect(labels).not.toContain('المساحة'); // area 0 omitted
    expect(labels).not.toContain('الماء المُطبَّق'); // 0 mm omitted
    expect(labels).not.toContain('وصفات التطبيق المتغيّر'); // 0 omitted
  });
});
