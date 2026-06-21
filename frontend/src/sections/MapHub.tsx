// ═══════════════════════════════════════════════════════════════
// SAHOOL — مركز الخرائط الموحّد (Map Hub) · طراز FieldView
// ───────────────────────────────────────────────────────────────
// السطح الموحّد «الحقول والخريطة»: يصهر الأسطح المجزّأة (FarmMapOverview /
// FieldMapCenter / FieldWorkspaceMapCard / SpatialIndicatorsPage / Satellite)
// في كابينة واحدة طراز Climate-FieldView:
//   • لوحة يسرى: قائمة حقول باحثة (Combobox + قائمة) — اختيار مشترك (useSelectedField).
//   • خريطة Leaflet مركزيّة (HubMap): كلّ الحقول، إبراز المختار، بلاطات مؤشّر.
//   • مُنتقي خريطة الأساس (CARTO/Esri من layerRegistry).
//   • مبدّلات الطبقات (NDVI/NDMI/الملوحة + المرتفعات/التربة كطبقات وصفيّة) عبر
//     LayerSwitcher + ColormapLegend، وشريط شفّافيّة.
//   • مقارنة جنباً لجنب (SideBySide) لطبقتين حقيقيّتين لنفس الحقل.
//   • رسم/قياس (turf) + دبابيس استكشاف (حالة محلّيّة — لا نقطة قراءة scouting خلفيّة).
//   • درج تفاصيل الحقل المنزلق (تحرير + ملخّص الموسم) — FieldDetailDrawer.
//   • إنشاء/استيراد حقل داخل المركز (AddFieldWithMap).
//   • مبدّل وضع 2D / تضاريس(3D) — العرض ثلاثيّ الأبعاد مقسوم بالكود (React.lazy).
//
// القيود: عربيّ-RTL، framer-motion للانتقالات، DS atoms/StateViews/ToastContainer،
// صدق البيانات (لا قيم ملفّقة؛ الغائب «—»). البوّابات (RBAC/العلم) تبقى في App.
// ═══════════════════════════════════════════════════════════════
import { Suspense, lazy, useCallback, useMemo, useState } from 'react';
import {
  Layers, MapPin, Plus, Columns2, Square, Ruler, Crosshair, Box, Mountain,
  Search as SearchIcon, Trash2,
} from 'lucide-react';
import { useSelectedField } from '../hooks/useSelectedField';
import { useFieldDetail } from '../hooks/useApi';
import { kongApi, asApiError } from '../services/api';
import { toastStore } from '../services/websocket';
import { useAuthStore } from '../hooks/useAuth';
import { canMutate } from '../lib/permissions';
import { layersOfKind } from '../lib/layerRegistry';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';
import AddFieldWithMap from '../components/AddFieldWithMap';
import {
  T, RADIUS, Card, Pill, Badge, SectionLabel,
  LayerSwitcher, ColormapLegend, SideBySide, type CmapId,
} from '../components/ds';
import HubMap, { type ScoutPin } from '../components/maphub/HubMap';
import FieldDetailDrawer from '../components/maphub/FieldDetailDrawer';

// العرض ثلاثيّ الأبعاد مقسوم بالكود — لا يُحمَّل إلا عند تفعيل وضع التضاريس،
// فلا يُثقِل الحزمة الأساسيّة (يحوي مستقبلاً maplibre-gl الثقيل).
const TerrainView3D = lazy(() => import('../components/maphub/TerrainView3D'));

// ── الطبقات القابلة للعرض كبلاطات مؤشّر (raster) — من السجلّ ──
// نُبقي فقط ما تنتجه خدمة الراستر فعلاً (ndvi/ndmi/salinity) مع لوحة DS موجودة.
const RASTER_INDEX_IDS = new Set(['ndvi', 'ndmi', 'salinity']);
const INDICATOR_LAYERS = layersOfKind('index')
  .filter((l) => RASTER_INDEX_IDS.has(l.id) && l.colormap != null)
  .map((l) => ({ id: l.id, label: l.labelAr, cmap: l.colormap as CmapId }));

