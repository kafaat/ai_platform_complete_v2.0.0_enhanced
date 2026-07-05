// ═══════════════════════════════════════════════════════════════
// FarmMapOverview — خريطة المزرعة الشاملة (كلّ الحقول على خريطة واحدة)
// ═══════════════════════════════════════════════════════════════
// كانت الخرائط تعرض حقلاً واحداً فقط (FieldIndicatorMap/FieldMapCenter). هذه
// نظرة عامّة تعرض **كلّ حقول المزرعة معاً**: مضلّع لكلّ حقل ذي هندسة، وعلامة
// نقطيّة لما بلا هندسة (lat/lon)، مع ضبط الإطار تلقائيّاً على الجميع.
// النقر على حقل يضبط «الحقل النشط» المشترك (useSelectedField) فيتبع المستخدم عبر
// الشاشات. أساسٌ لاحقٌ لـclustering (لفّ العلامات بمجموعة تجميع فوق هذه الخريطة).
import { useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { MapContainer, TileLayer, Polygon, CircleMarker, Tooltip, useMap } from 'react-leaflet';
import L from 'leaflet';
import { Map as MapIcon, MapPin } from 'lucide-react';
import '../lib/leafletSetup'; // CSS + أيقونات Leaflet (side-effect حاسم للتصيير)
import { geomToPolygon, collectFieldBoundsPoints, fieldRepresentativePoint } from '../lib/geo';
import { useSelectedField } from '../hooks/useSelectedField';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';

// صور أقمار (Esri World Imagery) — الأنسب لرؤية الحقول الفعليّة على الأرض.
const BASEMAP_SAT =
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
const SELECTED_COLOR = '#22d3ee';
const FIELD_COLOR = '#34d399';
const YEMEN_CENTER: [number, number] = [15.0, 44.0]; // مركز افتراضيّ قبل أوّل تحميل

// يضبط إطار الخريطة على كلّ نقاط الحقول (رؤوس المضلّعات + النقاط الاحتياطيّة).
function FitAll({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (!points.length) return;
    const bounds = L.latLngBounds(points.map(([lat, lng]) => L.latLng(lat, lng)));
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 16 });
  }, [map, points]);
  return null;
}

function _cropLabel(crop: string): string {
  return crop && crop !== '—' ? crop : 'بلا محصول';
}

