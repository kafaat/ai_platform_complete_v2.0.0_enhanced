// ═══════════════════════════════════════════════════════════════
// FieldWorkspaceMapCard — كرت «مساحة عمل الحقل» (مرجعيّ)
// ───────────────────────────────────────────────────────────────
// يستهلك field_id حقيقيّاً ويعرض على البنية القائمة (react-leaflet، بلا SDK جديد):
//   • حدود الحقل (GeoJSON) من GET /api/v1/fields/{id} (fetchFieldDetail.geometry)
//   • طبقة NDVI الحقيقيّة من خدمة الراستر (TileLayer XYZ) — قابلة للتبديل، تُربَط
//     فقط عند التفعيل، ولا تُعرَض إن لم تُعلن مساحة العمل وجود طبقة ndvi.
//   • شريط الخطّ الزمنيّ من workspace.timeline (أحداث مسجّلة فقط — لا تاريخ مخترَع)
//   • بطاقة «ملخّص القرار الموحّد» من workspace (طبقات متاحة + تضاريس + خطّ زمنيّ)
//
// المصدر الأساسيّ: GET /api/v1/fields/{id}/workspace (assemble_workspace) — عرض
// صرف (display_only) لا يفرض قراراً. صدق: حالات loading/empty/error صادقة، ولا
// يُعرَض رقم/طبقة لم يُرجِعها API (قاعدة عدم الاختلاق).
// ═══════════════════════════════════════════════════════════════
import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { MapContainer, TileLayer, Polygon, useMap } from 'react-leaflet';
import L from 'leaflet';
import { Map as MapIcon, Layers, Clock, FileText, Leaf } from 'lucide-react';
import '../lib/leafletSetup'; // CSS + أيقونات Leaflet (side-effect حاسم للتصيير)
import { geomToPolygon } from '../lib/geo';
import { fieldIndicatorTileUrl, fetchFieldImageryAvailableDates, type FieldImageryDateOption, type FieldWorkspace, type WorkspaceLayer } from '../services/api';
import { useFieldWorkspace, useFieldDetail } from '../hooks/useApi';
import { useSelectedField } from '../hooks/useSelectedField';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';

// صور أقمار (Esri World Imagery) — الأساس لرؤية الحقل على الأرض (نفس FarmMapOverview).
const BASEMAP_SAT =
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
const FIELD_COLOR = '#34d399';
const YEMEN_CENTER: [number, number] = [15.0, 44.0];

// مركز افتراضيّ للخريطة من مضلّع الحدود (متوسّط الرؤوس) — قبل ضبط الإطار.
function polygonCenter(poly: [number, number][] | undefined): [number, number] {
  if (!poly || !poly.length) return YEMEN_CENTER;
  const [sumLat, sumLng] = poly.reduce(([a, b], [la, ln]) => [a + la, b + ln], [0, 0]);
  return [sumLat / poly.length, sumLng / poly.length];
}

// تسمية عربيّة لحالة الطبقة (متاحة/عند الطلب/غير متوفّرة) — صدق التوفّر.
function layerStatusLabel(layer: WorkspaceLayer): string {
  if (layer.available) return 'متاحة';
  if (layer.status === 'on_demand') return 'عند الطلب';
  return 'غير متوفّرة';
}

function layerStatusColor(layer: WorkspaceLayer): string {
  if (layer.available) return '#34d399';
  if (layer.status === 'on_demand') return '#fbbf24';
  return '#64748b';
}

// ── بطاقة ملخّص القرار الموحّد (من مساحة العمل — عرض صرف لا قرار مفروض) ──
function DecisionSummaryCard({ ws }: { ws: FieldWorkspace }) {
  const availableLayers = ws.layers.filter((l) => l.available);
  return (
    <section
      className="rounded-xl p-4 border border-emerald-900 bg-emerald-950/30"
      dir="rtl"
      aria-label="ملخّص القرار الموحّد"
    >
      <div className="flex items-center gap-2 mb-3">
        <FileText className="w-4 h-4 text-emerald-400" aria-hidden="true" />
        <h2 className="text-sm font-bold text-slate-100">ملخّص القرار الموحّد</h2>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <dt className="text-slate-400">المحصول</dt>
        <dd className="text-slate-100">{ws.field.crop || 'بلا محصول'}</dd>
        <dt className="text-slate-400">المساحة</dt>
        <dd className="text-slate-100">
          {ws.field.area_ha != null ? `${ws.field.area_ha} هـ` : '—'}
        </dd>
        <dt className="text-slate-400">نوع التربة</dt>
        <dd className="text-slate-100">{ws.field.soil_type || '—'}</dd>
        <dt className="text-slate-400">طبقات متاحة</dt>
        <dd className="text-slate-100">{ws.available_layer_count}</dd>
        <dt className="text-slate-400">أحداث مسجّلة</dt>
        <dd className="text-slate-100">{ws.timeline_total}</dd>
      </dl>

      {availableLayers.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {availableLayers.map((l) => (
            <span
              key={l.key}
              className="text-[11px] px-2 py-0.5 rounded-full border border-emerald-800 text-emerald-200 bg-emerald-900/40"
            >
              {l.label_ar}
            </span>
          ))}
        </div>
      )}

      <p className="text-[11px] text-slate-500 mt-3 leading-relaxed">{ws.honesty_note_ar}</p>
    </section>
  );
}

