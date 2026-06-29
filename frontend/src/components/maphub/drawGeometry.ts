// ═══════════════════════════════════════════════════════════════
// SAHOOL — maphub/drawGeometry.ts
// هندسة نقيّة لأدوات الرسم التفاعليّة (لا DOM، ولا استيراد leaflet وقت التشغيل —
// أنواع فقط) كي تبقى قابلة للاختبار offline بلا الحاجة لتهيئة window/jsdom.
// نقاط الطبقة تُمرَّر/تُعاد ككائنات {x,y} عاديّة؛ Leaflet يقبل {x,y} في
// layerPointToLatLng عبر toPoint داخليّاً، فلا حاجة لـL.point هنا.
// ═══════════════════════════════════════════════════════════════
import type L from 'leaflet';

interface XY {
  x: number;
  y: number;
}

// رؤوس المستطيل المُدار من الضلع الأساس (A→B) ومؤشّر C: المسافة العموديّة المُوقَّعة
// من C إلى الخطّ AB تحدّد العمق. الحساب في فضاء بكسل layerPoint (مستقرّ مع pan) ثمّ
// يُعاد إلى إحداثيّات. يُعيد 4 رؤوس بترتيب حلقة: A, B, B+n·d, A+n·d.
export function rectangleCorners(map: L.Map, a: L.LatLng, b: L.LatLng, c: L.LatLng): L.LatLng[] {
  const pa = map.latLngToLayerPoint(a);
  const pb = map.latLngToLayerPoint(b);
  const pc = map.latLngToLayerPoint(c);
  const ex = pb.x - pa.x;
  const ey = pb.y - pa.y;
  const len = Math.hypot(ex, ey) || 1;
  const nx = -ey / len; // وحدة العموديّ على AB
  const ny = ex / len;
  const d = (pc.x - pb.x) * nx + (pc.y - pb.y) * ny; // مسافة موقّعة من C إلى AB
  const p3: XY = { x: pb.x + nx * d, y: pb.y + ny * d };
  const p4: XY = { x: pa.x + nx * d, y: pa.y + ny * d };
  return [a, b, map.layerPointToLatLng(p3 as L.Point), map.layerPointToLatLng(p4 as L.Point)];
}
