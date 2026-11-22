import { useEffect, useRef } from 'react';
import { useMap } from 'react-leaflet';
import L from 'leaflet';
import { ringSelfIntersectionRisk } from './drawing/drawingValidation';
import type { Position } from './drawing/drawingTypes';

// A separate input surface keeps map panning and field selection out of a stroke.
// The layer disappears with the tool, restoring the original map gestures.
export default function FreehandBoundary({ onFinish, onStatus }: {
  onFinish: (ring: L.LatLng[]) => void;
  onStatus?: (text: string | null) => void;
}) {
  const map = useMap();
  const surface = useRef<HTMLDivElement>(null);
  const finish = useRef(onFinish);
  const status = useRef(onStatus);
  finish.current = onFinish;
  status.current = onStatus;

  useEffect(() => {
    const el = surface.current;
    if (!el) return;
    let pointer: number | null = null;
    let points: L.Point[] = [];
    let preview: L.Polyline | undefined;
    L.DomEvent.disableClickPropagation(el);
    const reset = () => {
      const captured = pointer;
      pointer = null;
      if (captured !== null && el.hasPointerCapture(captured)) el.releasePointerCapture(captured);
      preview?.remove();
      preview = undefined;
      points = [];
    };
    const append = (e: PointerEvent) => {
      const point = map.mouseEventToContainerPoint(e);
      if (points.length && points[points.length - 1].distanceTo(point) < 3) return;
      points.push(point);
      preview?.addLatLng(map.containerPointToLatLng(point));
    };
    const down = (e: PointerEvent) => {
      if (pointer !== null || !e.isPrimary || e.button !== 0) return;
      e.preventDefault();
      el.setPointerCapture(e.pointerId);
      pointer = e.pointerId;
      preview = L.polyline([], { color: '#ffde00', weight: 3, interactive: false }).addTo(map);
      append(e);
    };
    const move = (e: PointerEvent) => { if (e.pointerId === pointer) append(e); };
    const up = (e: PointerEvent) => {
      if (e.pointerId !== pointer) return;
      append(e);
      const vertices = L.LineUtil.simplify(points, 2);
      const ring = vertices.map(point => map.containerPointToLatLng(point));
      reset();
      if (ring.length < 3) {
        status.current?.('ارسم حدّاً بثلاث زوايا على الأقل ثم ارفع لإغلاقه.');
        return;
      }
      // Validate the closing edge too, before a measurement or field is accepted.
      const closed: Position[] = ring.map(point => [point.lng, point.lat]);
      if (!ring[0].equals(ring[ring.length - 1], 0)) closed.push(closed[0]);
      if (ringSelfIntersectionRisk(closed)) {
        status.current?.('الحدّ يتقاطع مع نفسه — أعد الرسم دون تقاطع.');
        return;
      }
      const area = L.GeometryUtil.geodesicArea(ring);
      if (!Number.isFinite(area) || area <= 0) {
        status.current?.('ارسم حدّاً يحيط بمساحة ثم ارفع لإغلاقه.');
        return;
      }
      status.current?.(null);
      finish.current(ring);
    };
    const cancel = (e: PointerEvent) => { if (e.pointerId === pointer) reset(); };
    el.addEventListener('pointerdown', down);
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', up);
    el.addEventListener('pointercancel', cancel);
    el.addEventListener('lostpointercapture', cancel);
    return () => {
      reset();
      L.DomEvent.off(el);
      el.removeEventListener('pointerdown', down);
      el.removeEventListener('pointermove', move);
      el.removeEventListener('pointerup', up);
      el.removeEventListener('pointercancel', cancel);
      el.removeEventListener('lostpointercapture', cancel);
    };
  }, [map]);
  return <div ref={surface} data-testid="freehand-surface" style={{ position: 'absolute', inset: 0, zIndex: 610, touchAction: 'none', cursor: 'crosshair' }} />;
}
