// اختبارات أدوات الهندسة — geomToPolygon (تحويل ترتيب الإحداثيّات + الحدّ الأدنى
// للرؤوس) وقياسات turf (مساحة/طول مع التسامح مع المُدخَل غير الصالح).
import { describe, it, expect } from 'vitest';
import { geomToPolygon, areaSqMeters, lengthMeters } from './geo';

describe('geomToPolygon', () => {
  it('يقلب [lon,lat] إلى [lat,lng] لكلّ رأس', () => {
    const geom = {
      coordinates: [[
        [10, 20],
        [11, 21],
        [12, 22],
      ]],
    };
    expect(geomToPolygon(geom)).toEqual([
      [20, 10],
      [21, 11],
      [22, 12],
    ]);
  });

  it('يُرجِع undefined إذا قصُرت الحلقة عن ثلاثة رؤوس', () => {
    expect(geomToPolygon({ coordinates: [[[1, 2], [3, 4]]] })).toBeUndefined();
  });

  it('يُرجِع undefined لهندسة غائبة/بلا حلقة', () => {
    expect(geomToPolygon(undefined)).toBeUndefined();
    expect(geomToPolygon(null)).toBeUndefined();
    expect(geomToPolygon({})).toBeUndefined();
    expect(geomToPolygon({ coordinates: [] })).toBeUndefined();
  });

  it('يُسقِط الرؤوس غير الصالحة (أقلّ من إحداثيّين)', () => {
    const geom = {
      coordinates: [[
        [10, 20],
        [99],          // غير صالح — يُسقَط
        [11, 21],
        [12, 22],
      ]],
    };
    expect(geomToPolygon(geom)).toEqual([
      [20, 10],
      [21, 11],
      [22, 12],
    ]);
  });
});

describe('areaSqMeters', () => {
  it('يحسب مساحة مضلّع GeoJSON بالمتر المربّع (موجبة لمضلّع حقيقيّ)', () => {
    // مربّع صغير قرب خطّ الاستواء (~0.001 درجة ≈ 111م ضلعاً)
    const polygon = {
      type: 'Polygon',
      coordinates: [[
        [0, 0],
        [0.001, 0],
        [0.001, 0.001],
        [0, 0.001],
        [0, 0],
      ]],
    };
    const area = areaSqMeters(polygon);
    expect(area).toBeGreaterThan(10000); // ~12,300 م²
    expect(area).toBeLessThan(15000);
  });

  it('يُرجِع صفراً عند مُدخَل غير صالح بدل أن يرمي', () => {
    expect(areaSqMeters(undefined)).toBe(0);
    expect(areaSqMeters({})).toBe(0);
  });
});

describe('lengthMeters', () => {
  it('يحسب طول خطّ بالمتر (لا بالكيلومتر)', () => {
    const line = {
      type: 'LineString',
      coordinates: [[0, 0], [0.001, 0]],
    };
    const len = lengthMeters(line);
    // ~111م لطول 0.001 درجة عند خطّ الاستواء — لو كان بالكم لكان ~0.111
    expect(len).toBeGreaterThan(100);
    expect(len).toBeLessThan(120);
  });

  it('يُرجِع صفراً عند مُدخَل غير صالح', () => {
    expect(lengthMeters(undefined)).toBe(0);
    expect(lengthMeters({})).toBe(0);
  });
});
