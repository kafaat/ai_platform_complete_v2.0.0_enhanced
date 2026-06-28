// ═══════════════════════════════════════════════════════════════
// SAHOOL — addField/geometry.ts
// أدوات هندسيّة نقيّة لمحرّر حدّ الحقل (AddFieldWithMap):
//   • geodesicAreaHa     — مساحة جيوديسيّة (هكتار)
//   • geodesicPerimeterM — محيط جيوديسي (متر)
//   • formatLengthM      — تنسيق عرض طول بالمتر/الكيلومتر
//   • circleToPolygon    — دائرة (ريّ محوريّ) → مضلّع رؤوس
// نُقِلت حرفيّاً من AddFieldWithMap.tsx (تفكيك محفوظ السلوك): دوالّ نقيّة بلا
// حالة React، تعتمد فقط على L.LatLng / L.latLng من Leaflet.
// ═══════════════════════════════════════════════════════════════
import L from 'leaflet';

// ── Geodesic area (الصيغة الكرويّة الصحيحة — تطابق Leaflet/Mapbox) ──
// إصلاح: الصيغة السابقة كانت تُرجع نصف المساحة الصحيحة (خطأ في خلط الحدود)،
// ما يعني نصف توصيات البذور/الأسمدة/الريّ. الصيغة أدناه مُتحقّق منها عدديّاً.
export function geodesicAreaHa(latlngs: L.LatLng[]): number {
  const R = 6378137; // نصف قطر WGS84 (متر)
  if (latlngs.length < 3) return 0;
  let area = 0;
  const n = latlngs.length;
  for (let i = 0; i < n; i++) {
    const p1 = latlngs[i];
    const p2 = latlngs[(i + 1) % n];
    area += ((p2.lng - p1.lng) * Math.PI / 180) *
            (2 + Math.sin(p1.lat * Math.PI / 180) + Math.sin(p2.lat * Math.PI / 180));
  }
  const sqm = Math.abs(area * R * R / 2);
  return sqm / 10000;
}

// ── محيط جيوديسي (متر) — مجموع المسافات بين الرؤوس المتتالية ─────
// يُستخدم نفس نصف قطر WGS84 (R = 6378137) ومعادلة هافرسين على القوس الأكبر.
// الحلقة مُغلقة: نضيف الضلع من آخر رأس إلى الأوّل تلقائيّاً عبر (i+1)%n.
export function geodesicPerimeterM(latlngs: L.LatLng[]): number {
  const R = 6378137; // نصف قطر WGS84 (متر) — نفس ثابت المساحة
  if (!Array.isArray(latlngs) || latlngs.length < 2) return 0;
  const rad = Math.PI / 180;
  let perim = 0;
  const n = latlngs.length;
  for (let i = 0; i < n; i++) {
    const p1 = latlngs[i];
    const p2 = latlngs[(i + 1) % n];
    if (!p1 || !p2) continue;
    const dLat = (p2.lat - p1.lat) * rad;
    const dLng = (p2.lng - p1.lng) * rad;
    const a =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(p1.lat * rad) * Math.cos(p2.lat * rad) * Math.sin(dLng / 2) ** 2;
    perim += 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }
  return perim;
}

// تنسيق طول بالمتر: < 10000 م يُعرَض بالمتر (رقمان)، وإلّا بالكيلومتر للقراءة.
// الوحدة تبقى المتر كأساس؛ هذا تنسيق عرض فقط (لا تحويل لأقدام/فدّان أبداً).
export function formatLengthM(m: number): string {
  if (!isFinite(m) || m <= 0) return '0 م';
  if (m >= 10000) return `${(m / 1000).toFixed(2)} كم`;
  return `${Math.round(m)} م`;
}

// ── دائرة (ريّ محوريّ) → مضلّع مُقرَّب ──────────────────────────
// الخلفيّة تتوقّع GeoJSON Polygon؛ نحوّل (مركز + نصف قطر م) إلى حلقة رؤوس.
export function circleToPolygon(center: L.LatLng, radiusM: number, n = 72): L.LatLng[] {
  // توليد دائرة جيوديسية حقيقية حول المركز بدل تقريب degree-per-meter.
  // هذا يقلل الإزاحة/التشوّه في الحقول المحورية الكبيرة ويحافظ على نصف القطر بالمتر.
  const R = 6378137; // WGS84 radius, meters
  const lat1 = center.lat * Math.PI / 180;
  const lon1 = center.lng * Math.PI / 180;
  const d = radiusM / R;
  const pts: L.LatLng[] = [];
  for (let i = 0; i < n; i++) {
    const brng = (i / n) * 2 * Math.PI;
    const lat2 = Math.asin(
      Math.sin(lat1) * Math.cos(d) +
      Math.cos(lat1) * Math.sin(d) * Math.cos(brng),
    );
    const lon2 = lon1 + Math.atan2(
      Math.sin(brng) * Math.sin(d) * Math.cos(lat1),
      Math.cos(d) - Math.sin(lat1) * Math.sin(lat2),
    );
    pts.push(L.latLng(lat2 * 180 / Math.PI, lon2 * 180 / Math.PI));
  }
  return pts;
}
