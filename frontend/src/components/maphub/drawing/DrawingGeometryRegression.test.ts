// ═══════════════════════════════════════════════════════════════
// SAHOOL — انحدار هندسة مسار الرسم الجديد (DrawingCore) — تدقيق RS 2026-10-27
// ───────────────────────────────────────────────────────────────
// G-DRAW-1: المساحة الصافية = الحلقة الخارجيّة − الثقوب (نفس الصيغة الكرويّة لكلّ حلقة)،
//           والمحيط يشمل كلّ الحلقات (اصطلاح ST_Perimeter/Turf). كان المسار يقيس
//           coordinates[0] فقط فيُبالغ ~33٪ في مربّع بثقب نصف العرض (119.43 بدل 89.57 هـ).
// G-DRAW-2: فحص التقاطع الذاتيّ يجب أن يلتقط «ربطة عنق» برؤوس أربعة متمايزة (تقاطع
//           قطعتين غير متجاورتين)، لا الرؤوس المكرّرة وحدها.
// ═══════════════════════════════════════════════════════════════
import { describe, expect, it } from 'vitest';
import { measureDrawFeature } from './drawingMeasurements';
import { validateDrawFeature } from './drawingValidation';
import type { DrawFeature, Position } from './drawingTypes';

const square = (x: number, y: number, w: number): Position[] => [
  [x, y], [x + w, y], [x + w, y + w], [x, y + w], [x, y],
];

function feature(geometry: DrawFeature['geometry']): DrawFeature {
  return { id: 'f', kind: 'field', geometry, properties: {}, version: 1, draft: true };
}

const OUTER = square(44, 15, 0.01);
const HOLE = square(44.0025, 15.0025, 0.005);

describe('G-DRAW-1 — measureDrawFeature يطرح الثقوب', () => {
  const outer = measureDrawFeature(feature({ type: 'Polygon', coordinates: [OUTER] }));
  const hole = measureDrawFeature(feature({ type: 'Polygon', coordinates: [HOLE] }));

  it('Polygon بثقب: المساحة = الخارجيّة − الثقب (89.57 هـ لا 119.43)', () => {
    const donut = measureDrawFeature(feature({ type: 'Polygon', coordinates: [OUTER, HOLE] }));
    const expected = (outer.areaHa ?? 0) - (hole.areaHa ?? 0);
    expect(expected).toBeCloseTo(89.5707, 3);
    expect(donut.areaHa).toBeCloseTo(expected, 6);
    // المحيط يشمل حدّ الثقب الداخليّ (ST_Perimeter).
    expect(donut.perimeterM).toBeCloseTo((outer.perimeterM ?? 0) + (hole.perimeterM ?? 0), 6);
  });

  it('اتّجاه حلقة الثقب (CW/CCW) لا يغيّر الطرح', () => {
    const reversedHole = [...HOLE].reverse();
    const donut = measureDrawFeature(feature({ type: 'Polygon', coordinates: [OUTER, reversedHole] }));
    expect(donut.areaHa).toBeCloseTo((outer.areaHa ?? 0) - (hole.areaHa ?? 0), 6);
  });

  it('MultiPolygon: يطرح ثقوب كلّ جزء', () => {
    const other = square(44.1, 15, 0.01);
    const multi = measureDrawFeature(feature({ type: 'MultiPolygon', coordinates: [[OUTER, HOLE], [other]] }));
    const otherHa = measureDrawFeature(feature({ type: 'Polygon', coordinates: [other] })).areaHa ?? 0;
    expect(multi.areaHa).toBeCloseTo((outer.areaHa ?? 0) - (hole.areaHa ?? 0) + otherHa, 6);
  });

  it('حدّ المساحة القصوى في التحقّق يقرأ المساحة الصافية (89.57 هـ < 100 هـ يُقبَل)', () => {
    const res = validateDrawFeature(feature({ type: 'Polygon', coordinates: [OUTER, HOLE] }), { maxAreaHa: 100 });
    expect(res.issues.filter((i) => i.code === 'area-out-of-range')).toEqual([]);
  });
});

describe('G-DRAW-2 — فحص التقاطع الذاتيّ يلتقط تقاطع القطع', () => {
  const hasRisk = (ring: Position[]) =>
    validateDrawFeature(feature({ type: 'Polygon', coordinates: [ring] })).issues
      .some((i) => i.code === 'self-intersection-risk');

  it('ربطة عنق برؤوس أربعة متمايزة ⇒ تحذير تقاطع ذاتيّ', () => {
    const bowtie: Position[] = [[44, 15], [44.01, 15.01], [44.01, 15], [44, 15.01], [44, 15]];
    expect(hasRisk(bowtie)).toBe(true);
  });

  it('مضلّع بسيط (مربّع، ومضلّع مقعّر) ⇒ لا تحذير (لا إيجابيّات كاذبة على الأضلاع المتجاورة/الإغلاق)', () => {
    expect(hasRisk(OUTER)).toBe(false);
    const concave: Position[] = [[44, 15], [44.02, 15], [44.02, 15.02], [44.01, 15.005], [44, 15.02], [44, 15]];
    expect(hasRisk(concave)).toBe(false);
  });

  it('رأس مكرّر متتالٍ (نقرة إنهاء مزدوجة) ⇒ لا تحذير (ضلع صفريّ الطول لا يُعدّ تقاطعاً)', () => {
    const doubled: Position[] = [[44, 15], [44.01, 15], [44.01, 15], [44.01, 15.01], [44, 15.01], [44, 15]];
    expect(hasRisk(doubled)).toBe(false);
  });

  it('رأس مكرّر غير متجاور (سلوك قائم لحلقات SAM2) ⇒ يبقى التحذير', () => {
    const figure8: Position[] = [[44, 15], [44.01, 15], [44.005, 15.005], [44.01, 15.01], [44, 15.01], [44.005, 15.005], [44, 15]];
    expect(hasRisk(figure8)).toBe(true);
  });

  it('رأس يلامس ضلعاً غير مجاور (تماسّ T) ⇒ تحذير', () => {
    // الرأس الرابع (44.01,15) يقع على الضلع الأوّل (44,15)→(44.02,15) بلا تكرار رأس.
    const touching: Position[] = [[44, 15], [44.02, 15], [44.02, 15.02], [44.01, 15], [44, 15.02], [44, 15]];
    expect(hasRisk(touching)).toBe(true);
  });
});
