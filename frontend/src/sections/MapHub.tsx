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
import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react';
import {
  Layers, MapPin, Columns2, Square, Ruler, Crosshair, Box, Mountain,
  Search as SearchIcon, Trash2, CloudSun, Bell, Radio, Combine, Download, Upload,
  Tractor, CheckSquare, CircleDotDashed, History, RotateCcw, Target,
} from 'lucide-react';
import { useLocation } from 'react-router-dom';
import { buildProject, downloadProject, parseProjectFile, type SahoolMapView } from '../lib/projectFile';
import { loadWorkspace, saveWorkspace } from '../lib/workspaceStorage';
import { MAP_ENGINE } from '../lib/featureFlags';
import { useSelectedField } from '../hooks/useSelectedField';
import { useFieldDetail, useAlerts, useDevices, useWeatherForecast, useEquipment, useTasks } from '../hooks/useApi';
import { fieldRepresentativePoint } from '../lib/geo';
import { kongApi, asApiError, refreshFieldImagery, fetchFieldImageryAvailableDates, type FieldImageryDateOption } from '../services/api';
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
import HubMap, {
  type ScoutPin, type AlertMarker, type DeviceMarker, type WeatherMarker, type OperationalMarker,
} from '../components/maphub/HubMap';
import FieldDetailDrawer from '../components/maphub/FieldDetailDrawer';
import FieldSplitMergeTool from '../components/maphub/FieldSplitMergeTool';
import type { DrawFeature } from '../components/maphub/drawing';
import { buildPivotDrawFeature, summarizePivotDesign } from '../components/maphub/drawing';

// العرض ثلاثيّ الأبعاد مقسوم بالكود — لا يُحمَّل إلا عند تفعيل وضع التضاريس،
// فلا يُثقِل الحزمة الأساسيّة (يحوي مستقبلاً maplibre-gl الثقيل).
const TerrainView3D = lazy(() => import('../components/maphub/TerrainView3D'));

// محرّك MapLibre GL (WebGL) — إثبات مفهوم المرحلة 2 خلف عَلَم MAP_ENGINE. مقسوم
// بالكود (lazy) فلا يُحمَّل maplibre-gl الثقيل (~250KB) إلا عند تفعيل العَلَم.
const HubMapGL = lazy(() => import('../components/maphub/HubMapGL'));

// هل محرّك MapLibre مُفعَّل؟ (الافتراض leaflet). المرحلة 2ب: الرسم/القياس (Terra
// Draw) والدبابيس والتراكبات متاحة في كِلا المحرّكين (تكافؤ المزايا).
const GL_ENGINE = MAP_ENGINE === 'maplibre';

// ── الطبقات القابلة للعرض كبلاطات مؤشّر (raster) — من السجلّ ──
// كلّ المؤشّرات التي يحسبها raster-service (CDSE INDEX_EXPR) مع لوحة DS موجودة.
// ('moisture' المكافئ لـNDMI مُستثنى تفادياً للتكرار.)
const RASTER_INDEX_IDS = new Set([
  'ndvi', 'ndmi', 'salinity', 'evi', 'savi', 'msavi', 'ndwi', 'gndvi', 'ndre', 'msi',
]);
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
  evi: { short: 'EVI', low: 'إجهاد', high: 'كثيف' },
  savi: { short: 'SAVI', low: 'إجهاد', high: 'كثيف' },
  msavi: { short: 'MSAVI', low: 'إجهاد', high: 'كثيف' },
  ndwi: { short: 'NDWI', low: 'جافّ', high: 'مياه' },
  gndvi: { short: 'GNDVI', low: 'منخفض', high: 'مرتفع' },
  ndre: { short: 'NDRE', low: 'منخفض', high: 'مرتفع' },
  msi: { short: 'MSI', low: 'رطب', high: 'إجهاد' },
};

const PIN_CATEGORIES = ['آفة', 'مرض', 'نقص تغذية', 'إجهاد مائيّ', 'عشب ضارّ', 'أخرى'];

type MapHubLocationState = {
  fieldId?: string;
  openCdse?: boolean;
  indicator?: string;
  from?: string;
  showWeather?: boolean;
};

