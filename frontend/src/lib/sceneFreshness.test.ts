// اختبارات sceneFreshness — مقارنة توقيت/مشهد بيانات الطبقة (FieldView).
// صدق: المقارنة المتاحة اليوم هي تاريخ مشهد الطبقة مقابل التاريخ المختار للعرض؛
// غياب أحد التاريخين ⇒ unknown (لا تحذير مُلفّق). المقارنة الكاملة (scene_id/
// field_revision) مُختبَرة على المسار المُسقَط حتى تُرجِعها الواجهة الخلفيّة.
import { describe, it, expect } from 'vitest';
import { compareSceneFreshness, compareSceneProvenance } from './sceneFreshness';

describe('compareSceneFreshness — تاريخ الطبقة مقابل تاريخ العرض', () => {
  it('تاريخان مختلفان ⇒ mismatch (طبقة من مشهد أقدم/مختلف)', () => {
    const r = compareSceneFreshness('2026-05-01', '2026-06-10');
    expect(r.level).toBe('mismatch');
    expect(r.reason).toBe('scene-mismatch');
    expect(r.layerDate).toBe('2026-05-01');
    expect(r.displayDate).toBe('2026-06-10');
  });

  it('تاريخان متطابقان ⇒ match', () => {
    const r = compareSceneFreshness('2026-06-10', '2026-06-10');
    expect(r.level).toBe('match');
    expect(r.reason).toBe('same-scene');
  });

  it('يتسامح مع ISO الكامل (يقارن باليوم فقط)', () => {
    const r = compareSceneFreshness('2026-06-10T09:30:00Z', '2026-06-10');
    expect(r.level).toBe('match');
  });

  it('العرض على «latest» ⇒ unknown (لا مقارنة معنويّة)', () => {
    const r = compareSceneFreshness('2026-06-10', 'latest');
    expect(r.level).toBe('unknown');
    expect(r.reason).toBe('no-display-date');
  });

  it('عرض فارغ ⇒ unknown', () => {
    const r = compareSceneFreshness('2026-06-10', '');
    expect(r.level).toBe('unknown');
    expect(r.reason).toBe('no-display-date');
  });

  it('لا تاريخ للطبقة ⇒ unknown (لا نُلفّق تحذيراً)', () => {
    const r = compareSceneFreshness(null, '2026-06-10');
    expect(r.level).toBe('unknown');
    expect(r.reason).toBe('no-layer-date');
  });

  it('تاريخ غير صالح ⇒ unknown', () => {
    expect(compareSceneFreshness('not-a-date', '2026-06-10').level).toBe('unknown');
  });
});

describe('compareSceneProvenance — المقارنة الكاملة (مُسقَطة على التاريخ اليوم)', () => {
  it('بلا حقول مزوّد ⇒ يسقط إلى مقارنة captured_at', () => {
    const r = compareSceneProvenance(
      { captured_at: '2026-05-01' },
      { captured_at: '2026-06-10' },
    );
    expect(r.level).toBe('mismatch');
  });

  it('اختلاف scene_id ⇒ mismatch (حين يصل الحقل من الواجهة)', () => {
    const r = compareSceneProvenance(
      { scene_id: 'S2A_OLD', captured_at: '2026-06-10' },
      { scene_id: 'S2A_NEW', captured_at: '2026-06-10' },
    );
    expect(r.level).toBe('mismatch');
  });

  it('اختلاف field_revision ⇒ mismatch (هندسة الحقل تغيّرت)', () => {
    const r = compareSceneProvenance(
      { field_revision: 1, captured_at: '2026-06-10' },
      { field_revision: 2, captured_at: '2026-06-10' },
    );
    expect(r.level).toBe('mismatch');
  });

  it('تطابق scene_id + field_revision ⇒ match', () => {
    const r = compareSceneProvenance(
      { scene_id: 'S2A', field_revision: 3, captured_at: '2026-06-10' },
      { scene_id: 'S2A', field_revision: 3, captured_at: '2026-06-10' },
    );
    expect(r.level).toBe('match');
  });

  it('مزوّد ناقص (null) ⇒ يسقط إلى مقارنة التاريخ', () => {
    expect(compareSceneProvenance(null, null).level).toBe('unknown');
  });
});
