import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { FeatureGroup, useMap } from 'react-leaflet';
import L from 'leaflet';
import { X } from 'lucide-react';
import DrawControl from './DrawControl';
import InteractiveDrawLayer from './InteractiveDrawLayer';
import { circleToPolygon } from './circleBoundary';
import { areaSqMeters, lengthMeters, formatArea, formatLength } from '../../lib/geo';

const modes = {
  polygon: 'مضلّع', line: 'خطّ', circle: 'دائرة', rectangle: 'مستطيل', freehand: 'رسم حر',
} as const;
type Mode = keyof typeof modes;
type Props = {
  dock: HTMLElement | null;
  area?: (feature: GeoJSON.Feature) => number;
};

export default function MeasureTools({ dock, area = areaSqMeters }: Props) {
  const map = useMap();
  const [group, setGroup] = useState<L.FeatureGroup | null>(null);
  const [mode, setMode] = useState<Mode | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [showHelp, setShowHelp] = useState(true);
  const [totals, setTotals] = useState({ area: 0, length: 0 });
  function refresh() {
    let areaM2 = 0, lengthM = 0;
    group?.eachLayer(layer => {
      if (layer instanceof L.Polygon) areaM2 += area(layer.toGeoJSON());
      else if (layer instanceof L.Polyline) lengthM += lengthMeters(layer.toGeoJSON());
    });
    setTotals({ area: areaM2, length: lengthM });
  }
  function finish(ring: L.LatLng[]) {
    group?.addLayer(L.polygon(ring, { color: '#367c2b' }));
    refresh();
    setMode(null);
  }
  useEffect(() => {
    if (mode !== 'line' && mode !== 'polygon') return;
    const tool = mode === 'line'
      ? new L.Draw.Polyline(map, { shapeOptions: { color: '#ffde00' } })
      : new L.Draw.Polygon(map, { allowIntersection: false, showArea: false, shapeOptions: { color: '#367c2b' } });
    const stop = () => setMode(null);
    tool.enable();
    map.on(L.Draw.Event.DRAWSTOP, stop);
    return () => { map.off(L.Draw.Event.DRAWSTOP, stop); tool.disable(); };
  }, [map, mode]);

  return <>
    <FeatureGroup ref={setGroup}>
      <DrawControl position="topright"
        draw={{ polyline: false, polygon: false, circle: false, rectangle: false, marker: false, circlemarker: false }}
        edit={{ edit: mode ? false : {}, remove: mode ? false : {} }}
        onCreated={refresh} onEdited={refresh} onDeleted={refresh} />
    </FeatureGroup>
    <InteractiveDrawLayer tool={mode === 'line' || mode === 'polygon' ? null : mode}
      onCircle={(center, radius) => finish(circleToPolygon(center, radius))}
      onRectangle={finish} onFreehand={finish} onStatus={setHint} />
    {dock && createPortal(<section className="measure-dock" aria-label="أدوات القياس" dir="rtl">
      <div className="map-tool-row">
        {(Object.keys(modes) as Mode[]).map(key =>
          <button key={key} type="button" className="map-tool" aria-pressed={key === mode}
            onClick={() => { setMode(mode === key ? null : key); setShowHelp(true); }}>{modes[key]}</button>)}
        {(totals.area > 0 || totals.length > 0) && <button type="button" className="map-tool"
          onClick={() => { group?.clearLayers(); refresh(); }}>مسح القياسات</button>}
      </div>
      {showHelp && <div className="map-hint" role="status">
        {hint || (mode === 'line' ? 'انقر نقاط المسار ثم انقر آخر نقطة لإنهائه.' :
          mode === 'polygon' ? 'انقر زوايا الحدّ ثم انقر نقطة البداية لإغلاقه.' : 'اختر شكلاً للقياس على الخريطة.')}
        <button type="button" aria-label="إغلاق تعليمات الرسم" onClick={() => setShowHelp(false)}><X size={18} /></button>
      </div>}
      <div aria-live="polite">
        {totals.area > 0 && <output data-testid="measure-area">{formatArea(totals.area)}</output>}
        {totals.length > 0 && <output data-testid="measure-length">{formatLength(totals.length)}</output>}
      </div>
    </section>, dock)}
  </>;
}
