// ═══════════════════════════════════════════════════════════════
// SAHOOL — maphub/InteractiveDrawLayer.tsx
// أدوات رسم تفاعليّة بالنقر (دائرة + مستطيل مُدار) فوق الخريطة، بمعاينة حيّة
// تتبع مؤشّر الفأرة. تُكمّل أداة المضلّع (leaflet-draw) بلا أن تلمسها.
// ───────────────────────────────────────────────────────────────
//   • الدائرة: نقرة أولى = المركز، ثمّ تكبر/تصغر مع حركة الفأرة، ونقرة ثانية
//     تثبّتها. تُسلَّم (المركز + نصف القطر بالمتر) للمستهلِك الذي يحوّلها إلى
//     مضلّع نقاط كثيرة قابل للتحرير (نفس مسار الريّ المحوريّ).
//   • المستطيل المُدار: نقرة أولى وثانية تحدّدان الضلع الأوّل (باتّجاه حرّ)، ثمّ
//     يتّسع العرض عموديّاً مع حركة الفأرة، ونقرة ثالثة تُتمّ المستطيل. الحساب
//     يجري في فضاء البكسل (layerPoint) كي يبقى المستطيل قائم الزوايا بصريّاً.
//   • نقرة يمين (contextmenu) أو تبديل الأداة يُلغي الشكل قيد الرسم وينظّف المعاينة.
// المعاينة طبقات Leaflet مؤقّتة تُدار يدويّاً (لا حالة React) كي تتبع الفأرة بسلاسة.
// ═══════════════════════════════════════════════════════════════
import { useEffect, useRef } from 'react';
import { useMap, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import { rectangleCorners } from './drawGeometry';

export type DrawTool = 'circle' | 'rectangle' | null;

const PREVIEW_STYLE: L.PathOptions = {
  color: '#16a34a',
  fillColor: '#16a34a',
  fillOpacity: 0.18,
  weight: 2,
  dashArray: '6 6',
};

interface Props {
  tool: DrawTool;
  onCircle: (center: L.LatLng, radiusM: number) => void;
  onRectangle: (corners: L.LatLng[]) => void;
  onStatus?: (text: string | null) => void;
}

export default function InteractiveDrawLayer({ tool, onCircle, onRectangle, onStatus }: Props) {
  const map = useMap();
  const stepRef = useRef(0); // 0=بانتظار أوّل نقرة
  const aRef = useRef<L.LatLng | null>(null); // مركز الدائرة / رأس المستطيل A
  const bRef = useRef<L.LatLng | null>(null); // رأس المستطيل B
  const previewRef = useRef<L.Path | null>(null);

  const clearPreview = () => {
    if (previewRef.current) {
      previewRef.current.remove();
      previewRef.current = null;
    }
  };
  const reset = () => {
    stepRef.current = 0;
    aRef.current = null;
    bRef.current = null;
    clearPreview();
  };

  // إعادة الضبط عند تبديل الأداة أو التفكيك (لا بقايا معاينة).
  useEffect(() => {
    reset();
    if (tool === 'circle') onStatus?.('انقر لتحديد مركز الدائرة.');
    else if (tool === 'rectangle') onStatus?.('انقر النقطة الأولى للضلع.');
    else onStatus?.(null);
    return () => reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tool]);

  useMapEvents({
    click(e: L.LeafletMouseEvent) {
      if (!tool) return;
      const p = e.latlng;
      if (tool === 'circle') {
        if (stepRef.current === 0) {
          aRef.current = p;
          stepRef.current = 1;
          onStatus?.('حرّك الفأرة لضبط نصف القطر ثمّ انقر لوضع الدائرة.');
        } else {
          const center = aRef.current;
          if (center) {
            const r = center.distanceTo(p);
            clearPreview();
            reset();
            if (r > 0) onCircle(center, r);
          }
        }
      } else if (tool === 'rectangle') {
        if (stepRef.current === 0) {
          aRef.current = p;
          stepRef.current = 1;
          onStatus?.('انقر النقطة الثانية لتثبيت الضلع الأوّل.');
        } else if (stepRef.current === 1) {
          bRef.current = p;
          stepRef.current = 2;
          onStatus?.('حرّك الفأرة لضبط العرض ثمّ انقر لإتمام المستطيل.');
        } else {
          const a = aRef.current;
          const b = bRef.current;
          if (a && b) {
            const corners = rectangleCorners(map, a, b, p);
            clearPreview();
            reset();
            onRectangle(corners);
          }
        }
      }
    },
    mousemove(e: L.LeafletMouseEvent) {
      if (!tool || stepRef.current === 0) return;
      const p = e.latlng;
      if (tool === 'circle' && aRef.current) {
        const r = aRef.current.distanceTo(p);
        const prev = previewRef.current;
        if (prev instanceof L.Circle) {
          prev.setRadius(r);
        } else {
          clearPreview();
          previewRef.current = L.circle(aRef.current, { ...PREVIEW_STYLE, radius: r }).addTo(map);
        }
      } else if (tool === 'rectangle' && aRef.current) {
        if (stepRef.current === 1) {
          // معاينة الضلع الأوّل: خطّ A→المؤشّر.
          const pts: L.LatLngExpression[] = [aRef.current, p];
          const prev = previewRef.current;
          if (prev instanceof L.Polyline && !(prev instanceof L.Polygon)) {
            prev.setLatLngs(pts);
          } else {
            clearPreview();
            previewRef.current = L.polyline(pts, PREVIEW_STYLE).addTo(map);
          }
        } else if (stepRef.current === 2 && bRef.current) {
          const corners = rectangleCorners(map, aRef.current, bRef.current, p);
          const prev = previewRef.current;
          if (prev instanceof L.Polygon) {
            prev.setLatLngs(corners);
          } else {
            clearPreview();
            previewRef.current = L.polygon(corners, PREVIEW_STYLE).addTo(map);
          }
        }
      }
    },
    contextmenu() {
      // نقرة يمين تُلغي الشكل قيد الرسم (لا تُلغي اختيار الأداة).
      if (!tool || stepRef.current === 0) return;
      reset();
      if (tool === 'circle') onStatus?.('أُلغِي — انقر لتحديد مركز الدائرة.');
      else onStatus?.('أُلغِي — انقر النقطة الأولى للضلع.');
    },
  });

  return null;
}