export default function MapHub() {
  const location = useLocation();
  const routeState = (location.state ?? {}) as MapHubLocationState;
  const { options: fields, isLoading, isError, refetch, fieldId, setFieldId } = useSelectedField();
  const { user, tenantId } = useAuthStore();
  const mutateAllowed = canMutate(user?.role);

  const detailQ = useFieldDetail(fieldId || undefined);

  // ── حالة العرض (تُستعاد تلقائيّاً من localStorage — «العودة لنفس البيئة») ──────
  const savedWorkspace = useMemo(() => loadWorkspace(), []);
  const [mode, setMode] = useState<'2d' | '3d'>(savedWorkspace?.mode === '3d' ? '3d' : '2d');
  const [basemapId, setBasemapId] = useState<string>(savedWorkspace?.basemapId ?? (BASEMAPS[0]?.id ?? 'satellite'));
  const initialSearch = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const routeFieldId = routeState.fieldId ?? initialSearch.get('field_id') ?? initialSearch.get('fieldId') ?? undefined;
  const routeIndicator = routeState.indicator ?? initialSearch.get('index') ?? initialSearch.get('indicator') ?? undefined;
  const requestedCdseOpen = routeState.openCdse === true || initialSearch.get('source') === 'my-fields' || !!routeIndicator;
  const requestedWeatherOpen = routeState.showWeather === true
    || initialSearch.get('weather') === '1'
    || initialSearch.get('weather') === 'true'
    || initialSearch.get('source') === 'my-fields';
  // فتح «حقل جديد» عبر رابط عميق (من شاشة «حقولي») — زرّ الإنشاء انتقل إلى حقولي.
  const requestedAddOpen = initialSearch.get('add') === '1';
  const [activeIndicator, setActiveIndicator] = useState<string | null>(
    requestedCdseOpen ? (routeIndicator || 'ndvi') : (savedWorkspace?.activeIndicator ?? null),
  ); // null = لا مؤشّر
  const [imageryTs, setImageryTs] = useState(0); // cache-bust للبلاطات بعد معالجة Sentinel/COG
  const [selectedImageryDate, setSelectedImageryDate] = useState<string>('latest');
  const [availableImageryDates, setAvailableImageryDates] = useState<FieldImageryDateOption[]>([]);
  const [opacity, setOpacity] = useState(savedWorkspace?.opacity ?? 0.75);
  const [compare, setCompare] = useState(savedWorkspace?.compare ?? false);
  const [leftLayer, setLeftLayer] = useState<string>(savedWorkspace?.leftLayer ?? (INDICATOR_LAYERS[0]?.id ?? 'ndvi'));
  const [rightLayer, setRightLayer] = useState<string>(savedWorkspace?.rightLayer ?? (INDICATOR_LAYERS[1]?.id ?? 'ndmi'));
  const [drawTools, setDrawTools] = useState(savedWorkspace?.drawTools ?? false);
  const [pinMode, setPinMode] = useState(savedWorkspace?.pinMode ?? false);
  // ── طبقات التراكب (مستقلّة؛ تُستعاد من المخزن) ──────────
  const [showWeather, setShowWeather] = useState(savedWorkspace?.showWeather ?? false);
  const [showAlerts, setShowAlerts] = useState(savedWorkspace?.showAlerts ?? false);
  const [showDevices, setShowDevices] = useState(savedWorkspace?.showDevices ?? false);
  const [showEquipment, setShowEquipment] = useState(false);
  const [showTasks, setShowTasks] = useState(false);
  const [showPivots, setShowPivots] = useState(false);
  const [pivotDesigner, setPivotDesigner] = useState(false);
  const [pivotRadiusM, setPivotRadiusM] = useState(400);
  const [pivotStartAngleDeg, setPivotStartAngleDeg] = useState(0);
  const [pivotEndAngleDeg, setPivotEndAngleDeg] = useState(360);
  const [pivotRingCount, setPivotRingCount] = useState(4);
  const [pivotSpanCount, setPivotSpanCount] = useState(8);
  const [pivotDrafts, setPivotDrafts] = useState<DrawFeature[]>([]);
  const [pins, setPins] = useState<ScoutPin[]>([]);
  const [pinCategory, setPinCategory] = useState(savedWorkspace?.pinCategory || PIN_CATEGORIES[0]);
  // ── v2: لقطة عرض الخريطة (مركز lat/lng + تكبير) — تُستعاد وتُلتقط من الخريطة ──
  const [mapView, setMapView] = useState<SahoolMapView | null>(savedWorkspace?.mapView ?? null);
  // مفتاح إعادة التركيب — يتغيّر عند استيراد مشروع ذي عرض، فتُعاد الخريطة وتبدأ من
  // العرض الجديد (initialView). أوّل تحميل = 0 (لقطة localStorage تُمرَّر كـinitialView).
  const [restoreKey, setRestoreKey] = useState(0);
  // اللقطة الابتدائيّة للتمرير للخريطة عند (إعادة) التركيب. تُلتقط من الحالة الحاليّة
  // عند تغيّر restoreKey فقط — لا تتغيّر مع التقاط الحركة (mapView state) كي لا تُعاد
  // الخريطة عند كلّ moveend. (mapView يُقرأ عمداً مرّةً عند كلّ remount.)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const initialMapView = useMemo<SahoolMapView | null>(() => mapView, [restoreKey]);
  const [detailOpen, setDetailOpen] = useState(false);
  const [showAddField, setShowAddField] = useState(false);
  const [showSplitMerge, setShowSplitMerge] = useState(false); // أداة الدمج/التقسيم — مغلقة افتراضيّاً
  const [search, setSearch] = useState('');
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [geometryHistory, setGeometryHistory] = useState<Array<{ revision: number; changed_at?: string | null; reason?: string | null; source?: string | null }>>([]);
  const [geometryHistoryBusy, setGeometryHistoryBusy] = useState(false);
  const [geometryRevertBusy, setGeometryRevertBusy] = useState<number | null>(null);

  // ── حفظ/استيراد مساحة العمل (.sahool-project.json) — مستوحى من GeoLibre ──────
  // عميل-فقط: التصدير يقرأ الحالة الحاليّة، والاستيراد يستدعي الـsetters القائمة.
  const projectInputRef = useRef<HTMLInputElement>(null);
  const imageryRefreshKeyRef = useRef<string>('');

  // فتح مباشر من صفحة «حقولي»: الرابط يحدد الحقل والمؤشّر، والمتجر المشترك يُثبَّت
  // قبل أن يعرض MapHub الخريطة. هذا يجعل /fields → اختيار صف → /fields/map-center
  // مساراً قابلاً للمشاركة ويعرض CDSE/NDVI للحقل المختار دون الاعتماد على حالة ذاكرة فقط.
  useEffect(() => {
    if (!routeFieldId) return;
    if (fields.length && !fields.some((f) => f.id === routeFieldId)) return;
    if (fieldId !== routeFieldId) setFieldId(routeFieldId);
  }, [routeFieldId, fields, fieldId, setFieldId]);

  useEffect(() => {
    if (!requestedCdseOpen) return;
    const next = routeIndicator || 'ndvi';
    if (INDICATOR_LAYERS.some((l) => l.id === next)) setActiveIndicator(next);
    setCompare(false);
    setMode('2d');
  }, [requestedCdseOpen, routeIndicator]);

  useEffect(() => {
    if (!requestedWeatherOpen) return;
    setShowWeather(true);
  }, [requestedWeatherOpen]);

  // رابط عميق ?add=1 (من «حقولي») يفتح نموذج إنشاء الحقل — مقيَّد بصلاحيّة التعديل.
  useEffect(() => {
    if (requestedAddOpen && mutateAllowed) setShowAddField(true);
  }, [requestedAddOpen, mutateAllowed]);

  // التقاط عرض الخريطة (moveend من أيّ محرّك) — كتابة مُتسامِحة (idempotent): إن
  // لم يتغيّر المركز/التكبير لا نُحدّث الحالة، فلا حلقة استعادة↔حركة ولا حفظ زائد.
  const handleViewChange = useCallback((center: [number, number], zoom: number) => {
    const next: SahoolMapView = { centerLat: center[0], centerLng: center[1], zoom };
    setMapView((prev) => {
      if (prev
        && prev.centerLat === next.centerLat
        && prev.centerLng === next.centerLng
        && prev.zoom === next.zoom) return prev; // لا تغيير ⇒ لا re-render/حفظ
      return next;
    });
  }, []);

  // تواريخ CDSE المتاحة للحقل. الربط مهم: لا نترك رابط البلاطات يطلب latest
  // عندما يختار المستخدم مشهداً محدداً، حتى لا تختلط طبقات/كاش بتواريخ مختلفة.
  useEffect(() => {
    if (!fieldId || mode !== '2d') {
      setAvailableImageryDates([]);
      setSelectedImageryDate('latest');
      return;
    }
    let cancelled = false;
    fetchFieldImageryAvailableDates(fieldId)
      .then((dates) => {
        if (cancelled) return;
        const sorted = [...dates].sort((a, b) => b.date.localeCompare(a.date));
        setAvailableImageryDates(sorted);
        setSelectedImageryDate((prev) => {
          if (prev === 'latest') return prev;
          return sorted.some((d) => d.date === prev) ? prev : 'latest';
        });
      })
      .catch(() => {
        if (!cancelled) setAvailableImageryDates([]);
      });
    return () => { cancelled = true; };
  }, [fieldId, mode]);

  // عند اختيار مؤشّر وحقل، نطلب معالجة/تحديث صور Sentinel ثم نكسر كاش البلاطات.
  // هذا لا يصنع قيماً وهمية: إذا لم تنتج الخلفية COG حقيقي، ستظل البلاطات شفافة.
  useEffect(() => {
    if (!fieldId || !activeIndicator || mode !== '2d') return;
    const key = `${tenantId ?? 'default'}:${fieldId}:${activeIndicator}:${selectedImageryDate}`;
    if (imageryRefreshKeyRef.current === key) return;
    imageryRefreshKeyRef.current = key;
    let cancelled = false;
    refreshFieldImagery(fieldId, selectedImageryDate)
      .then(() => {
        window.setTimeout(() => {
          if (!cancelled) setImageryTs(Date.now());
        }, 20000);
      })
      .catch(() => {
        // فشل المزود أو غياب الاعتمادات لا يكسر الخريطة؛ نعيد الجلب لكشف أي طبقة مخزنة سابقاً.
        if (!cancelled) setImageryTs(Date.now());
      });
    return () => { cancelled = true; };
  }, [fieldId, activeIndicator, mode, tenantId, selectedImageryDate]);

  useEffect(() => {
    if (!fieldId) {
      setGeometryHistory([]);
      return;
    }
    let cancelled = false;
    setGeometryHistoryBusy(true);
    kongApi.get(`/api/v1/fields/${fieldId}/geometry/history?limit=8`)
      .then((res) => {
        if (cancelled) return;
        const revisions = Array.isArray(res.data?.revisions) ? res.data.revisions : [];
        setGeometryHistory(revisions.map((r: Record<string, unknown>) => ({
          revision: Number(r.revision),
          changed_at: typeof r.changed_at === 'string' ? r.changed_at : null,
          reason: typeof r.reason === 'string' ? r.reason : null,
          source: typeof r.source === 'string' ? r.source : null,
        })).filter((r: { revision: number }) => Number.isFinite(r.revision)));
      })
      .catch(() => { if (!cancelled) setGeometryHistory([]); })
      .finally(() => { if (!cancelled) setGeometryHistoryBusy(false); });
    return () => { cancelled = true; };
  }, [fieldId]);

  const handleRevertGeometry = useCallback(async (revision: number) => {
    if (!fieldId || geometryRevertBusy !== null) return;
    const ok = window.confirm(`استرجاع حدود الحقل إلى المراجعة #${revision}؟ سيتم إبطال بلاطات المؤشرات القديمة وإعادة المعالجة.`);
    if (!ok) return;
    setGeometryRevertBusy(revision);
    try {
      await kongApi.post(`/api/v1/fields/${fieldId}/geometry/revert/${revision}`);
      toastStore.add('success', '✅ تم استرجاع الحدود', `المراجعة #${revision}`);
      await refetch();
      setImageryTs(Date.now());
      const res = await kongApi.get(`/api/v1/fields/${fieldId}/geometry/history?limit=8`);
      setGeometryHistory(Array.isArray(res.data?.revisions) ? res.data.revisions : []);
    } catch (e) {
      toastStore.add('error', 'تعذّر استرجاع الحدود', asApiError(e).message || 'تحقّق من الصلاحيّة أو سجلّ المراجعات.');
    } finally {
      setGeometryRevertBusy(null);
    }
  }, [fieldId, geometryRevertBusy, refetch]);

  const handleExportProject = useCallback(() => {
    const project = buildProject({
      mode, basemapId, activeIndicator, opacity, compare, leftLayer, rightLayer,
      drawTools, pinMode, showWeather, showAlerts, showDevices, pinCategory,
      selectedFieldId: fieldId, mapView,
    });
    downloadProject(project, `sahool-project-${new Date().toISOString().slice(0, 10)}.json`);
    toastStore.add('success', '✅ حُفِظ المشروع', 'نُزِّلت مساحة العمل كملفّ');
  }, [mode, basemapId, activeIndicator, opacity, compare, leftLayer, rightLayer,
      drawTools, pinMode, showWeather, showAlerts, showDevices, pinCategory, fieldId, mapView]);

  const handleImportProject = useCallback(async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.currentTarget.files?.[0];
    e.currentTarget.value = ''; // اسمح بإعادة استيراد نفس الملفّ
    if (!file) return;
    try {
      const w = await parseProjectFile(file);
      setMode(w.mode);
      setBasemapId(w.basemapId);
      setActiveIndicator(w.activeIndicator);
      setOpacity(w.opacity);
      setCompare(w.compare);
      setLeftLayer(w.leftLayer);
      setRightLayer(w.rightLayer);
      setDrawTools(w.drawTools);
      setPinMode(w.pinMode);
      setShowWeather(w.showWeather);
      setShowAlerts(w.showAlerts);
      setShowDevices(w.showDevices);
      if (w.pinCategory) setPinCategory(w.pinCategory);
      if (w.selectedFieldId) setFieldId(w.selectedFieldId);
      // v2: استعادة عرض الخريطة المستورد. تحديث mapView + بصمة الاستعادة يُعيد
      // تركيب الخريطة (مفتاح remount) فتبدأ من العرض الجديد — كأوّل تحميل تماماً.
      setMapView(w.mapView);
      if (w.mapView) setRestoreKey((k) => k + 1);
      toastStore.add('success', '✅ استُورِد المشروع', 'استُعيدت مساحة العمل');
    } catch (err) {
      toastStore.add('error', '⚠️ فشل استيراد المشروع',
        err instanceof Error ? err.message : 'ملفّ غير صالح');
    }
  }, [setFieldId]);

  // حفظ تلقائيّ لإعدادات مساحة العمل عند أيّ تغيير ⇒ تُستعاد عند الفتح التالي (بلا حفظ يدويّ).
  useEffect(() => {
    saveWorkspace({
      mode, basemapId, activeIndicator, opacity, compare, leftLayer, rightLayer,
      drawTools, pinMode, showWeather, showAlerts, showDevices, pinCategory, mapView,
    });
  }, [mode, basemapId, activeIndicator, opacity, compare, leftLayer, rightLayer,
      drawTools, pinMode, showWeather, showAlerts, showDevices, pinCategory, mapView]);

  const selected = fields.find((f) => f.id === fieldId);
  const indicatorActive = mode === '2d' && !compare ? activeIndicator : null;

  // قائمة الحقول المُرشَّحة بالبحث (اسم/محصول) — لوحة الحقول الباحثة.
  const visibleFields = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return fields;
    return fields.filter((f) =>
      f.name.toLowerCase().includes(q) || (f.crop ?? '').toLowerCase().includes(q));
  }, [fields, search]);


  const fieldSummary = useMemo(() => {
    const totalArea = fields.reduce((sum, f) => sum + (Number(f.area) || 0), 0);
    const crops = new Set(fields.map((f) => (f.crop || '').trim()).filter((c) => c && c !== '—'));
    const withGeometry = fields.filter((f) => Boolean(fieldRepresentativePoint(f))).length;
    return { totalArea, cropCount: crops.size, withGeometry };
  }, [fields]);

  const selectedHasActiveSeason = useMemo(() => {
    const d = detailQ.data as unknown as Record<string, unknown> | undefined;
    if (!d) return false;
    if (d.active_season || d.current_season) return true;
    const seasons = d.seasons;
    if (Array.isArray(seasons)) {
      return seasons.some((season) => {
        const s = season as Record<string, unknown>;
        return s.status === 'active' || s.active === true || !s.season_end;
      });
    }
    return false;
  }, [detailQ.data]);

  const mapDataStatus = useMemo(() => {
    if (!fieldId) return { tone: 'warn' as const, label: 'اختر حقلاً', hint: 'لن تُحمّل المؤشرات قبل تحديد حقل.' };
    if (!indicatorActive) return { tone: 'info' as const, label: 'لا مؤشر نشط', hint: 'اختر NDVI أو NDMI أو الملوحة لعرض الصور الجوية.' };
    return { tone: 'ok' as const, label: 'مؤشر نشط', hint: `سيتم تحميل ${LAYER_LEGEND[indicatorActive]?.short ?? indicatorActive} داخل حدود الحقل.` };
  }, [fieldId, indicatorActive]);

  // ── بيانات طبقات التراكب (حيّة، أمانة صارمة) ──────────────────
  // تنبيهات/أجهزة استعلامات React Query رخيصة مُخزَّنة — نُشغّلها دوماً (لا نُهدر
  // طلبات؛ مفعّل دائماً ويُعاد الاستخدام من الكاش). نُظهرها فقط حين التبديل مفعّل.
  const alertsQ = useAlerts({ status: 'active' });
  const devicesQ = useDevices();
  const equipmentQ = useEquipment();
  const tasksQ = useTasks();

  // فهرس النقطة الممثِّلة لكلّ حقل (lat/lng) — حقول بلا هندسة/نقطة غير قابلة للعرض.
  const fieldPointById = useMemo(() => {
    const m = new Map<string, [number, number]>();
    for (const f of fields) {
      const pt = fieldRepresentativePoint(f);
      if (pt) m.set(f.id, pt);
    }
    return m;
  }, [fields]);
  const fieldNameById = useMemo(() => {
    const m = new Map<string, string>();
    for (const f of fields) m.set(f.id, f.name);
    return m;
  }, [fields]);

  // علامات التنبيهات: تُوضَع عند النقطة الممثِّلة لحقل التنبيه فقط. تنبيه بلا
  // field_id أو بحقلٍ بلا هندسة/نقطة = غير قابل للعرض ⇒ يُحتسَب، لا تُختلَق نقطة.
  const { alertMarkers, alertsUnplaceable } = useMemo(() => {
    const list = alertsQ.data ?? [];
    const markers: AlertMarker[] = [];
    let unplaceable = 0;
    for (const a of list) {
      const pt = a.field_id ? fieldPointById.get(a.field_id) : undefined;
      if (!pt) { unplaceable += 1; continue; }
      markers.push({
        id: a.alert_id,
        lat: pt[0], lng: pt[1],
        severity: String(a.severity ?? 'info'),
        title: a.title_ar ?? a.alert_type ?? 'تنبيه',
        fieldName: a.field_id ? (fieldNameById.get(a.field_id) ?? '') : '',
      });
    }
    return { alertMarkers: markers, alertsUnplaceable: unplaceable };
  }, [alertsQ.data, fieldPointById, fieldNameById]);

  // علامات الأجهزة: عند النقطة الممثِّلة لحقل الجهاز فقط. جهاز بلا field_id أو
  // بحقلٍ بلا هندسة/نقطة = غير قابل للعرض ⇒ يُحتسَب، لا تُختلَق إحداثيّة.
  const { deviceMarkers, devicesUnplaceable } = useMemo(() => {
    const list = devicesQ.data ?? [];
    const markers: DeviceMarker[] = [];
    let unplaceable = 0;
    for (const d of list) {
      const pt = d.field_id ? fieldPointById.get(d.field_id) : undefined;
      if (!pt) { unplaceable += 1; continue; }
      markers.push({
        id: d.device_id,
        lat: pt[0], lng: pt[1],
        name: d.name,
        dtype: d.type,
        online: !!d.online,
      });
    }
    return { deviceMarkers: markers, devicesUnplaceable: unplaceable };
  }, [devicesQ.data, fieldPointById]);


  // طبقات تشغيلية على نفس الخريطة: المعدّات/المهام/المحوري. لا تُختلق إحداثيات؛
  // العنصر لا يظهر إلا إذا ارتبط بحقل له هندسة/نقطة. هذا يطابق نمط John Deere/FieldView:
  // الخريطة هي مركز التشغيل، لكن السجلات التفصيلية تبقى في اللوحات الجانبية.
  const { equipmentMarkers, equipmentUnplaceable } = useMemo(() => {
    const list = equipmentQ.data ?? [];
    const markers: OperationalMarker[] = [];
    let unplaceable = 0;
    for (const e of list) {
      const row = e as typeof e & { field_id?: string | null; field_name?: string | null };
      const pt = row.field_id ? fieldPointById.get(row.field_id) : undefined;
      if (!pt) { unplaceable += 1; continue; }
      markers.push({
        id: row.equipment_id,
        lat: pt[0], lng: pt[1],
        kind: 'equipment',
        title: row.name,
        subtitle: `${row.type}${row.field_name ? ` · ${row.field_name}` : ''}`,
        status: row.status,
      });
    }
    return { equipmentMarkers: markers, equipmentUnplaceable: unplaceable };
  }, [equipmentQ.data, fieldPointById]);

  const { taskMarkers, tasksUnplaceable } = useMemo(() => {
    const list = tasksQ.data?.tasks ?? [];
    const markers: OperationalMarker[] = [];
    let unplaceable = 0;
    for (const t of list) {
      const pt = t.field_id ? fieldPointById.get(t.field_id) : undefined;
      if (!pt) { unplaceable += 1; continue; }
      markers.push({
        id: t.task_id,
        lat: pt[0], lng: pt[1],
        kind: 'task',
        title: t.task_type,
        subtitle: `${fieldNameById.get(t.field_id) ?? t.field_name ?? 'حقل'} · ${t.status}`,
        status: t.status,
      });
    }
    return { taskMarkers: markers, tasksUnplaceable: unplaceable };
  }, [tasksQ.data, fieldPointById, fieldNameById]);

  const pivotMarkers = useMemo<OperationalMarker[]>(() => {
    if (!selected || !showPivots) return [];
    const detail = detailQ.data as { irrigation_type?: string | null; pivot?: unknown } | undefined;
    const hasPivot = String(detail?.irrigation_type ?? '').toLowerCase().includes('pivot') || detail?.pivot != null;
    const pt = fieldPointById.get(selected.id);
    if (!hasPivot || !pt) return [];
    return [{
      id: `pivot-${selected.id}`,
      lat: pt[0], lng: pt[1],
      kind: 'pivot',
      title: `محوري ${selected.name}`,
      subtitle: 'طبقة محوري مرتبطة بالحقل المختار',
      status: 'active',
    }];
  }, [selected, showPivots, detailQ.data, fieldPointById]);

  const operationalMarkers = useMemo<OperationalMarker[]>(() => [
    ...(showEquipment ? equipmentMarkers : []),
    ...(showTasks ? taskMarkers : []),
    ...pivotMarkers,
  ], [showEquipment, showTasks, equipmentMarkers, taskMarkers, pivotMarkers]);

  // الطقس: نقطة واحدة فقط للحقل المختار (تجنّب N طلبات لكلّ الحقول). نحسب lat/lon
  // من النقطة الممثِّلة للمختار؛ الافتراضات الآمنة تُمرَّر حين لا حقل/نقطة، لكنّنا
  // لا نَعرض الشارة إلّا حين يوجد حقل مختار له نقطة (selectedPoint).
  const selectedPoint = useMemo<[number, number] | null>(
    () => (selected ? fieldRepresentativePoint(selected) : null),
    [selected],
  );
  const weatherQ = useWeatherForecast(selectedPoint?.[0] ?? 15.05, selectedPoint?.[1] ?? 45.55);
  const weatherMarker = useMemo<WeatherMarker | null>(() => {
    if (!selectedPoint) return null;
    const cur = weatherQ.data?.current;
    return {
      fieldId: selected?.id ?? null,
      lat: selectedPoint[0], lng: selectedPoint[1],
      tempC: cur?.tmean ?? null,
      humidityPct: cur?.humidity_pct ?? null,
      conditionAr: cur?.weather_ar ?? null,
      windSpeedKmh: cur?.wind_speed_kmh ?? null,
      windDirectionDeg: cur?.wind_direction_deg ?? null,
    };
  }, [selected, selectedPoint, weatherQ.data]);

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

  // ── v36: Pivot Designer مرئي داخل MapHub ─────────────────────
  // النقر على الخريطة في وضع التصميم ينشئ قطاع pivot كـ DrawFeature محليّ.
  // الحفظ الدائم سيأتي في مرحلة Backend CRUD/PostGIS، لذلك نعلّمه draft=true.
  const handleAddPivotDraft = useCallback((lat: number, lng: number) => {
    if (!selected) {
      toastStore.add('warning', 'اختر حقلاً أولاً', 'تصميم المحوري يحتاج حقلاً مختاراً لربط التصميم به.');
      return;
    }
    const feature = buildPivotDrawFeature({
      center: [lng, lat],
      radiusM: pivotRadiusM,
      startAngleDeg: pivotStartAngleDeg,
      endAngleDeg: pivotEndAngleDeg,
      ringCount: pivotRingCount,
      spanCount: pivotSpanCount,
      fieldId: selected.id,
      name: `Pivot ${selected.name}`,
    });
    setPivotDrafts((prev) => [...prev, feature]);
    setShowPivots(true);
    toastStore.add('success', 'تم إنشاء تصميم Pivot', `المساحة التقريبية ${(feature.measurements?.areaHa ?? 0).toFixed(2)} هـ`);
  }, [pivotEndAngleDeg, pivotRadiusM, pivotRingCount, pivotSpanCount, pivotStartAngleDeg, selected]);

  const handleClearPivotDrafts = useCallback(() => setPivotDrafts([]), []);

  const pivotSummary = useMemo(() => summarizePivotDesign({
    center: selectedPoint ? [selectedPoint[1], selectedPoint[0]] : [44, 15],
    radiusM: pivotRadiusM,
    startAngleDeg: pivotStartAngleDeg,
    endAngleDeg: pivotEndAngleDeg,
    ringCount: pivotRingCount,
    spanCount: pivotSpanCount,
  }), [pivotEndAngleDeg, pivotRadiusM, pivotRingCount, pivotSpanCount, pivotStartAngleDeg, selectedPoint]);

  // ── إنشاء/استيراد حقل (نفس مسار FieldManagementPage الحقيقيّ) ──
  const handleSaveField = useCallback(async (data: {
    name: string; manager: string; crop: string; soil_type: string;
    field_code?: string; water_source?: string; irrigation_type?: string; pivot?: unknown; country?: string; region?: string;
    area_ha: number; geometry: { type: string; coordinates: number[][][] };
  }) => {
    try {
      await kongApi.post('/api/v1/fields', {
        name: data.name, crop: data.crop, soil_type: data.soil_type, manager: data.manager,
        field_code: data.field_code ?? null, water_source: data.water_source ?? null,
        irrigation_type: data.irrigation_type ?? null, pivot: data.pivot ?? null,
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


  const handleDeleteSelectedField = useCallback(async () => {
    if (!selected || deleteBusy) return;
    if (selectedHasActiveSeason) {
      toastStore.add('warning', 'لا يمكن حذف الحقل', 'يوجد موسم نشط مرتبط بهذا الحقل. أغلق الموسم أو انقله أولاً.');
      return;
    }
    setDeleteBusy(true);
    try {
      await kongApi.delete(`/api/v1/fields/${selected.id}`);
      toastStore.add('success', '🗑️ تم حذف الحقل', selected.name);
      setDeleteConfirmOpen(false);
      setFieldId('');
      await refetch();
    } catch (e) {
      toastStore.add('error', 'تعذّر حذف الحقل', asApiError(e).message || 'تحقّق من الصلاحيّة أو وجود موسم نشط.');
    } finally {
      setDeleteBusy(false);
    }
  }, [deleteBusy, refetch, selected, selectedHasActiveSeason, setFieldId]);

  if (isLoading) return <LoadingState message="جارٍ تحميل مركز الخرائط…" />;
  if (isError) return <ErrorState title="تعذّر تحميل الحقول" onRetry={() => refetch()} />;


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
              type="button" onClick={() => setMode('2d')} data-testid="btn-mode-2d"
              className="flex items-center gap-1 px-3 py-1.5 text-xs font-semibold"
              style={{ background: mode === '2d' ? T.green : 'transparent', color: mode === '2d' ? '#fff' : T.muted }}
            >
              <Box className="w-3.5 h-3.5" /> 2D
            </button>
            <button
              type="button" onClick={() => setMode('3d')} data-testid="btn-mode-3d"
              className="flex items-center gap-1 px-3 py-1.5 text-xs font-semibold"
              style={{ background: mode === '3d' ? T.green : 'transparent', color: mode === '3d' ? '#fff' : T.muted }}
            >
              <Mountain className="w-3.5 h-3.5" /> تضاريس(3D)
            </button>
          </div>
          {mutateAllowed && (
            <button
              type="button" onClick={() => setShowSplitMerge(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold"
              style={{ background: T.card2, color: T.ink, border: `1px solid ${T.line}` }}
            >
              <Combine className="w-3.5 h-3.5" /> دمج/تقسيم
            </button>
          )}
          {/* زرّ «حقل جديد» انتقل إلى شاشة «حقولي» (MyFieldsPage)؛ يُفتَح هنا عبر ?add=1.
              نموذج AddFieldWithMap يبقى أدناه (يُفعَّل بالرابط العميق). */}
          {/* حفظ/استيراد مساحة العمل (.sahool-project.json) — عميل-فقط، متاح للجميع */}
          <button
            type="button" onClick={handleExportProject} title="حفظ مساحة العمل كملفّ"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold"
            style={{ background: T.card2, color: T.ink, border: `1px solid ${T.line}` }}
          >
            <Download className="w-3.5 h-3.5" /> حفظ المشروع
          </button>
          <button
            type="button" onClick={() => projectInputRef.current?.click()} title="استيراد مساحة عمل"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold"
            style={{ background: T.card2, color: T.ink, border: `1px solid ${T.line}` }}
          >
            <Upload className="w-3.5 h-3.5" /> استيراد
          </button>
          <input
            ref={projectInputRef} type="file" accept=".json,application/json"
            onChange={handleImportProject} style={{ display: 'none' }}
          />
        </div>
      </header>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3" data-testid="maphub-summary">
        <SummaryStat label="إجمالي الحقول" value={String(fields.length)} />
        <SummaryStat label="المساحة الكلية" value={`${fieldSummary.totalArea.toFixed(1)} هـ`} />
        <SummaryStat label="محاصيل مختلفة" value={String(fieldSummary.cropCount)} />
        <SummaryStat label="حقول بهندسة" value={`${fieldSummary.withGeometry}/${fields.length}`} />
      </div>

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
                      data-testid={`field-${f.id}`}
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
                <div className="mt-2 grid grid-cols-[1fr_auto] gap-2">
                  <button
                    type="button" onClick={() => setDetailOpen(true)}
                    className="text-center rounded-lg px-3 py-2 text-xs font-semibold"
                    style={{ background: T.green, color: '#fff' }}
                  >
                    تفاصيل الحقل ومواسمه
                  </button>
                  {mutateAllowed && (
                    <button
                      type="button"
                      data-testid="delete-selected-field"
                      onClick={() => selectedHasActiveSeason ? toastStore.add('warning', 'لا يمكن حذف الحقل', 'يوجد موسم نشط مرتبط بهذا الحقل.') : setDeleteConfirmOpen(true)}
                      title={selectedHasActiveSeason ? 'لا يمكن حذف حقل مرتبط بموسم نشط' : 'حذف الحقل'}
                      className="inline-flex items-center justify-center rounded-lg px-3 py-2 text-xs font-semibold"
                      style={{ background: selectedHasActiveSeason ? '#475569' : '#7f1d1d', color: '#fff', border: `1px solid ${selectedHasActiveSeason ? '#64748b' : '#ef4444'}` }}
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>
                {selectedHasActiveSeason && (
                  <div className="mt-2 text-[11px]" style={{ color: '#fbbf24' }}>
                    حذف الحقل معطّل لأن هناك موسماً نشطاً مرتبطاً به.
                  </div>
                )}
              </Card>
            )}

            {selected && (
              <Card pad={12}>
                <SectionLabel
                  action={<Badge tone={geometryHistory.length > 1 ? 'ok' : 'neutral'}>{geometryHistory.length}</Badge>}
                >
                  <span className="inline-flex items-center gap-1">
                    <History className="w-3.5 h-3.5" /> سجلّ الحدود
                  </span>
                </SectionLabel>
                {geometryHistoryBusy ? (
                  <div className="text-xs" style={{ color: T.muted }}>جارٍ تحميل إصدارات الحدود…</div>
                ) : geometryHistory.length === 0 ? (
                  <div className="text-xs" style={{ color: T.faint }}>لا يوجد سجلّ حدود متاح بعد.</div>
                ) : (
                  <div className="space-y-1.5" data-testid="geometry-history-panel">
                    {geometryHistory.slice(0, 5).map((r, idx) => (
                      <div key={`${r.revision}-${idx}`} className="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5" style={{ background: T.card2, border: `1px solid ${T.line}` }}>
                        <div className="min-w-0">
                          <div className="text-xs font-semibold" style={{ color: T.ink }}>مراجعة #{r.revision}</div>
                          <div className="text-[10px] truncate" style={{ color: T.faint }}>
                            {(r.changed_at ? new Date(r.changed_at).toLocaleString('ar') : '—')} · {r.reason ?? r.source ?? 'تحديث حدود'}
                          </div>
                        </div>
                        {mutateAllowed && idx > 0 && (
                          <button
                            type="button"
                            data-testid={`revert-geometry-${r.revision}`}
                            onClick={() => handleRevertGeometry(r.revision)}
                            disabled={geometryRevertBusy !== null}
                            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-semibold"
                            style={{ background: '#1f2937', color: '#e5e7eb', opacity: geometryRevertBusy !== null ? 0.6 : 1 }}
                          >
                            <RotateCcw className="w-3 h-3" /> استرجاع
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            )}
          </aside>

          {/* ── العمود المركزيّ: أدوات + خريطة ── */}
          <div className="space-y-3">
            <Card pad={12}>
              <div className="flex flex-wrap items-center justify-between gap-2" data-testid="map-data-status">
                <div>
                  <div className="text-xs font-semibold" style={{ color: T.muted }}>حالة بيانات الخريطة</div>
                  <div className="text-sm font-bold" style={{ color: mapDataStatus.tone === 'ok' ? '#34d399' : mapDataStatus.tone === 'warn' ? '#fbbf24' : T.ink }}>{mapDataStatus.label}</div>
                  <div className="text-[11px] mt-0.5" style={{ color: T.faint }}>{mapDataStatus.hint}</div>
                </div>
                <div className="flex items-center gap-2 text-[11px]" style={{ color: T.muted }}>
                  <span>المحرك: {GL_ENGINE ? 'MapLibre GL' : 'Leaflet'}</span>
                  {selected && <span>· الحقل: {selected.name}</span>}
                  {indicatorActive && <span>· الطبقة: {LAYER_LEGEND[indicatorActive]?.short ?? indicatorActive}</span>}
                </div>
              </div>
            </Card>

            {/* شريط الأدوات: الأساس + الطبقات + الشفّافيّة + الرسم/الدبابيس/المقارنة */}
            {mode === '2d' && (
              <Card pad={12}>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
                  {/* خريطة الأساس */}
                  <div className="flex items-center gap-2" data-testid="basemap-switcher">
                    <span className="text-xs font-semibold" style={{ color: T.muted }}>الأساس</span>
                    <LayerSwitcher layers={BASEMAPS} active={basemapId} onChange={setBasemapId} />
                  </div>

                  {/* طبقات المؤشّر (قائمة منسدلة تشمل «بلا» — كلّ مؤشّرات CDSE) */}
                  {!compare && (
                    <div className="flex items-center gap-2" data-testid="indicator-switcher">
                      <span className="text-xs font-semibold" style={{ color: T.muted }}>الطبقة</span>
                      <select
                        value={activeIndicator ?? '__none__'}
                        onChange={(e) => setActiveIndicator(e.target.value === '__none__' ? null : e.target.value)}
                        className="px-2 py-1 rounded-lg text-xs"
                        style={{ background: T.card, border: `1px solid ${T.line}`, color: T.ink }}
                        aria-label="مؤشّر الطبقة (CDSE)"
                      >
                        <option value="__none__">بلا</option>
                        {INDICATOR_LAYERS.map((l) => (
                          <option key={l.id} value={l.id}>{l.label}</option>
                        ))}
                      </select>
                    </div>
                  )}

                  {!compare && activeIndicator && availableImageryDates.length > 0 && (
                    <div className="flex items-center gap-2" data-testid="imagery-date-switcher">
                      <span className="text-xs font-semibold" style={{ color: T.muted }}>المشهد</span>
                      <select
                        value={selectedImageryDate}
                        onChange={(e) => { setSelectedImageryDate(e.target.value); setImageryTs(Date.now()); }}
                        className="px-2 py-1 rounded-lg text-xs"
                        style={{ background: T.card, border: `1px solid ${T.line}`, color: T.ink }}
                        aria-label="تاريخ صورة القمر الصناعي"
                      >
                        <option value="latest">الأحدث</option>
                        {availableImageryDates.map((d) => (
                          <option key={d.date} value={d.date}>
                            {d.date}{typeof d.cloud_pct === 'number' ? ` · غيوم ${Math.round(d.cloud_pct)}%` : ''}{d.has_cog ? ' · جاهز' : ''}
                          </option>
                        ))}
                      </select>
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

                  {/* أزرار الوضع: مقارنة / رسم / دبابيس — متاحة في كِلا المحرّكين
                      (Leaflet · MapLibre GL · المرحلة 2ب). */}
                  <div className="flex items-center gap-1.5" style={{ marginInlineStart: 'auto' }}>
                    <ToolToggle testid="btn-compare" active={compare} onClick={() => { setCompare((v) => !v); setPinMode(false); setDrawTools(false); setPivotDesigner(false); }} icon={compare ? <Columns2 className="w-3.5 h-3.5" /> : <Square className="w-3.5 h-3.5" />} label="مقارنة" />
                    {/* حصر متبادل: الرسم/القياس والدبابيس يستهلكان نقرات الخريطة معاً، فتفعيل
                        أحدهما يُعطّل الآخر (والمقارنة) — وإلّا كلّ نقرة قياس تُسقط دبّوساً بالخطأ. */}
                    <ToolToggle testid="btn-draw" active={drawTools} onClick={() => { setDrawTools((v) => !v); setPinMode(false); setCompare(false); setPivotDesigner(false); }} icon={<Ruler className="w-3.5 h-3.5" />} label="رسم/قياس" />
                    <ToolToggle testid="btn-pins" active={pinMode} onClick={() => { setPinMode((v) => !v); setCompare(false); setDrawTools(false); setPivotDesigner(false); }} icon={<Crosshair className="w-3.5 h-3.5" />} label="دبابيس" />
                    <ToolToggle testid="btn-pivot-designer" active={pivotDesigner} onClick={() => { setPivotDesigner((v) => !v); setPinMode(false); setCompare(false); setDrawTools(false); setShowPivots(true); }} icon={<Target className="w-3.5 h-3.5" />} label="تصميم Pivot" />
                  </div>
                </div>

                {/* صفّ طبقات التراكب: طقس / تنبيهات / أجهزة (مستقلّة، لا تظهر في
                    المقارنة) — متاحة في كِلا المحرّكين. */}
                {!compare && (
                  <div className="flex flex-wrap items-center gap-2 mt-3 pt-3" style={{ borderTop: `1px solid ${T.line}` }}>
                    <span className="text-xs font-semibold" style={{ color: T.muted }}>طبقات التراكب</span>
                    <ToolToggle testid="btn-weather" active={showWeather} onClick={() => setShowWeather((v) => !v)} icon={<CloudSun className="w-3.5 h-3.5" />} label="طقس/رياح" />
                    <ToolToggle testid="btn-alerts" active={showAlerts} onClick={() => setShowAlerts((v) => !v)} icon={<Bell className="w-3.5 h-3.5" />} label="تنبيهات" />
                    <ToolToggle testid="btn-devices" active={showDevices} onClick={() => setShowDevices((v) => !v)} icon={<Radio className="w-3.5 h-3.5" />} label="أجهزة" />
                    <ToolToggle testid="btn-equipment" active={showEquipment} onClick={() => setShowEquipment((v) => !v)} icon={<Tractor className="w-3.5 h-3.5" />} label="معدّات" />
                    <ToolToggle testid="btn-tasks" active={showTasks} onClick={() => setShowTasks((v) => !v)} icon={<CheckSquare className="w-3.5 h-3.5" />} label="مهام" />
                    <ToolToggle testid="btn-pivots" active={showPivots} onClick={() => setShowPivots((v) => !v)} icon={<CircleDotDashed className="w-3.5 h-3.5" />} label="محوري" />
                    {/* ملاحظات الأمانة: عناصر بلا حقل/هندسة غير قابلة للعرض — تُحتسَب لا تُختلَق */}
                    {showAlerts && alertsUnplaceable > 0 && (
                      <span className="text-[11px]" style={{ color: T.faint }}>
                        {alertsUnplaceable} تنبيه غير قابل للعرض على الخريطة (بلا حقل/هندسة)
                      </span>
                    )}
                    {showDevices && devicesUnplaceable > 0 && (
                      <span className="text-[11px]" style={{ color: T.faint }}>
                        {devicesUnplaceable} جهاز غير قابل للعرض على الخريطة (بلا حقل/هندسة)
                      </span>
                    )}
                    {showEquipment && equipmentUnplaceable > 0 && (
                      <span className="text-[11px]" style={{ color: T.faint }}>
                        {equipmentUnplaceable} معدّة غير قابلة للعرض (بلا حقل/هندسة)
                      </span>
                    )}
                    {showTasks && tasksUnplaceable > 0 && (
                      <span className="text-[11px]" style={{ color: T.faint }}>
                        {tasksUnplaceable} مهمة غير قابلة للعرض (بلا حقل/هندسة)
                      </span>
                    )}
                    {showPivots && pivotMarkers.length === 0 && (
                      <span className="text-[11px]" style={{ color: T.faint }}>
                        المحوري يظهر للحقل المختار فقط عند وجود بيانات pivot/irrigation_type
                      </span>
                    )}
                    {showWeather && !selectedPoint && (
                      <span className="text-[11px]" style={{ color: T.faint }}>
                        اختر حقلاً ذا هندسة/نقطة لعرض طبقة الطقس واتجاه الرياح كبلاطة فوق الخريطة
                      </span>
                    )}
                  </div>
                )}

                {/* صفّ الدبابيس: التصنيف + المسح (يظهر في وضع الدبابيس أو حين توجد دبابيس)
                    — متاح في كِلا المحرّكين. */}
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

                {(pivotDesigner || pivotDrafts.length > 0) && (
                  <div data-testid="pivot-designer-panel" className="mt-3 pt-3 space-y-2" style={{ borderTop: `1px solid ${T.line}` }}>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-semibold" style={{ color: T.muted }}>مصمم Pivot</span>
                      <Pill tone="info">{pivotDrafts.length} تصميم</Pill>
                      {pivotDesigner && <span className="text-[11px]" style={{ color: T.faint }}>انقر على الخريطة لاختيار مركز المحوري</span>}
                      {pivotDrafts.length > 0 && (
                        <button
                          type="button" onClick={handleClearPivotDrafts}
                          className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-lg"
                          style={{ color: T.danger, border: `1px solid ${T.line}` }}
                        >
                          <Trash2 className="w-3 h-3" /> مسح تصاميم Pivot
                        </button>
                      )}
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                      <NumberField label="نصف القطر م" value={pivotRadiusM} min={30} max={2500} step={10} onChange={setPivotRadiusM} />
                      <NumberField label="زاوية البداية" value={pivotStartAngleDeg} min={0} max={359} step={5} onChange={setPivotStartAngleDeg} />
                      <NumberField label="زاوية النهاية" value={pivotEndAngleDeg} min={0} max={360} step={5} onChange={setPivotEndAngleDeg} />
                      <NumberField label="الحلقات" value={pivotRingCount} min={1} max={24} step={1} onChange={setPivotRingCount} />
                      <NumberField label="الأذرع" value={pivotSpanCount} min={1} max={64} step={1} onChange={setPivotSpanCount} />
                    </div>
                    <div className="text-[11px]" style={{ color: pivotSummary.valid ? T.muted : T.danger }}>
                      المساحة التقريبية {pivotSummary.areaHa.toFixed(2)} هـ · القطاع {Math.round(pivotSummary.sweepDeg)}° · المحيط القوسي {Math.round(pivotSummary.circumferenceM)} م
                      {!pivotSummary.valid ? ` · مشاكل: ${pivotSummary.issues.join(', ')}` : ''}
                    </div>
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
                  left={<CompareMap fields={fields} selectedId={fieldId} basemapId={basemapId} indicatorId={leftLayer} opacity={opacity} imageryTs={imageryTs} imageryDate={selectedImageryDate === 'latest' ? null : selectedImageryDate} tenantId={tenantId} />}
                  right={<CompareMap fields={fields} selectedId={fieldId} basemapId={basemapId} indicatorId={rightLayer} opacity={opacity} imageryTs={imageryTs} imageryDate={selectedImageryDate === 'latest' ? null : selectedImageryDate} tenantId={tenantId} />}
                />
                <div className="text-[11px] mt-2" style={{ color: T.muted }}>
                  طبقتان حقيقيّتان لنفس الحقل والتاريخ المختار — للموازنة البصريّة.
                </div>
              </Card>
            ) : (
              <div style={{ position: 'relative' }}>
                {GL_ENGINE ? (
                  // محرّك MapLibre GL (WebGL) — المرحلة 2ب: تكافؤ مزايا Leaflet
                  // (رسم/قياس Terra Draw + دبابيس + تراكبات). مقسوم بالكود (lazy).
                  <Suspense fallback={<LoadingState message="جارٍ تحميل محرّك MapLibre GL…" />}>
                    <HubMapGL
                      key={`gl-${restoreKey}`}
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
                      alertMarkers={showAlerts ? alertMarkers : []}
                      deviceMarkers={showDevices ? deviceMarkers : []}
                      weatherMarker={showWeather ? weatherMarker : null}
                      operationalMarkers={operationalMarkers}
                      initialView={initialMapView}
                      onViewChange={handleViewChange}
                      imageryTs={imageryTs}
                      imageryDate={selectedImageryDate === 'latest' ? null : selectedImageryDate}
                      tenantId={tenantId}
                      pivotDesignerEnabled={pivotDesigner}
                      onAddPivotDraft={handleAddPivotDraft}
                      pivotDrafts={showPivots ? pivotDrafts : []}
                    />
                  </Suspense>
                ) : (
                  <HubMap
                    key={`leaflet-${restoreKey}`}
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
                    alertMarkers={showAlerts ? alertMarkers : []}
                    deviceMarkers={showDevices ? deviceMarkers : []}
                    weatherMarker={showWeather ? weatherMarker : null}
                    operationalMarkers={operationalMarkers}
                    initialView={initialMapView}
                    onViewChange={handleViewChange}
                    imageryTs={imageryTs}
                    imageryDate={selectedImageryDate === 'latest' ? null : selectedImageryDate}
                    tenantId={tenantId}
                    pivotDesignerEnabled={pivotDesigner}
                    onAddPivotDraft={handleAddPivotDraft}
                    pivotDrafts={showPivots ? pivotDrafts : []}
                  />
                )}
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

      {/* أداة دمج/تقسيم الحقول (CRUD حقيقيّ مُتلِف — فحص الموسم النشط مسبقاً، أمانة صارمة).
          البوّابة الأماميّة mutateAllowed؛ صلاحيّة FIELD_DELETE يفرضها الخادم (403 يُعرَض بصدق). */}
      {showSplitMerge && mutateAllowed && (
        <FieldSplitMergeTool
          fields={fields}
          selectedId={fieldId}
          onClose={() => setShowSplitMerge(false)}
          refetch={refetch}
        />
      )}

      {deleteConfirmOpen && selected && (
        <div className="fixed inset-0 z-[1200] flex items-center justify-center p-4" style={{ background: 'rgba(2,6,23,0.72)' }} role="dialog" aria-modal="true">
          <div className="w-full max-w-md rounded-2xl border p-4 shadow-2xl" style={{ background: T.card, borderColor: T.line }}>
            <div className="flex items-center gap-2 text-base font-bold" style={{ color: '#fecaca' }}>
              <Trash2 className="w-5 h-5" /> تأكيد حذف الحقل
            </div>
            <p className="mt-3 text-sm leading-6" style={{ color: T.ink }}>
              سيتم حذف الحقل <strong>{selected.name}</strong>. هذا الإجراء لا يمكن التراجع عنه من الواجهة.
            </p>
            <p className="mt-2 text-xs" style={{ color: T.faint }}>
              يرفض الخادم الحذف إذا كان الحقل مرتبطاً بموسم نشط أو لا تملك الصلاحية المناسبة.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" onClick={() => setDeleteConfirmOpen(false)} className="rounded-lg px-3 py-2 text-xs font-semibold" style={{ background: T.card2, color: T.ink, border: `1px solid ${T.line}` }}>
                إلغاء
              </button>
              <button type="button" data-testid="confirm-delete-field" disabled={deleteBusy} onClick={handleDeleteSelectedField} className="inline-flex items-center gap-1 rounded-lg px-3 py-2 text-xs font-semibold" style={{ background: deleteBusy ? '#475569' : '#dc2626', color: '#fff' }}>
                <Trash2 className="w-3.5 h-3.5" /> {deleteBusy ? 'جارٍ الحذف…' : 'حذف نهائي'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


function NumberField({ label, value, min, max, step, onChange }: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="text-[11px] font-semibold" style={{ color: T.muted }}>
      <span className="block mb-1">{label}</span>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => {
          const next = Number(e.target.value);
          if (Number.isFinite(next)) onChange(Math.max(min, Math.min(max, next)));
        }}
        className="w-full rounded-lg px-2 py-1 text-xs"
        style={{ background: T.card, border: `1px solid ${T.line}`, color: T.ink }}
      />
    </label>
  );
}

function SummaryStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border px-3 py-2" style={{ background: T.card, borderColor: T.line }}>
      <div className="text-[11px]" style={{ color: T.faint }}>{label}</div>
      <div className="mt-1 text-sm font-bold" style={{ color: T.ink }}>{value}</div>
    </div>
  );
}

// زرّ تبديل أداة (مقارنة/رسم/دبابيس) — موحّد الشكل.
function ToolToggle({ active, onClick, icon, label, testid }: { active: boolean; onClick: () => void; icon: React.ReactNode; label: string; testid?: string }) {
  return (
    <button
      type="button" onClick={onClick} data-testid={testid}
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
  fields, selectedId, basemapId, indicatorId, opacity, imageryTs, imageryDate, tenantId,
}: {
  fields: ReturnType<typeof useSelectedField>['options'];
  selectedId: string; basemapId: string; indicatorId: string; opacity: number; imageryTs?: number; imageryDate?: string | null; tenantId?: string | null;
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
        imageryTs={imageryTs ?? 0}
        imageryDate={imageryDate ?? null}
        tenantId={tenantId ?? null}
      />
      {legend && (
        <div style={{ position: 'absolute', insetInlineStart: 8, bottom: 8, zIndex: 600, pointerEvents: 'none' }}>
          <ColormapLegend cmap={cmap} title={legend.short} lowLabel={legend.low} highLabel={legend.high} />
        </div>
      )}
    </div>
  );
}
