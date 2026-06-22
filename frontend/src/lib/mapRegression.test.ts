// ═══════════════════════════════════════════════════════════════
// SAHOOL — سويت Regression للخرائط (إغلاق المرحلة 1)
// ───────────────────────────────────────────────────────────────
// تُقفِل الثوابت المنطقيّة لطبقة GIS بعد دفعة الخرائط (Undo/Redo · التراكبات ·
// Split/Merge · de-modal · إصلاح RTL). البنود البصريّة التفاعليّة البحتة (سحب
// الرؤوس، الإزاحة الفعليّة) تتطلّب متصفّحاً حيّاً وتُوثَّق في مصفوفة الإغلاق؛ هنا
// نُثبِّت ما يُمكن إثباته آليّاً بدوالّ حقيقيّة (لا محاكاة كاذبة):
//   • عدم انقلاب lat/lng في دورة رسم→حفظ→قاعدة→إعادة فتح (geomToPolygon والتحويل
//     العكسيّ للحفظ متعاكسان تماماً).
//   • عقد صدق التراكبات: عنصر بلا حقل/هندسة لا يُوضَع على الخريطة (يُسقَط ويُعَدّ).
//   • تطابق حمولة الحفظ (GeoJSON [lng,lat] · حلقة مُغلَقة).
// ملاحظة: Split/Merge مُغطّى بالكامل في fieldGeometryOps.test.ts؛ هنا لا نُكرّره.
// ═══════════════════════════════════════════════════════════════
import { describe, it, expect } from 'vitest';
import { geomToPolygon, fieldRepresentativePoint, type MappableField } from './geo';

// التحويل العكسيّ للحفظ كما هو في AddFieldWithMap.handleSave (السطر ~455):
//   رؤوس Leaflet {lat,lng} → GeoJSON [lng,lat] مع إغلاق الحلقة بالرأس الأوّل.
// نُعيد إنتاجه هنا حرفيّاً لنُثبِّت أنّه معكوس geomToPolygon (لا انقلاب محاور).
function leafletRingToGeoJsonRing(ring: [number, number][]): number[][] {
  const pts = ring.map(([lat, lng]) => ({ lat, lng }));
  return [...pts.map((p) => [p.lng, p.lat]), [pts[0].lng, pts[0].lat]];
}

describe('Regression — عدم انقلاب lat/lng في الدورة الكاملة (رسم→حفظ→قاعدة→إعادة فتح)', () => {
  // مضلّع حقل بإحداثيّات GeoJSON [lon,lat] غير متماثلة (lon≠lat) كي ينكشف أيّ قلب.
  const geojsonRing = [
    [44.0, 15.0],
    [44.25, 15.0],
    [44.25, 15.2],
    [44.0, 15.2],
    [44.0, 15.0],
  ];
  const stored = { type: 'Polygon', coordinates: [geojsonRing] };

  it('إعادة الفتح: geomToPolygon يقلب [lon,lat]→[lat,lng] لكلّ رأس (lat أوّلاً)', () => {
    const leaflet = geomToPolygon(stored)!;
    expect(leaflet).toBeDefined();
    // أوّل رأس: GeoJSON [44,15] ⇒ Leaflet [15,44] (lat=15 قبل lng=44) — لا قلب.
    expect(leaflet[0]).toEqual([15.0, 44.0]);
    // كلّ النقاط lat ضمن [15,15.2] و lng ضمن [44,44.25] (لو انقلبت لخرجت عن النطاق).
    for (const [lat, lng] of leaflet) {
      expect(lat).toBeGreaterThanOrEqual(15.0);
      expect(lat).toBeLessThanOrEqual(15.2);
      expect(lng).toBeGreaterThanOrEqual(44.0);
      expect(lng).toBeLessThanOrEqual(44.25);
    }
  });

  it('الدورة معكوسة تماماً: GeoJSON → Leaflet (تحميل) → GeoJSON (حفظ) = الأصل', () => {
    const leaflet = geomToPolygon(stored)!; // تحميل (geomToPolygon يُسقِط رأس الإغلاق المكرّر؟ لا — يُبقي كلّ الرؤوس)
    const reSaved = leafletRingToGeoJsonRing(leaflet);
    // الحلقة الناتجة من الحفظ تُغلَق بالرأس الأوّل؛ نُقارن المحتوى الجوهريّ.
    // geomToPolygon أبقى الرؤوس الخمسة (مع الإغلاق)، فالحفظ يُضيف إغلاقاً سادساً مطابقاً.
    expect(reSaved.slice(0, geojsonRing.length)).toEqual(geojsonRing);
    // الرأس الأخير المُضاف للحفظ = الرأس الأوّل (إغلاق نظيف، لا قيمة ملفّقة).
    expect(reSaved[reSaved.length - 1]).toEqual(geojsonRing[0]);
  });

  it('حمولة الحفظ بترتيب GeoJSON [lng,lat] لا [lat,lng]', () => {
    const leaflet: [number, number][] = [
      [15.0, 44.0], // [lat,lng]
      [15.0, 44.25],
      [15.2, 44.25],
    ];
    const saved = leafletRingToGeoJsonRing(leaflet);
    // أوّل رأس محفوظ: [lng=44, lat=15] — الطول أوّلاً (GeoJSON)، لا العكس.
    expect(saved[0]).toEqual([44.0, 15.0]);
  });
});

