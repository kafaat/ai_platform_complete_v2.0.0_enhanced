// اختبارات أدوات الهندسة — geomToPolygon (تحويل ترتيب الإحداثيّات + الحدّ الأدنى
// للرؤوس) وقياسات turf (مساحة/طول مع التسامح مع المُدخَل غير الصالح).
import { describe, it, expect } from 'vitest';
import {
  geomToPolygon,
  areaSqMeters,
  lengthMeters,
  fieldRepresentativePoint,
  collectFieldBoundsPoints,
  snapPoint,
  snapRing,
  type SnapTarget,
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
    // تحقّق رقميّ دقيق (لا حدّ فضفاض): 0.001°×0.001° عند خطّ الاستواء ⇒ 12392.03 م²
    // (قيمة turf@WGS84 المرجعيّة، مثبَّتة رقميّاً — لا حدّ فضفاض).
    expect(area).toBeCloseTo(12392.03, 1); // ضمن ~±0.05 م²
    expect(area / 10000).toBeCloseTo(1.2392, 3); // ≈ 1.2392 هكتار (نسبة مشتقّة دقيقة)
  });

  it('يحسب مساحة مربّع 0.01°×0.01° بنسبة ~100× مربّع 0.001° (مقياس تربيعيّ)', () => {
    const small = areaSqMeters({
      type: 'Polygon',
      coordinates: [[[0, 0], [0.001, 0], [0.001, 0.001], [0, 0.001], [0, 0]]],
    });
    const big = areaSqMeters({
      type: 'Polygon',
      coordinates: [[[0, 0], [0.01, 0], [0.01, 0.01], [0, 0.01], [0, 0]]],
    });
    // المساحة تتناسب مع مربّع الطول ⇒ النسبة ≈ 100 (تحقّق مقياسيّ حتميّ).
    expect(big / small).toBeCloseTo(100, 0);
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
    // تحقّق رقميّ دقيق: 0.001° على خطّ الاستواء ⇒ ~111.19م (turf earthRadius=6371008.8).
    // لو كانت الوحدة كم لكانت ~0.111 (نمنع انحدار الوحدات صراحةً).
    expect(len).toBeCloseTo(111.19, 1); // ضمن ~±0.05م
    expect(len).toBeGreaterThan(1); // ليست بالكيلومتر
  });

  it('يُرجِع صفراً عند مُدخَل غير صالح', () => {
    expect(lengthMeters(undefined)).toBe(0);
    expect(lengthMeters({})).toBe(0);
  });
});

// ── G — الالتقاط للحدود (snapPoint / snapRing) ───────────────────────
// حدّ حقل قائم: مربّع صغير قرب خطّ الاستواء (~111م ضلعاً عند 0.001 درجة).
// [lat, lng] كما تستهلكه الواجهة. ملاحظة: 1e-5 درجة ≈ 1.1م (ضمن التسامح ~8م).
const _existingRing: SnapTarget = [
  [15.0,       44.0],
  [15.0,       44.001],
  [15.001,     44.001],
  [15.001,     44.0],
  [15.0,       44.0],
];

describe('snapPoint (الالتقاط لأقرب رأس/ضلع ضمن التسامح)', () => {
  it('يلتقط لرأس قائم قريب جدّاً (kind=vertex)', () => {
    // نقطة على بعد ~1م من رأس [15.0, 44.0].
    const r = snapPoint([15.00001, 44.0], [_existingRing], 8);
    expect(r.snapped).toBe(true);
    expect(r.kind).toBe('vertex');
    expect(r.point[0]).toBeCloseTo(15.0, 6);
    expect(r.point[1]).toBeCloseTo(44.0, 6);
    expect(r.distM).toBeLessThan(8);
  });

  it('يلتقط لأقرب ضلع (إسقاط عموديّ) لا لرأس حين النقطة على منتصف ضلع', () => {
    // نقطة قرب منتصف الضلع السفليّ (lng≈44.0005) بإزاحة طفيفة عن الخطّ.
    const r = snapPoint([15.00001, 44.0005], [_existingRing], 8);
    expect(r.snapped).toBe(true);
    expect(r.kind).toBe('edge');
    // تُسقَط على الضلع (lat≈15.0) فتقترب من خطّ الحدّ.
    expect(r.point[0]).toBeCloseTo(15.0, 4);
    expect(r.point[1]).toBeCloseTo(44.0005, 4);
  });

  it('لا يلتقط حين النقطة أبعد من التسامح (snapped=false، تُعاد كما هي)', () => {
    // ~110م بعيداً عن الحدّ (0.001 درجة) — خارج تسامح 8م.
    const p: [number, number] = [15.0, 43.999];
    const r = snapPoint(p, [_existingRing], 8);
    expect(r.snapped).toBe(false);
    expect(r.kind).toBe('none');
    expect(r.point).toEqual(p);
    expect(r.distM).toBe(0);
  });

  it('بلا أهداف ⇒ لا التقاط (تُعاد النقطة كما هي)', () => {
    const p: [number, number] = [15.0, 44.0];
    expect(snapPoint(p, [], 8).snapped).toBe(false);
  });

  it('يتسامح مع رؤوس/أهداف غير صالحة دون أن يرمي', () => {
    const bad = [[NaN, 1], [2]] as unknown as SnapTarget;
    const r = snapPoint([15.0, 44.0], [bad], 8);
    expect(r.snapped).toBe(false);
  });
});

describe('snapRing (التقاط حلقة الرسم — حدود قائمة + إغلاق البداية)', () => {
  it('يلتقط الرؤوس القريبة من حدّ قائم ويُبقي البعيدة', () => {
    // رأس قريب من زاوية الحدّ القائم (يُلتقَط) + رأسان بعيدان (يبقيان).
    const ring: [number, number][] = [
      [15.00001, 44.00001], // قرب رأس الحدّ [15.0, 44.0] ⇒ يُلتقَط
      [16.0, 45.0],
      [16.0, 45.5],
    ];
    const out = snapRing(ring, [_existingRing], 8);
    expect(out).toHaveLength(3);
    expect(out[0][0]).toBeCloseTo(15.0, 5); // التُقِط للرأس
    expect(out[1]).toEqual([16.0, 45.0]);   // بعيد ⇒ كما هو
    expect(out[2]).toEqual([16.0, 45.5]);
  });

  it('يُغلق البداية: رأس قريب من رأس البداية يُلتقَط إليه حتى بلا حدود قائمة', () => {
    // مربّع ~110م ضلعاً؛ الرأس الأخير قرب رأس البداية ⇒ يُلتقَط لإغلاق نظيف.
    const ring: [number, number][] = [
      [15.0, 44.0],
      [15.001, 44.0],
      [15.001, 44.001],
      [15.000005, 44.000005], // قرب البداية (~0.7م) ⇒ يُلتقَط لرأس [0]
    ];
    const out = snapRing(ring, [], 8);
    expect(out[3][0]).toBeCloseTo(15.0, 5);
    expect(out[3][1]).toBeCloseTo(44.0, 5);
  });

  it('مُدخَل قصير/فارغ يُعاد بأمان', () => {
    expect(snapRing([], [_existingRing], 8)).toEqual([]);
    const two: [number, number][] = [[15.0, 44.0], [15.001, 44.0]];
    expect(snapRing(two, [], 8)).toEqual(two); // أقصر من 3 ⇒ لا التقاط بداية
  });
});
