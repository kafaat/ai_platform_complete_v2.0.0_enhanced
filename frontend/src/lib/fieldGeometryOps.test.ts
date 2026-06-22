// اختبارات عمليّات دمج/تقسيم حدود الحقول (Split & Merge) — هندسة نقيّة، أمانة صارمة.
// نتحقّق من حفظ المساحة (دمج مربّعين متجاورين → مضلّع واحد؛ تقسيم مربّع بنصف →
// جزأين تجمع مساحتاهما الأصل) ومن السلوك الصادق عند الحالات الحدّيّة (لا تجاور →
// MultiPolygon؛ قصّ لا يتقاطع → null؛ مُدخَل ناقص → null).
import { describe, it, expect } from 'vitest';
import { areaSqMeters } from './geo';
import {
  mergeFieldGeometries,
  splitFieldGeometry,
  toTurfFeature,
  isMultiPolygon,
  type PolygonGeometry,
} from './fieldGeometryOps';

// مربّع GeoJSON [lon,lat] مغلق من (x0,y0) إلى (x1,y1).
function square(x0: number, y0: number, x1: number, y1: number): PolygonGeometry {
  return {
    type: 'Polygon',
    coordinates: [[
      [x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0],
    ]],
  };
}

// تسامح نسبيّ صغير لأخطاء التقريب الهندسيّة (turf على القطع الإهليلجيّ).
function approxEqual(a: number, b: number, relTol = 1e-3): boolean {
  return Math.abs(a - b) <= relTol * Math.max(Math.abs(a), Math.abs(b), 1);
}

describe('mergeFieldGeometries — دمج (UNION)', () => {
  it('مربّعان متجاوران (يتشاركان حدّاً) → مضلّع واحد، المساحة محفوظة', () => {
    const left = square(44.0, 15.0, 44.1, 15.1);
    const right = square(44.1, 15.0, 44.2, 15.1); // يلامس left عند lon=44.1
    const merged = mergeFieldGeometries([left, right]);
    expect(merged).not.toBeNull();
    expect(merged!.type).toBe('Polygon'); // متجاوران ⇒ جزء واحد
    const areaMerged = areaSqMeters(merged);
    const areaSum = areaSqMeters(left) + areaSqMeters(right);
    expect(approxEqual(areaMerged, areaSum)).toBe(true);
  });

  it('مربّعان متداخلان جزئيّاً → مساحة الاتّحاد < مجموع المساحتين (لا ازدواج)', () => {
    const a = square(44.0, 15.0, 44.1, 15.1);
    const b = square(44.05, 15.05, 44.15, 15.15); // تداخل جزئيّ
    const merged = mergeFieldGeometries([a, b]);
    expect(merged).not.toBeNull();
    const areaMerged = areaSqMeters(merged);
    const areaSum = areaSqMeters(a) + areaSqMeters(b);
    expect(areaMerged).toBeLessThan(areaSum);
    expect(areaMerged).toBeGreaterThan(areaSqMeters(a));
  });

  it('مربّعان منفصلان (غير متجاورين) → MultiPolygon (لا إسقاط لأيّ جزء)', () => {
    const a = square(44.0, 15.0, 44.1, 15.1);
    const far = square(45.0, 16.0, 45.1, 16.1); // بعيد جدّاً
    const merged = mergeFieldGeometries([a, far]);
    expect(merged).not.toBeNull();
    expect(isMultiPolygon(merged)).toBe(true);
    // كلا الجزأين محفوظ: مساحة الاتّحاد ≈ مجموع المساحتين.
    expect(approxEqual(areaSqMeters(merged), areaSqMeters(a) + areaSqMeters(far))).toBe(true);
  });

  it('دمج ثلاثة مربّعات متجاورة في صفّ → جزء واحد، المساحة محفوظة', () => {
    const a = square(44.0, 15.0, 44.1, 15.1);
    const b = square(44.1, 15.0, 44.2, 15.1);
    const c = square(44.2, 15.0, 44.3, 15.1);
    const merged = mergeFieldGeometries([a, b, c]);
    expect(merged).not.toBeNull();
    expect(merged!.type).toBe('Polygon');
    const sum = areaSqMeters(a) + areaSqMeters(b) + areaSqMeters(c);
    expect(approxEqual(areaSqMeters(merged), sum)).toBe(true);
  });

  it('أقلّ من حقلين صالحين → null (الدمج يتطلّب اثنين)', () => {
    expect(mergeFieldGeometries([square(44, 15, 44.1, 15.1)])).toBeNull();
    expect(mergeFieldGeometries([])).toBeNull();
    expect(mergeFieldGeometries([null, undefined])).toBeNull();
    expect(mergeFieldGeometries([square(44, 15, 44.1, 15.1), { type: 'Point' }])).toBeNull();
  });
});

describe('splitFieldGeometry — تقسيم (تقاطع/فرق)', () => {
  it('مربّع + قصّ نصفه → جزآن تجمع مساحتاهما الأصل', () => {
    const field = square(44.0, 15.0, 44.2, 15.2);
    // قصّ النصف الأيسر (lon 44.0..44.1)، يمتدّ رأسيّاً بما يغطّي الحقل كاملاً.
    const cut = square(43.95, 14.95, 44.1, 15.25);
    const result = splitFieldGeometry(field, cut);
    expect(result).not.toBeNull();
    const { partA, partB } = result!;
    const total = areaSqMeters(field);
    const sumParts = areaSqMeters(partA) + areaSqMeters(partB);
    expect(approxEqual(sumParts, total)).toBe(true);
    // كلّ جزء ذو مساحة موجبة فعليّة (تقسيم حقيقيّ لا جزء صفريّ).
    expect(areaSqMeters(partA)).toBeGreaterThan(0);
    expect(areaSqMeters(partB)).toBeGreaterThan(0);
    // النصف ≈ نصف المساحة الكلّيّة.
    expect(approxEqual(areaSqMeters(partA), total / 2, 1e-2)).toBe(true);
  });

  it('قصّ لا يتقاطع مع الحقل → null (لا تقاطع ⇒ لا تقسيم)', () => {
    const field = square(44.0, 15.0, 44.1, 15.1);
    const cut = square(45.0, 16.0, 45.1, 16.1); // منفصل تماماً
    expect(splitFieldGeometry(field, cut)).toBeNull();
  });

  it('قصّ يبتلع الحقل كاملاً → null (الباقي فارغ ⇒ لا جزأين)', () => {
    const field = square(44.0, 15.0, 44.1, 15.1);
    const cut = square(43.5, 14.5, 44.5, 15.5); // يحيط بالحقل كلّه
    expect(splitFieldGeometry(field, cut)).toBeNull();
  });

  it('مُدخَل ناقص (هندسة غير مساحيّة) → null', () => {
    const field = square(44.0, 15.0, 44.1, 15.1);
    expect(splitFieldGeometry(field, null)).toBeNull();
    expect(splitFieldGeometry(null, field)).toBeNull();
    expect(splitFieldGeometry({ type: 'Point' }, field)).toBeNull();
  });
});

describe('toTurfFeature — قراءة دفاعيّة', () => {
  it('يقبل Polygon صالحاً ويرفض الناقص', () => {
    expect(toTurfFeature(square(44, 15, 44.1, 15.1))).not.toBeNull();
    expect(toTurfFeature(null)).toBeNull();
    expect(toTurfFeature(undefined)).toBeNull();
    expect(toTurfFeature({ type: 'Polygon', coordinates: [[[44, 15]]] })).toBeNull(); // < 4 رؤوس
    expect(toTurfFeature({ type: 'LineString', coordinates: [] })).toBeNull();
  });
});
