import { describe, expect, it } from 'vitest';
import { buildFieldHealthReport } from './fieldHealthReport';

const NOW = Date.parse('2026-07-04T00:00:00Z');

describe('buildFieldHealthReport', () => {
  it('returns an honest empty state when no field is active', () => {
    const r = buildFieldHealthReport({}, NOW);
    expect(r.fieldId).toBeNull();
    expect(r.confidence).toBe(0);
    expect(r.state.severity).toBe('warn');
    expect(r.nextAction?.cta).toContain('قائمة الحقول');
  });

  it('answers the five questions for a well-sourced field', () => {
    const r = buildFieldHealthReport({
      fieldId: 'F-1',
      fieldName: 'حقل الشمال',
      crop: 'قمح',
      areaHa: 12.4,
      imageryDates: [
        { date: '2026-07-02', has_cog: true, cloud_pct: 5 },
        { date: '2026-06-28', has_cog: true, cloud_pct: 10 },
      ],
      weatherReady: true,
      activeAlertsCount: 0,
      openTasksCount: 0,
      agentContextReady: true,
    }, NOW);

    expect(r.fieldId).toBe('F-1');
    expect(r.fieldLabel).toBe('حقل الشمال');
    expect(r.confidence).toBeGreaterThan(0);
    expect(r.state.headline).toContain('حقل الشمال');
    expect(r.reasons.length).toBeGreaterThan(0);
    expect(r.nextAction).not.toBeNull();
    // الدليل يحمل قيماً حقيقيّة مشتقّة من المدخلات (لا اختلاق)
    const imageryEvidence = r.evidence.find((e) => e.label === 'الصور');
    expect(imageryEvidence?.value).toContain('2026-07-02');
    const cropEvidence = r.evidence.find((e) => e.label === 'المحصول/المساحة');
    expect(cropEvidence?.value).toContain('قمح');
    expect(cropEvidence?.value).toContain('12.4');
  });

  it('surfaces missing imagery as a reason and operational impact (no fabricated cost)', () => {
    const r = buildFieldHealthReport({
      fieldId: 'F-2',
      fieldName: 'حقل الجنوب',
      crop: '—',
      areaHa: 0,
      imageryDates: [],
      weatherReady: false,
    }, NOW);

    expect(r.reasons.join(' ')).toContain('صور');
    expect(r.impact).toContain('الأثر التشغيليّ');
    // لا رقم عملة ملفَّق في الأثر
    expect(r.impact).not.toMatch(/\$|ريال|USD/);
    // مصادر ضعيفة موجودة ⇒ الحالة ليست "سليم" تماماً (قد تكون info/warn/critical حسب الوزن)
    expect(['info', 'warn', 'critical']).toContain(r.state.severity);
  });
});