describe('Regression — عقد صدق تراكبات الطقس/التنبيهات/الأجهزة (لا اختلاق إحداثيّات)', () => {
  // التراكبات تضع العنصر على نقطة حقله الممثِّلة فقط؛ ما لا حقل/هندسة له يُسقَط ويُعَدّ.
  // نُثبِّت العقد عبر الدالّة الحقيقيّة fieldRepresentativePoint + مُخفِّض المطابقة.
  type OverlayItem = { id: string; fieldId: string | null };
  const fields: Record<string, MappableField> = {
    f_geom: { geometry: { coordinates: [[[44, 15], [44.1, 15], [44.1, 15.1], [44, 15]]] }, lat: null, lon: null },
    f_point: { geometry: null, lat: 15.5, lon: 44.5 }, // لا هندسة لكن نقطة احتياطيّة
    f_empty: { geometry: null, lat: null, lon: null }, // لا شيء — غير قابل للوضع
  };

  // مُخفِّض يطابق منطق MapHub: عنصر→نقطة حقله؛ null⇒غير قابل للوضع.
  function placeMarkers(items: OverlayItem[]) {
    const placed: { id: string; lat: number; lng: number }[] = [];
    let unplaceable = 0;
    for (const it of items) {
      const f = it.fieldId ? fields[it.fieldId] : undefined;
      const pt = f ? fieldRepresentativePoint(f) : null;
      if (pt) placed.push({ id: it.id, lat: pt[0], lng: pt[1] });
      else unplaceable += 1;
    }
    return { placed, unplaceable };
  }

  it('عنصر بحقل ذي هندسة → يُوضَع على مركز المضلّع', () => {
    const { placed, unplaceable } = placeMarkers([{ id: 'a1', fieldId: 'f_geom' }]);
    expect(placed).toHaveLength(1);
    expect(unplaceable).toBe(0);
    // ضمن حدود المضلّع (لا قيمة ملفّقة خارجه).
    expect(placed[0].lat).toBeGreaterThanOrEqual(15);
    expect(placed[0].lng).toBeGreaterThanOrEqual(44);
  });

  it('عنصر بلا field_id → يُسقَط ويُعَدّ (لا إحداثيّ مُختلَق)', () => {
    const { placed, unplaceable } = placeMarkers([{ id: 'a2', fieldId: null }]);
    expect(placed).toHaveLength(0);
    expect(unplaceable).toBe(1);
  });

  it('عنصر بحقل بلا هندسة ولا نقطة → يُسقَط ويُعَدّ', () => {
    const { placed, unplaceable } = placeMarkers([{ id: 'a3', fieldId: 'f_empty' }]);
    expect(placed).toHaveLength(0);
    expect(unplaceable).toBe(1);
  });

  it('خليط: يُوضَع القابل ويُعَدّ غير القابل بدقّة (لا فقد صامت)', () => {
    const { placed, unplaceable } = placeMarkers([
      { id: 'a', fieldId: 'f_geom' },   // قابل (هندسة)
      { id: 'b', fieldId: 'f_point' },  // قابل (نقطة احتياطيّة)
      { id: 'c', fieldId: 'f_empty' },  // غير قابل
      { id: 'd', fieldId: null },       // غير قابل
    ]);
    expect(placed.map((p) => p.id)).toEqual(['a', 'b']);
    expect(unplaceable).toBe(2);
  });
});