// خرائط الأساس من السجلّ (kind:'basemap').
const BASEMAPS = layersOfKind('basemap').map((b) => ({ id: b.id, label: b.labelAr }));

// تسمية مختصرة + حدّا المفتاح للطبقة (عرض ColormapLegend).
const LAYER_LEGEND: Record<string, { short: string; low: string; high: string }> = {
  ndvi: { short: 'NDVI', low: 'إجهاد', high: 'كثيف' },
  ndmi: { short: 'NDMI', low: 'جافّ', high: 'رطب' },
  salinity: { short: 'الملوحة', low: 'منخفضة', high: 'مرتفعة' },
};

const PIN_CATEGORIES = ['آفة', 'مرض', 'نقص تغذية', 'إجهاد مائيّ', 'عشب ضارّ', 'أخرى'];

export default function MapHub() {
  const { options: fields, isLoading, isError, refetch, fieldId, setFieldId } = useSelectedField();
  const { user } = useAuthStore();
  const mutateAllowed = canMutate(user?.role);

  const detailQ = useFieldDetail(fieldId || undefined);

  // ── حالة العرض ──────────────────────────────────────────────
  const [mode, setMode] = useState<'2d' | '3d'>('2d');
  const [basemapId, setBasemapId] = useState<string>(BASEMAPS[0]?.id ?? 'satellite');
  const [activeIndicator, setActiveIndicator] = useState<string | null>(null); // null = لا مؤشّر
  const [opacity, setOpacity] = useState(0.75);
  const [compare, setCompare] = useState(false);
  const [leftLayer, setLeftLayer] = useState<string>(INDICATOR_LAYERS[0]?.id ?? 'ndvi');
  const [rightLayer, setRightLayer] = useState<string>(INDICATOR_LAYERS[1]?.id ?? 'ndmi');
  const [drawTools, setDrawTools] = useState(false);
  const [pinMode, setPinMode] = useState(false);
  const [pins, setPins] = useState<ScoutPin[]>([]);
  const [pinCategory, setPinCategory] = useState(PIN_CATEGORIES[0]);
  const [detailOpen, setDetailOpen] = useState(false);
  const [showAddField, setShowAddField] = useState(false);
  const [search, setSearch] = useState('');

  const selected = fields.find((f) => f.id === fieldId);

  // قائمة الحقول المُرشَّحة بالبحث (اسم/محصول) — لوحة الحقول الباحثة.
  const visibleFields = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return fields;
    return fields.filter((f) =>
      f.name.toLowerCase().includes(q) || (f.crop ?? '').toLowerCase().includes(q));
  }, [fields, search]);

  // ── دبابيس الاستكشاف (حالة محلّيّة) ──────────────────────────
  // TODO(maphub-scouting): الخلفيّة تعرض إنشاء استكشاف (POST) فقط بلا نقطة قراءة
  // (GET) تُرجع قائمة مُخزَّنة — موثّق في hooks/useScouting.ts. لذا الدبابيس حالة
  // محلّيّة (جلسة) لا تُحفَظ بعد. اربطها بـPOST /scouting حين تتوفّر قراءة مقابلة.
  const handleAddPin = useCallback((lat: number, lng: number) => {
    setPins((prev) => [
      ...prev,
      { id: `pin_${Date.now()}_${prev.length}`, lat, lng, note: '', category: pinCategory },
    ]);
  }, [pinCategory]);

  const handleClearPins = useCallback(() => setPins([]), []);

  // ── إنشاء/استيراد حقل (نفس مسار FieldManagementPage الحقيقيّ) ──
  const handleSaveField = useCallback(async (data: {
    name: string; manager: string; crop: string; soil_type: string;
    field_code?: string; water_source?: string; country?: string; region?: string;
    area_ha: number; geometry: { type: string; coordinates: number[][][] };
  }) => {
    try {
      await kongApi.post('/api/v1/fields', {
        name: data.name, crop: data.crop, soil_type: data.soil_type, manager: data.manager,
        field_code: data.field_code ?? null, water_source: data.water_source ?? null,
        country: data.country ?? null, region: data.region ?? null, geometry: data.geometry,
      });
      setShowAddField(false);
      toastStore.add('success', '✅ تم إضافة الحقل', data.name);
      refetch();
    } catch (e) {
      const msg = asApiError(e).message || 'تعذّر حفظ الحقل — تحقّق من القاعدة/الصلاحيّة أو صحّة الحدود.';
      toastStore.add('error', '⚠️ فشل حفظ الحقل', msg);
      throw new Error(msg);
    }
  }, [refetch]);

  const handleImportField = useCallback(async (payload: unknown) => {
    try {
      await kongApi.post('/api/v1/fields/import', payload);
      setShowAddField(false);
      toastStore.add('success', '✅ تم استيراد الحقل', '');
      refetch();
    } catch (e) {
      const msg = asApiError(e).message || 'تعذّر استيراد الحقل — تحقّق من صحّة الملفّ والحدود والصلاحيّة.';
      throw new Error(msg);
    }
  }, [refetch]);

  if (isLoading) return <LoadingState message="جارٍ تحميل مركز الخرائط…" />;
  if (isError) return <ErrorState title="تعذّر تحميل الحقول" onRetry={() => refetch()} />;

  const indicatorActive = mode === '2d' && !compare ? activeIndicator : null;

  return (
    <div className="max-w-7xl mx-auto" dir="rtl">
      {/* ── الترويسة + أدوات الوضع ── */}
      <header className="flex items-center gap-2 mb-3 flex-wrap">
        <Layers className="w-5 h-5 text-emerald-400" aria-hidden="true" />
        <h1 className="text-lg font-bold" style={{ color: '#e2e8f0' }}>مركز الخرائط الموحّد</h1>
        <span className="text-xs" style={{ color: T.faint }}>{fields.length} حقل</span>
        <div className="flex items-center gap-1.5" style={{ marginInlineStart: 'auto' }}>
          {/* مبدّل وضع 2D / تضاريس(3D) */}
          <div className="flex rounded-lg overflow-hidden" style={{ border: `1px solid ${T.line}` }}>
            <button
              type="button" onClick={() => setMode('2d')}
              className="flex items-center gap-1 px-3 py-1.5 text-xs font-semibold"
              style={{ background: mode === '2d' ? T.green : 'transparent', color: mode === '2d' ? '#fff' : T.muted }}
            >
              <Box className="w-3.5 h-3.5" /> 2D
            </button>
            <button
              type="button" onClick={() => setMode('3d')}
              className="flex items-center gap-1 px-3 py-1.5 text-xs font-semibold"
              style={{ background: mode === '3d' ? T.green : 'transparent', color: mode === '3d' ? '#fff' : T.muted }}
            >
              <Mountain className="w-3.5 h-3.5" /> تضاريس(3D)
            </button>
          </div>
          {mutateAllowed && (
            <button
              type="button" onClick={() => setShowAddField(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white"
              style={{ background: '#16a34a' }}
            >
              <Plus className="w-3.5 h-3.5" /> حقل جديد
            </button>
          )}
        </div>
      </header>

      {fields.length === 0 ? (
        <EmptyState
          title="لا حقول مُسجّلة بعد"
          hint={mutateAllowed ? 'أضِف حقلاً (رسم/استيراد) لتبدأ.' : 'لا حقول متاحة لعرضها.'}
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-3">
          {/* ── اللوحة اليسرى: قائمة الحقول الباحثة ── */}
          <aside className="space-y-3">
            <Card pad={12}>
              <SectionLabel
                action={<Badge tone="ok">{fields.length}</Badge>}
              >
                <span className="inline-flex items-center gap-1">
                  <SearchIcon style={{ width: 13, height: 13 }} /> الحقول
                </span>
              </SectionLabel>
              {/* مدخل بحث (اسم/محصول) — لوحة الحقول الباحثة طراز FieldView */}
              <div className="flex items-center gap-2 mb-2" style={{ background: T.card, border: `1px solid ${T.line}`, borderRadius: RADIUS.sm, padding: '6px 10px' }}>
                <SearchIcon style={{ width: 14, height: 14, color: T.muted, flexShrink: 0 }} aria-hidden="true" />
                <input
                  type="search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="ابحث باسم الحقل/المحصول…"
                  aria-label="بحث في الحقول"
                  style={{ flex: 1, border: 'none', outline: 'none', fontSize: 13, color: T.ink, background: 'transparent', fontFamily: 'inherit' }}
                />
              </div>
              <div className="space-y-1 overflow-auto" style={{ maxHeight: '46vh' }}>
                {visibleFields.length === 0 ? (
                  <div className="text-xs text-center py-3" style={{ color: T.faint }}>لا حقول مطابقة للبحث</div>
                ) : visibleFields.map((f) => {
                  const isSel = f.id === fieldId;
                  return (
                    <button
                      key={f.id}
                      onClick={() => setFieldId(f.id)}
                      className="w-full text-right rounded-lg px-3 py-2 border transition-colors"
                      style={{
                        background: isSel ? '#0e7490' : T.card2,
                        borderColor: isSel ? '#22d3ee' : T.line,
                        color: isSel ? '#e0f2fe' : T.ink,
                      }}
                    >
                      <div className="flex items-center gap-2">
                        <MapPin className="w-3.5 h-3.5 flex-shrink-0" aria-hidden="true" />
                        <span className="text-sm font-medium truncate">{f.name}</span>
                      </div>
                      <div className="text-[11px] opacity-70 mt-0.5">
                        {f.crop && f.crop !== '—' ? f.crop : 'بلا محصول'}
                        {f.area ? ` · ${f.area} هـ` : ''}
                      </div>
                    </button>
                  );
                })}
              </div>
            </Card>

            {/* بطاقة الحقل المختار + فتح الدرج */}
            {selected && (
              <Card pad={12}>
                <SectionLabel>الحقل المختار</SectionLabel>
                <div className="text-sm font-semibold" style={{ color: T.ink }}>{selected.name}</div>
                <div className="text-xs mt-0.5" style={{ color: T.muted }}>
                  {detailQ.isLoading ? 'جارٍ تحميل التفاصيل…'
                    : detailQ.data ? `${detailQ.data.crop || '—'} · ${detailQ.data.area_ha ?? selected.area} هـ`
                    : `${selected.crop} · ${selected.area} هـ`}
                </div>
                <button
                  type="button" onClick={() => setDetailOpen(true)}
                  className="mt-2 w-full text-center rounded-lg px-3 py-2 text-xs font-semibold"
                  style={{ background: T.green, color: '#fff' }}
                >
                  تفاصيل الحقل ومواسمه
                </button>
              </Card>
            )}
          </aside>

          {/* ── العمود المركزيّ: أدوات + خريطة ── */}
          <div className="space-y-3">
            {/* شريط الأدوات: الأساس + الطبقات + الشفّافيّة + الرسم/الدبابيس/المقارنة */}
            {mode === '2d' && (
              <Card pad={12}>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
                  {/* خريطة الأساس */}
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold" style={{ color: T.muted }}>الأساس</span>
                    <LayerSwitcher layers={BASEMAPS} active={basemapId} onChange={setBasemapId} />
                  </div>

                  {/* طبقات المؤشّر (تشمل «بلا» لإيقاف الطبقة) */}
                  {!compare && (
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold" style={{ color: T.muted }}>الطبقة</span>
                      <LayerSwitcher
                        layers={[{ id: '__none__', label: 'بلا' }, ...INDICATOR_LAYERS.map((l) => ({ id: l.id, label: LAYER_LEGEND[l.id]?.short ?? l.label }))]}
                        active={activeIndicator ?? '__none__'}
                        onChange={(id) => setActiveIndicator(id === '__none__' ? null : id)}
                      />
                    </div>
                  )}

                  {/* شريط الشفّافيّة — يظهر حين توجد طبقة مؤشّر نشطة */}
                  {!compare && activeIndicator && (
                    <div className="flex items-center gap-2">
                      <span className="text-xs" style={{ color: T.muted, whiteSpace: 'nowrap' }}>الشفافيّة</span>
                      <input
                        type="range" min={0} max={1} step={0.05} value={opacity}
                        onChange={(e) => setOpacity(parseFloat(e.target.value))}
                        style={{ width: 110, accentColor: T.green }}
                        aria-label="شفافية المؤشّر"
                      />
                      <span className="text-xs" style={{ color: T.muted, width: 34 }}>{Math.round(opacity * 100)}%</span>
                    </div>
                  )}

                  {/* أزرار الوضع: مقارنة / رسم / دبابيس */}
                  <div className="flex items-center gap-1.5" style={{ marginInlineStart: 'auto' }}>
                    <ToolToggle active={compare} onClick={() => { setCompare((v) => !v); setPinMode(false); }} icon={compare ? <Columns2 className="w-3.5 h-3.5" /> : <Square className="w-3.5 h-3.5" />} label="مقارنة" />
                    <ToolToggle active={drawTools} onClick={() => setDrawTools((v) => !v)} icon={<Ruler className="w-3.5 h-3.5" />} label="رسم/قياس" />
                    <ToolToggle active={pinMode} onClick={() => { setPinMode((v) => !v); setCompare(false); }} icon={<Crosshair className="w-3.5 h-3.5" />} label="دبابيس" />
                  </div>
                </div>

                {/* صفّ الدبابيس: التصنيف + المسح (يظهر في وضع الدبابيس أو حين توجد دبابيس) */}
                {(pinMode || pins.length > 0) && (
                  <div className="flex flex-wrap items-center gap-2 mt-3 pt-3" style={{ borderTop: `1px solid ${T.line}` }}>
                    <span className="text-xs font-semibold" style={{ color: T.muted }}>تصنيف الدبّوس</span>
                    <select
                      value={pinCategory} onChange={(e) => setPinCategory(e.target.value)}
                      className="px-2 py-1 rounded-lg text-xs"
                      style={{ background: T.card, border: `1px solid ${T.line}`, color: T.ink }}
                    >
                      {PIN_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
                    </select>
                    <Pill tone="info">{pins.length} دبّوس</Pill>
                    {pins.length > 0 && (
                      <button
                        type="button" onClick={handleClearPins}
                        className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-lg"
                        style={{ color: T.danger, border: `1px solid ${T.line}` }}
                      >
                        <Trash2 className="w-3 h-3" /> مسح الدبابيس
                      </button>
                    )}
                    <span className="text-[11px]" style={{ color: T.faint }}>
                      (محلّيّة — لا تُحفَظ بعد؛ بانتظار نقطة قراءة استكشاف خلفيّة)
                    </span>
                  </div>
                )}
              </Card>
            )}

            {/* الخريطة */}
            {mode === '3d' ? (
              <Suspense fallback={<LoadingState message="جارٍ تحميل وضع التضاريس…" />}>
                <TerrainView3D
                  fieldId={selected?.id}
                  fieldName={selected?.name}
                  elevationM={detailQ.data?.elevation_m ?? null}
                  slopePct={detailQ.data?.slope_pct ?? null}
                  aspect={detailQ.data?.aspect ?? null}
                />
              </Suspense>
            ) : compare ? (
              <Card pad={12}>
                <SectionLabel>مقارنة الطبقات (جنباً لجنب)</SectionLabel>
                <SideBySide
                  leftLabel={<LayerSwitcher layers={INDICATOR_LAYERS.map((l) => ({ id: l.id, label: LAYER_LEGEND[l.id]?.short ?? l.label }))} active={leftLayer} onChange={setLeftLayer} />}
                  rightLabel={<LayerSwitcher layers={INDICATOR_LAYERS.map((l) => ({ id: l.id, label: LAYER_LEGEND[l.id]?.short ?? l.label }))} active={rightLayer} onChange={setRightLayer} />}
                  left={<CompareMap fields={fields} selectedId={fieldId} basemapId={basemapId} indicatorId={leftLayer} opacity={opacity} />}
                  right={<CompareMap fields={fields} selectedId={fieldId} basemapId={basemapId} indicatorId={rightLayer} opacity={opacity} />}
                />
                <div className="text-[11px] mt-2" style={{ color: T.muted }}>
                  طبقتان حقيقيّتان لنفس الحقل والتاريخ (latest) — للموازنة البصريّة.
                </div>
              </Card>
            ) : (
              <div style={{ position: 'relative' }}>
                <HubMap
                  fields={fields}
                  selectedId={fieldId}
                  onSelect={setFieldId}
                  basemapId={basemapId}
                  indicatorId={indicatorActive}
                  indicatorOpacity={opacity}
                  drawTools={drawTools}
                  pinMode={pinMode}
                  pins={pins}
                  onAddPin={handleAddPin}
                />
                {/* مفتاح ألوان الطبقة النشطة */}
                {indicatorActive && LAYER_LEGEND[indicatorActive] && (
                  <div style={{ position: 'absolute', insetInlineStart: 10, bottom: 10, zIndex: 600, pointerEvents: 'none' }}>
                    <ColormapLegend
                      cmap={(INDICATOR_LAYERS.find((l) => l.id === indicatorActive)?.cmap) ?? 'ndvi'}
                      title={LAYER_LEGEND[indicatorActive].short}
                      lowLabel={LAYER_LEGEND[indicatorActive].low}
                      highLabel={LAYER_LEGEND[indicatorActive].high}
                    />
                  </div>
                )}
              </div>
            )}

            <div className="text-[11px]" style={{ color: T.muted }}>
              السطح الموحّد «الحقول والخريطة» — بلاطات <code>/raster</code> الحقيقيّة فوق حدود <code>/fields</code>.
              أدوات القياس من turf، الدبابيس محلّيّة (لا اختراع نقطة قراءة خلفيّة).
            </div>
          </div>
        </div>
      )}

      {/* درج تفاصيل الحقل المنزلق */}
      <FieldDetailDrawer
        fieldId={detailOpen ? fieldId : null}
        fieldName={selected?.name ?? ''}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
      />

      {/* إنشاء/استيراد حقل داخل المركز */}
      {showAddField && (
        <AddFieldWithMap
          onSave={handleSaveField}
          onImport={handleImportField}
          onCancel={() => setShowAddField(false)}
        />
      )}
    </div>
  );
}

// زرّ تبديل أداة (مقارنة/رسم/دبابيس) — موحّد الشكل.
function ToolToggle({ active, onClick, icon, label }: { active: boolean; onClick: () => void; icon: React.ReactNode; label: string }) {
  return (
    <button
      type="button" onClick={onClick}
      className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold"
      style={{
        background: active ? T.green : T.card2, color: active ? '#fff' : T.ink,
        border: `1px solid ${active ? T.green : T.line}`,
      }}
    >
      {icon}{label}
    </button>
  );
}

// لوحة خريطة مفردة لوضع المقارنة (بلا أدوات/دبابيس) — تعيد استخدام HubMap.
function CompareMap({
  fields, selectedId, basemapId, indicatorId, opacity,
}: {
  fields: ReturnType<typeof useSelectedField>['options'];
  selectedId: string; basemapId: string; indicatorId: string; opacity: number;
}) {
  const legend = LAYER_LEGEND[indicatorId];
  const cmap = INDICATOR_LAYERS.find((l) => l.id === indicatorId)?.cmap ?? 'ndvi';
  return (
    <div style={{ position: 'relative' }}>
      <HubMap
        fields={fields}
        selectedId={selectedId}
        onSelect={() => { /* المقارنة للعرض فقط — الاختيار من اللوحة اليسرى */ }}
        basemapId={basemapId}
        indicatorId={indicatorId}
        indicatorOpacity={opacity}
        drawTools={false}
        pinMode={false}
        pins={[]}
        onAddPin={() => { /* لا دبابيس في المقارنة */ }}
        height={260}
      />
      {legend && (
        <div style={{ position: 'absolute', insetInlineStart: 8, bottom: 8, zIndex: 600, pointerEvents: 'none' }}>
          <ColormapLegend cmap={cmap} title={legend.short} lowLabel={legend.low} highLabel={legend.high} />
        </div>
      )}
    </div>
  );
}