// ── كتالوج الطبقات (توفّر صادق لكلّ طبقة) ──
function LayersPanel({ ws }: { ws: FieldWorkspace }) {
  return (
    <section className="rounded-xl p-4 border border-slate-800 bg-slate-900/40" dir="rtl">
      <div className="flex items-center gap-2 mb-3">
        <Layers className="w-4 h-4 text-cyan-400" aria-hidden="true" />
        <h2 className="text-sm font-bold text-slate-100">الطبقات</h2>
      </div>
      <ul className="space-y-1.5">
        {ws.layers.map((l) => (
          <li key={l.key} className="flex items-center gap-2 text-sm">
            <span
              className="w-2 h-2 rounded-full flex-shrink-0"
              style={{ background: layerStatusColor(l) }}
              aria-hidden="true"
            />
            <span className="text-slate-200 flex-1">{l.label_ar}</span>
            <span className="text-[11px] text-slate-400">{layerStatusLabel(l)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

// ── شريط الخطّ الزمنيّ (من أحداث مسجّلة فقط) ──
function TimelineStrip({ ws }: { ws: FieldWorkspace }) {
  return (
    <section className="rounded-xl p-4 border border-slate-800 bg-slate-900/40" dir="rtl">
      <div className="flex items-center gap-2 mb-3">
        <Clock className="w-4 h-4 text-amber-400" aria-hidden="true" />
        <h2 className="text-sm font-bold text-slate-100">الخطّ الزمنيّ</h2>
        <span className="text-xs text-slate-500">{ws.timeline_total} حدث</span>
      </div>
      {ws.timeline.length === 0 ? (
        <EmptyState
          title="لا أحداث مسجّلة"
          hint="لا تتوفّر بيانات خطّ زمنيّ لهذا الحقل بعد."
        />
      ) : (
        <ol className="space-y-2 max-h-56 overflow-auto">
          {ws.timeline.map((c, i) => (
            <li
              key={`${c.event_type}-${c.occurred_at}-${i}`}
              className="flex items-start gap-3 text-sm"
            >
              <span className="text-amber-400 mt-1" aria-hidden="true">
                ◆
              </span>
              <div className="flex-1 min-w-0">
                <div className="text-slate-200 truncate">{c.op_ar}</div>
                <div className="text-[11px] text-slate-500">
                  {c.occurred_at ? c.occurred_at.slice(0, 10) : '—'}
                  {c.issue_tags.length > 0 ? ` · ${c.issue_tags.join('، ')}` : ''}
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

export interface FieldWorkspaceMapCardProps {
  /** field_id حقيقيّ. إن غاب، يُستعمل «الحقل النشط» المشترك (منتقي حقول). */
  fieldId?: string;
  /** هل تُعرَض شارة منتقي الحقل (عند الاعتماد على الحقل النشط المشترك)؟ */
  showPicker?: boolean;
}

export default function FieldWorkspaceMapCard({
  fieldId: fieldIdProp,
  showPicker = true,
}: FieldWorkspaceMapCardProps) {
  const location = useLocation();
  const routeFieldId = ((location.state as { fieldId?: string } | null)?.fieldId) ?? null;
  // الحقل النشط المشترك حين لا يُمرَّر field_id صراحةً (يتبع المستخدم عبر الشاشات).
  const navigate = useNavigate();
  const selected = useSelectedField({ routeFieldId });
  const fieldId = fieldIdProp ?? selected.fieldId;

  const [ndviOn, setNdviOn] = useState(false);
  const [imageryDates, setImageryDates] = useState<FieldImageryDateOption[]>([]);
  const [selectedImageryDate, setSelectedImageryDate] = useState<string>('latest');

  const workspace = useFieldWorkspace(fieldId);
  const detail = useFieldDetail(fieldId);

  // اجلب تواريخ COG/CDSE المتاحة لمساحة العمل أيضاً، حتى لا تبقى طبقة NDVI
  // عالقة على latest حين تتوفر تواريخ صريحة. الفشل لا يخترع تاريخاً؛ يبقي latest.
  useEffect(() => {
    let cancelled = false;
    if (!fieldId) {
      setImageryDates([]);
      setSelectedImageryDate('latest');
      return;
    }
    // v11-F8: البطاقة تعرض NDVI؛ نقصر التواريخ على COG الخاصّ به (لا خلط مؤشّرات).
    fetchFieldImageryAvailableDates(fieldId, 'ndvi')
      .then((items) => {
        if (cancelled) return;
        const sorted = [...items]
          .filter((d) => d.date)
          .sort((a, b) => b.date.localeCompare(a.date));
        setImageryDates(sorted);
        setSelectedImageryDate((prev) => {
          if (prev !== 'latest' && sorted.some((d) => d.date === prev)) return prev;
          return sorted.find((d) => d.has_cog)?.date ?? sorted[0]?.date ?? 'latest';
        });
      })
      .catch(() => {
        if (!cancelled) {
          setImageryDates([]);
          setSelectedImageryDate('latest');
        }
      });
    return () => { cancelled = true; };
  }, [fieldId]);

  // مضلّع الحدود من هندسة الحقل (GeoJSON) — منطق نقيّ مُذكَّر.
  const polygon = useMemo(() => geomToPolygon(detail.data?.geometry), [detail.data?.geometry]);
  const center = useMemo(() => polygonCenter(polygon), [polygon]);

  // طبقة NDVI تُعرَض فقط إن أعلنتها مساحة العمل (قاعدة عدم الاختلاق).
  const ndviLayer = workspace.data?.layers.find((l) => l.key === 'ndvi');
  const ndviTileUrl = fieldId ? fieldIndicatorTileUrl(fieldId, 'ndvi', selectedImageryDate) : '';

  // لا حقل نشط أصلاً (لا حقول مُسجّلة / لم يُمرَّر field_id).
  if (!fieldId) {
    if (selected.isLoading) return <LoadingState message="جارٍ تحميل الحقول…" />;
    if (selected.isError)
      return <ErrorState title="تعذّر تحميل الحقول" onRetry={() => selected.refetch()} />;
    return (
      <EmptyState
        title="لا حقل مُختار"
        hint="أضِف حقلاً أو اختَر حقلاً لعرض مساحة العمل."
      />
    );
  }

  // المصدر الأساسيّ: مساحة العمل. تحميلها يحكم الهيكل العامّ.
  if (workspace.isLoading) return <LoadingState message="جارٍ تحميل مساحة عمل الحقل…" />;
  if (workspace.isError)
    return (
      <ErrorState
        title="تعذّر تحميل مساحة عمل الحقل"
        detail="قد تكون الخدمة غير متوفّرة (503) أو الحقل غير موجود."
        onRetry={() => workspace.refetch()}
      />
    );
  if (!workspace.data)
    return (
      <EmptyState title="لا تتوفّر بيانات" hint="لم تُرجِع الخدمة مساحة عمل لهذا الحقل." />
    );

  const ws = workspace.data;
  const ndviAvailable = !!ndviLayer; // الطبقة معلنة في الكتالوج
  const hasBoundary = !!polygon && polygon.length >= 3;

  return (
    <div className="space-y-4 max-w-6xl mx-auto" dir="rtl">
      <header className="flex items-center gap-2 flex-wrap">
        <MapIcon className="w-5 h-5 text-emerald-400" aria-hidden="true" />
        <h1 className="text-lg font-bold text-slate-100">مساحة عمل الحقل</h1>
        <span className="text-sm text-slate-400">{ws.field.name_ar || fieldId}</span>
        {showPicker && !fieldIdProp && selected.options.length > 1 && (
          <select
            aria-label="اختيار الحقل النشط"
            className="mr-auto rounded-lg bg-slate-800 border border-slate-700 text-sm text-slate-200 px-2 py-1"
            value={fieldId}
            onChange={(e) => selected.setFieldId(e.target.value)}
          >
            {selected.options.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
        )}
      </header>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <button onClick={() => navigate('/health/satellite', { state: { fieldId } })} className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 hover:border-emerald-500">الأقمار والمؤشرات</button>
        <button onClick={() => navigate('/health/lab-sampling', { state: { fieldId } })} className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 hover:border-emerald-500">العينات والمختبر</button>
        <button onClick={() => navigate('/health/prescriptions', { state: { fieldId } })} className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 hover:border-emerald-500">وصفات ومناطق</button>
        <button onClick={() => navigate('/irrigation/plan', { state: { fieldId } })} className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 hover:border-emerald-500">خطة الري</button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-4">
        {/* الخريطة: حدود الحقل + طبقة NDVI القابلة للتبديل */}
        <div className="space-y-2">
          <div
            style={{ height: '60vh', borderRadius: 12, overflow: 'hidden' }}
            className="border border-slate-800"
          >
            <MapContainer
              center={center}
              zoom={hasBoundary ? 15 : 11}
              style={{ height: '100%', width: '100%' }}
              scrollWheelZoom
              key={fieldId /* إعادة تركيب الخريطة عند تبدّل الحقل */}
            >
              <TileLayer url={BASEMAP_SAT} attribution="Tiles &copy; Esri — World Imagery" />

              {/* طبقة NDVI الحقيقيّة من خدمة الراستر — تُربَط فقط عند التفعيل
                  وإعلان توفّرها. لا تلوين مفبرك: بلا COG صافٍ تظهر بلاطات فارغة. */}
              {ndviOn && ndviAvailable && ndviTileUrl && (
                <TileLayer
                  url={ndviTileUrl}
                  opacity={0.75}
                  attribution="NDVI &copy; SAHOOL Raster (Sentinel-2)"
                />
              )}

              {/* حدود الحقل (GeoJSON Polygon) */}
              {hasBoundary && (
                <Polygon
                  positions={polygon}
                  pathOptions={{ color: FIELD_COLOR, weight: 2, fillOpacity: 0.1 }}
                />
              )}

              <FitBoundsOnce polygon={polygon} />
            </MapContainer>
          </div>

          {/* تبديل طبقة NDVI — صدق: تُعطَّل ويُعلَن السبب إن لم تتوفّر الطبقة */}
          <div className="flex items-center gap-2 text-sm">
            <button
              type="button"
              onClick={() => setNdviOn((v) => !v)}
              disabled={!ndviAvailable}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                borderColor: ndviOn && ndviAvailable ? '#34d399' : '#334155',
                color: ndviOn && ndviAvailable ? '#34d399' : '#cbd5e1',
                background: ndviOn && ndviAvailable ? '#064e3b55' : 'transparent',
              }}
              aria-pressed={ndviOn && ndviAvailable}
            >
              <Leaf className="w-4 h-4" aria-hidden="true" />
              طبقة NDVI
            </button>
            {imageryDates.length > 0 && (
              <select
                aria-label="اختيار تاريخ صورة Sentinel لمساحة العمل"
                className="rounded-lg bg-slate-800 border border-slate-700 text-xs text-slate-200 px-2 py-1"
                value={selectedImageryDate}
                onChange={(e) => setSelectedImageryDate(e.target.value)}
              >
                {imageryDates.map((d) => (
                  <option key={d.date} value={d.date}>
                    {d.date}{d.cloud_pct != null ? ` · غيوم ${Math.round(d.cloud_pct)}%` : ''}
                  </option>
                ))}
              </select>
            )}
            <span className="text-[11px] text-slate-500">
              {ndviAvailable
                ? ndviLayer?.note_ar
                : 'طبقة NDVI غير معلنة من الخادم لهذا الحقل — لا تُعرَض.'}
            </span>
          </div>

          {!hasBoundary && (
            <EmptyState
              title="لا حدود مرسومة للحقل"
              hint="لم تُرجِع الخدمة هندسة (geometry) لهذا الحقل — لا مضلّع يُرسَم."
            />
          )}
        </div>

        {/* اللوحة الجانبيّة: ملخّص القرار + الطبقات + الخطّ الزمنيّ */}
        <aside className="space-y-4">
          <DecisionSummaryCard ws={ws} />
          <LayersPanel ws={ws} />
          <TimelineStrip ws={ws} />
        </aside>
      </div>
    </div>
  );
}

// يضبط إطار الخريطة على مضلّع الحدود عند توفّره (نفس نمط FitAll في FarmMapOverview).
// مكوّن داخل MapContainer فقط ⇒ useMap آمن دائماً (لا استدعاء شرطيّ للـhook).
function FitBoundsOnce({ polygon }: { polygon?: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (!polygon || polygon.length < 3) return;
    const bounds = L.latLngBounds(polygon.map(([lat, lng]) => L.latLng(lat, lng)));
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [24, 24], maxZoom: 17 });
  }, [map, polygon]);
  return null;
}
