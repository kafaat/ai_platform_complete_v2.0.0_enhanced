import { useEffect, useRef } from 'react';
import { useMap } from 'react-leaflet';
import L from 'leaflet';

// A separate input surface keeps map panning and field selection out of a stroke.
// The layer disappears with the tool, restoring the original map gestures.
export default function FreehandBoundary({ onFinish }: { onFinish: (ring: L.LatLng[]) => void }) {
  const map = useMap();
  const surface = useRef<HTMLDivElement>(null);
  const finish = useRef(onFinish);
  finish.current = onFinish;

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
      if (ring.length >= 3 && L.GeometryUtil.geodesicArea(ring) > 0) finish.current(ring);
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
