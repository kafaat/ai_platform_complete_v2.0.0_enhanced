// اختبارات أدوات الهندسة — geomToPolygon (تحويل ترتيب الإحداثيّات + الحدّ الأدنى
// للرؤوس) وقياسات turf (مساحة/طول مع التسامح مع المُدخَل غير الصالح).
import { describe, it, expect } from 'vitest';
import {
  geomToPolygon,
  areaSqMeters,
  lengthMeters,
  fieldRepresentativePoint,
  collectFieldBoundsPoints,
} from './geo';

const _poly = {
  coordinates: [
    [
      [44.0, 15.0],
      [44.2, 15.0],
      [44.2, 15.2],
      [44.0, 15.2],
      [44.0, 15.0],
    ],
  ],
};

describe('fieldRepresentativePoint (خريطة المزرعة الشاملة)', () => {
  it('مركز المضلّع (متوسّط الرؤوس) كـ[lat,lng] إن توفّرت هندسة', () => {
    const p = fieldRepresentativePoint({ geometry: _poly, lat: null, lon: null });
    expect(p).not.toBeNull();
    // متوسّط lat/lng للرؤوس الخمسة (الإغلاق مكرّر فيرجّح زاوية — قيمة محصورة ضمن الحدود).
    expect(p![0]).toBeGreaterThan(14.9);
    expect(p![0]).toBeLessThan(15.3);
    expect(p![1]).toBeGreaterThan(43.9);
    expect(p![1]).toBeLessThan(44.3);
  });

  it('يسقط إلى lat/lon حين لا هندسة', () => {
    expect(fieldRepresentativePoint({ geometry: null, lat: 15.5, lon: 44.5 })).toEqual([15.5, 44.5]);
  });

  it('null حين لا هندسة ولا إحداثيّات', () => {
    expect(fieldRepresentativePoint({ geometry: undefined, lat: null, lon: null })).toBeNull();
  });
});

describe('collectFieldBoundsPoints', () => {
  it('يجمع رؤوس مضلّع الحقول + نقاط الحقول بلا هندسة', () => {
    const pts = collectFieldBoundsPoints([
      { geometry: _poly, lat: null, lon: null }, // 5 رؤوس
      { geometry: null, lat: 16.0, lon: 45.0 }, // نقطة احتياطيّة
    ]);
    expect(pts.length).toBe(6);
    expect(pts).toContainEqual([16.0, 45.0]);
    // كلّ النقاط [lat,lng] صالحة عدديّاً.
    for (const [lat, lng] of pts) {
      expect(Number.isFinite(lat) && Number.isFinite(lng)).toBe(true);
    }
  });

  it('يتجاهل الحقول التي لا هندسة ولا إحداثيّات لها', () => {
    const pts = collectFieldBoundsPoints([{ geometry: null, lat: null, lon: null }]);
    expect(pts).toEqual([]);
  });
});

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