export default function FarmMapOverview() {
  const navigate = useNavigate();
  const { options: fields, isLoading, isError, refetch, fieldId, setFieldId } = useSelectedField();

  // كلّ النقاط لضبط الإطار + مركز افتراضيّ (متوسّطها) — منطق نقيّ مُذكَّر.
  const points = useMemo(() => collectFieldBoundsPoints(fields), [fields]);
  const center = useMemo<[number, number]>(() => {
    if (!points.length) return YEMEN_CENTER;
    const [sumLat, sumLng] = points.reduce(([a, b], [la, ln]) => [a + la, b + ln], [0, 0]);
    return [sumLat / points.length, sumLng / points.length];
  }, [points]);

  if (isLoading) return <LoadingState message="جارٍ تحميل خريطة المزرعة…" />;
  if (isError) return <ErrorState title="تعذّر تحميل الحقول" onRetry={() => refetch()} />;
  if (!fields.length)
    return <EmptyState title="لا حقول مُسجّلة بعد" hint="أضِف حقولاً لرؤيتها على خريطة المزرعة." />;

  const selected = fields.find((f) => f.id === fieldId);

  return (
    <div className="space-y-4 max-w-6xl mx-auto" dir="rtl">
      <header className="flex items-center gap-2">
        <MapIcon className="w-5 h-5 text-emerald-400" aria-hidden="true" />
        <h1 className="text-lg font-bold text-slate-100">خريطة المزرعة الشاملة</h1>
        <span className="text-xs text-slate-400">{fields.length} حقل</span>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4">
        {/* الخريطة: كلّ الحقول معاً */}
        <div style={{ height: '70vh', borderRadius: 12, overflow: 'hidden' }}>
          <MapContainer center={center} zoom={11} style={{ height: '100%', width: '100%' }}>
            <TileLayer url={BASEMAP_SAT} attribution="Tiles &copy; Esri — World Imagery" />
            <FitAll points={points} />
            {fields.map((f) => {
              const poly = geomToPolygon(f.geometry);
              const isSel = f.id === fieldId;
              const label = `${f.name}${f.crop && f.crop !== '—' ? ` · ${f.crop}` : ''}`;
              if (poly && poly.length >= 3) {
                return (
                  <Polygon
                    key={f.id}
                    positions={poly}
                    pathOptions={{
                      color: isSel ? SELECTED_COLOR : FIELD_COLOR,
                      weight: isSel ? 3 : 1.5,
                      fillOpacity: isSel ? 0.35 : 0.15,
                    }}
                    eventHandlers={{ click: () => setFieldId(f.id, { source: 'user', name: f.name }) }}
                  >
                    <Tooltip>{label}</Tooltip>
                  </Polygon>
                );
              }
              const pt = fieldRepresentativePoint(f);
              if (!pt) return null;
              return (
                <CircleMarker
                  key={f.id}
                  center={pt}
                  radius={isSel ? 9 : 6}
                  pathOptions={{
                    color: isSel ? SELECTED_COLOR : FIELD_COLOR,
                    fillColor: isSel ? SELECTED_COLOR : FIELD_COLOR,
                    fillOpacity: 0.8,
                    weight: isSel ? 3 : 1.5,
                  }}
                  eventHandlers={{ click: () => setFieldId(f.id, { source: 'user', name: f.name }) }}
                >
                  <Tooltip>{label}</Tooltip>
                </CircleMarker>
              );
            })}
          </MapContainer>
        </div>

        {/* لوحة جانبيّة: قائمة الحقول (نقرة تختار الحقل النشط المشترك) */}
        <aside className="space-y-2">
          <div className="text-xs text-slate-400 mb-1">
            الحقول — انقر لاختياره (يتبعك عبر الشاشات)
          </div>
          <div className="space-y-1 max-h-[64vh] overflow-auto">
            {fields.map((f) => {
              const isSel = f.id === fieldId;
              const noGeom = !geomToPolygon(f.geometry);
              return (
                <button
                  key={f.id}
                  onClick={() => setFieldId(f.id, { source: 'user', name: f.name })}
                  className="w-full text-right rounded-lg px-3 py-2 border transition-colors"
                  style={{
                    background: isSel ? '#0e7490' : '#1e293b',
                    borderColor: isSel ? '#22d3ee' : '#334155',
                    color: isSel ? '#e0f2fe' : '#cbd5e1',
                  }}
                >
                  <div className="flex items-center gap-2">
                    <MapPin className="w-3.5 h-3.5 flex-shrink-0" aria-hidden="true" />
                    <span className="text-sm font-medium truncate">{f.name}</span>
                  </div>
                  <div className="text-[11px] opacity-70 mt-0.5">
                    {_cropLabel(f.crop)}
                    {f.area ? ` · ${f.area} هـ` : ''}
                    {noGeom ? ' · بلا حدود' : ''}
                  </div>
                </button>
              );
            })}
          </div>
          {selected && (
            <div className="rounded-lg p-3 border border-cyan-800 bg-cyan-950/40 text-sm text-cyan-100 space-y-2">
              <div className="font-semibold">{selected.name}</div>
              <div className="grid grid-cols-2 gap-2 text-[11px] text-cyan-200/90">
                <div>المحصول: {selected.crop || '—'}</div>
                <div>المساحة: {selected.area ? `${selected.area} هـ` : '—'}</div>
                <div className="col-span-2">المعرّف: {selected.id}</div>
              </div>
              <div className="text-[11px] text-cyan-300/80">
                النقر على الحقل يثبّت الاختيار المشترك لكل الشاشات. استخدم الأزرار للانتقال بسياق الحقل نفسه.
              </div>
              <div className="grid grid-cols-2 gap-2 pt-1">
                <button onClick={() => navigate('/fields/workspace')} className="rounded-lg border border-cyan-700 px-2 py-1 text-[11px] hover:bg-cyan-900/40">مساحة العمل</button>
                <button onClick={() => navigate('/health/satellite')} className="rounded-lg border border-cyan-700 px-2 py-1 text-[11px] hover:bg-cyan-900/40">الأقمار</button>
                <button onClick={() => navigate('/health/lab-sampling')} className="rounded-lg border border-cyan-700 px-2 py-1 text-[11px] hover:bg-cyan-900/40">العينات</button>
                <button onClick={() => navigate('/irrigation/plan')} className="rounded-lg border border-cyan-700 px-2 py-1 text-[11px] hover:bg-cyan-900/40">خطة الري</button>
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
