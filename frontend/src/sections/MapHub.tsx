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
//   • رسم/قياس (turf) + دبابيس استكشاف دائمة (v94 — تُجلَب/تُحفَظ على الخادم، RLS).
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
  Search as SearchIcon, Trash2, Combine, Download, Upload,
  History, RotateCcw, Target,
  Satellite,
} from 'lucide-react';
import { useLocation } from 'react-router';
import { buildProject, downloadProject, parseProjectFile, type SahoolMapView } from '../lib/projectFile';
import { loadWorkspace, saveWorkspace } from '../lib/workspaceStorage';
import { MAP_ENGINE } from '../lib/featureFlags';
import { useSelectedField } from '../hooks/useSelectedField';
import { useFieldDetail, useAlerts, useDevices, useWeatherForecast, useEquipment, useTasks, useCurrentNDVI, useFieldSoilMoisture, useSoilNRecommendation, useFieldPrescriptions, useFieldPhenology, useFieldStageActions, useFieldWaterEfficiency, useSeasons, useFarmLedgerSummary, useSeasonProfitability, useSeasonVariance, useSeasonEconomicState } from '../hooks/useApi';
import { fieldRepresentativePoint, geomToPolygon } from '../lib/geo';
import { kongApi, rasterApi, asApiError, apiErrorMessage, refreshFieldImagery, fetchFieldImageryAvailableDates, runHistoricalImageryBackfill, fetchHistoricalImageryBackfillStatus, isTerminalBackfillStatus, fieldCdseThumbnailUrl, cdseClipParams, fetchTerrainTileJson, fetchFieldContours, hillshadeTileUrl, slopeTileUrl, fetchSoilTileJson, soilTileUrl, fetchSoilSamplingPlan, type FieldImageryDateOption, type TerrainTileJson, type FieldContours, type SoilProperty, type SoilTileJson } from '../services/api';
import { toastStore } from '../services/websocket';
import { useAuthStore, UNAUTH_TENANT_KEY } from '../hooks/useAuth';
import { canMutate } from '../lib/permissions';
import { availableBasemapLayers, layersOfKind } from '../lib/layerRegistry';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';
import AddFieldWithMap from '../components/AddFieldWithMap';
import FieldViewInsightStrip from '../components/fieldview/FieldViewInsightStrip';
import FieldHealthReportCard from '../components/fieldview/FieldHealthReportCard';
import FarmerMetricsCard from '../components/fieldview/FarmerMetricsCard';
import ZoneVraEntryCard from '../components/fieldview/ZoneVraEntryCard';
import FieldEconomicsCard from '../components/fieldview/FieldEconomicsCard';
import OperationsCenterCard from '../components/fieldview/OperationsCenterCard';
import FieldWaterBrainCard from '../components/fieldview/FieldWaterBrainCard';
import FieldScoutingCard from '../components/fieldview/FieldScoutingCard';
import SeasonCommandCard from '../components/fieldview/SeasonCommandCard';
import TraceabilityCard from '../components/fieldview/TraceabilityCard';
import FieldObjectivePanel from '../components/fieldview/FieldObjectivePanel';
import SeasonProfitabilityCard from '../components/fieldview/SeasonProfitabilityCard';
import CropKnowledgeCard from '../components/fieldview/CropKnowledgeCard';
import HarvestTraceabilityCard from '../components/fieldview/HarvestTraceabilityCard';
import BoundaryReviewCard from '../components/fieldview/BoundaryReviewCard';
import FieldIntelligenceCardView from '../components/fieldview/FieldIntelligenceCardView';
import WindbreakCard from '../components/fieldview/WindbreakCard';
import DriftRiskCard from '../components/fieldview/DriftRiskCard';
import EvidenceGraphCard from '../components/fieldview/EvidenceGraphCard';
import EvidenceHistoryCard from '../components/fieldview/EvidenceHistoryCard';
import SeasonEvidenceCard from '../components/fieldview/SeasonEvidenceCard';
import YemeniCalendarCard from '../components/fieldview/YemeniCalendarCard';
import PlantingAdvisorCard from '../components/fieldview/PlantingAdvisorCard';
import LedgerEntryCard from '../components/fieldview/LedgerEntryCard';
import AgroKnowledgeCard from '../components/fieldview/AgroKnowledgeCard';
import AgroCalculatorsCard from '../components/fieldview/AgroCalculatorsCard';
import DiagnosticsCard from '../components/fieldview/DiagnosticsCard';
import SoilGovernanceCard from '../components/fieldview/SoilGovernanceCard';
import MpcGovernanceCard from '../components/fieldview/MpcGovernanceCard';
import WhatIfScenariosCard from '../components/fieldview/WhatIfScenariosCard';
import WaterHarvestingCard from '../components/fieldview/WaterHarvestingCard';
import IrrigationDecisionAidsCard from '../components/fieldview/IrrigationDecisionAidsCard';
import IrrigationDecisionCard from '../components/fieldview/IrrigationDecisionCard';
import CropSafetyKnowledgeCard from '../components/fieldview/CropSafetyKnowledgeCard';
import AgroAnalyticsCard from '../components/fieldview/AgroAnalyticsCard';
import WaterFieldOpsCard from '../components/fieldview/WaterFieldOpsCard';
import SpecialtyCropsCard from '../components/fieldview/SpecialtyCropsCard';
import DistrictsWeatherCard from '../components/fieldview/DistrictsWeatherCard';
import AgronomyConsistencyCard from '../components/fieldview/AgronomyConsistencyCard';
import CropPropagationCard from '../components/fieldview/CropPropagationCard';
import GisTemporalOpsCard from '../components/fieldview/GisTemporalOpsCard';
import LearningEvidenceCard from '../components/fieldview/LearningEvidenceCard';
import ClimateRiskCard from '../components/fieldview/ClimateRiskCard';
import type { EvidenceAvailability } from '../lib/fieldObjectiveEngine';
import { useCropScoutingIssues, useScoutingPins, useCreateScoutingPin } from '../hooks/useScouting';
import type { ScoutingPinRecord } from '../hooks/useScouting';
import { buildComparePresets } from '../lib/layerComparePresets';
import { saveFieldMapView, markDefaultViewOnce } from '../lib/fieldMapView';
import {
  T, RADIUS, Card, Pill, Badge, SectionLabel,
  LayerSwitcher, ColormapLegend, SideBySide, type CmapId,
} from '../components/ds';
import { MapIndicatorLegend } from '../components/insights/MapIndicatorLegend';
import { MapHubShell } from './maphub/MapHubShell';
import { MapHubToolToggle } from './maphub/MapHubToolToggle';
import { OperationalOverlayControls } from './maphub/OperationalOverlayControls';
import { MapCanvasBoundary } from './maphub/MapCanvasBoundary';
import { FieldContextStrip } from './maphub/FieldContextStrip';
import { PriorityQueuePanel } from './maphub/PriorityQueuePanel';
import { FieldDrawerShell } from './maphub/FieldDrawerShell';
import { FieldTimelineShell } from './maphub/FieldTimelineShell';
import { MapActionPalette } from './maphub/MapActionPalette';
import { RoleAwareMapSurface } from './maphub/RoleAwareMapSurface';
import {
  isOperationalOverlayBlocked,
  mapClutterBlockedTitle,
  type OperationalOverlayId,
  type OperationalOverlayState,
} from './maphub/mapClutterControl';

// نطاقات المؤشّرات (vmin/vmax/invert) — مرآة لـ_INDEX_DOMAIN في raster-service
// (tile_render.py) كي تتطابق أسطورة المقياس مع التصيير الفعليّ. مجهول ⇒ افتراضيّ NDVI.
const INDEX_DOMAIN: Record<string, [number, number, boolean]> = {
  ndvi: [-0.2, 0.9, false], evi: [-0.2, 0.9, false], ndmi: [-0.3, 0.6, false],
  ndwi: [-0.5, 0.5, false], ndsi: [-0.1, 0.6, true], salinity: [-0.1, 0.6, true],
  ndre: [-0.1, 0.6, false], msavi: [-0.2, 0.9, false], moisture: [-0.3, 0.6, false],
  savi: [-0.2, 0.9, false], gndvi: [-0.2, 0.9, false], msi: [0.4, 1.6, true],
};
import HubMap, {
  type ScoutPin, type AlertMarker, type DeviceMarker, type WeatherMarker, type OperationalMarker,
} from '../components/maphub/HubMap';
import FieldDetailDrawer from '../components/maphub/FieldDetailDrawer';
import FieldSplitMergeTool from '../components/maphub/FieldSplitMergeTool';
import SceneProvenanceCard from '../components/maphub/SceneProvenanceCard';
import type { DrawFeature } from '../components/maphub/drawing';
import { buildPivotDrawFeature, summarizePivotDesign, createDrawingFeatureOfflineFirst as createDrawingFeature, listDrawingFeaturesWithOfflineQueue as listDrawingFeatures, buildAgriculturalZoneFeature, normalizeFieldGeometryForZone, type AgriculturalZoneKind, type PersistedDrawFeature } from '../components/maphub/drawing';

// العرض ثلاثيّ الأبعاد مقسوم بالكود — لا يُحمَّل إلا عند تفعيل وضع التضاريس،
// فلا يُثقِل الحزمة الأساسيّة (يحوي مستقبلاً maplibre-gl الثقيل).
const TerrainView3D = lazy(() => import('../components/maphub/TerrainView3D'));

// محرّك MapLibre GL (WebGL) — إثبات مفهوم المرحلة 2 خلف عَلَم MAP_ENGINE. مقسوم
// بالكود (lazy) فلا يُحمَّل maplibre-gl الثقيل (~250KB) إلا عند تفعيل العَلَم.
const HubMapGL = lazy(() => import('../components/maphub/HubMapGL'));

// هل محرّك MapLibre مُفعَّل؟ (الافتراض leaflet). المرحلة 2ب: الرسم/القياس (Terra
// Draw) والدبابيس والتراكبات متاحة في كِلا المحرّكين (تكافؤ المزايا).
const GL_ENGINE = MAP_ENGINE === 'maplibre';


function idempotencyConfig(source: Record<string, unknown> | null | undefined) {
  const key = source?.idempotency_key;
  return key ? { headers: { 'Idempotency-Key': String(key) } } : undefined;
}

function withoutIdempotency<T extends Record<string, unknown>>(source: T): Omit<T, 'idempotency_key'> {
  const { idempotency_key: _idempotencyKey, ...body } = source;
  return body;
}

// ── الطبقات القابلة للعرض كبلاطات مؤشّر (raster) — من السجلّ ──
// كلّ المؤشّرات التي يحسبها raster-service (CDSE INDEX_EXPR) مع لوحة DS موجودة.
// ('moisture' المكافئ لـNDMI مُستثنى تفادياً للتكرار.)
const RAW_IMAGERY_INDEX_ID = 'truecolor';
const CORE_TIMELINE_THUMBNAIL_INDEX_IDS = new Set([
  RAW_IMAGERY_INDEX_ID, 'ndvi', 'ndre', 'ndmi', 'msavi', 'ndwi', 'salinity',
]);

const ADVANCED_ANALYSIS_INDEX_IDS = new Set([
  'evi', 'savi', 'gndvi', 'msi', 'reci', 'gci', 'arvi', 'sipi', 'nbr', 'ccci', 'vari', 'gli', 'bsi',
]);

const RASTER_INDEX_IDS = new Set([
  ...CORE_TIMELINE_THUMBNAIL_INDEX_IDS,
  ...ADVANCED_ANALYSIS_INDEX_IDS,
]);
const INDICATOR_LAYERS = layersOfKind('index')
  .filter((l) => RASTER_INDEX_IDS.has(l.id))
  .map((l) => ({ id: l.id, label: l.labelAr, cmap: (l.colormap ?? 'ndvi') as CmapId }));

// خرائط الأساس من السجلّ (kind:'basemap').
const BASEMAPS = availableBasemapLayers(import.meta.env as Record<string, string | undefined>)
  .map((b) => ({ id: b.id, label: b.labelAr }));

// تسمية مختصرة + حدّا المفتاح للطبقة (عرض ColormapLegend).
const LAYER_LEGEND: Record<string, { short: string; low: string; high: string }> = {
  truecolor: { short: 'TrueColor', low: 'صورة خام', high: 'ألوان طبيعية' },
  ndvi: { short: 'NDVI', low: 'إجهاد', high: 'كثيف' },
  ndmi: { short: 'NDMI', low: 'جافّ', high: 'رطب' },
  salinity: { short: 'الملوحة', low: 'منخفضة', high: 'مرتفعة' },
  evi: { short: 'EVI', low: 'إجهاد', high: 'كثيف' },
  savi: { short: 'SAVI', low: 'إجهاد', high: 'كثيف' },
  msavi: { short: 'MSAVI', low: 'إجهاد', high: 'كثيف' },
  ndwi: { short: 'NDWI', low: 'جافّ', high: 'مياه' },
  gndvi: { short: 'GNDVI', low: 'منخفض', high: 'مرتفع' },
  ndre: { short: 'NDRE', low: 'منخفض', high: 'مرتفع' },
  reci: { short: 'RECI', low: 'منخفض', high: 'كلوروفيل' },
  gci: { short: 'GCI', low: 'منخفض', high: 'كلوروفيل' },
  arvi: { short: 'ARVI', low: 'إجهاد', high: 'كثيف' },
  sipi: { short: 'SIPI', low: 'منخفض', high: 'صبغات' },
  nbr: { short: 'NBR', low: 'منخفض', high: 'مرتفع' },
  ccci: { short: 'CCCI', low: 'منخفض', high: 'كلوروفيل' },
  vari: { short: 'VARI', low: 'منخفض', high: 'أخضر' },
  gli: { short: 'GLI', low: 'منخفض', high: 'أخضر' },
  bsi: { short: 'BSI', low: 'غطاء', high: 'تربة عارية' },
  msi: { short: 'MSI', low: 'رطب', high: 'إجهاد' },
};


function normalizeDateOnly(value: string | null | undefined): string {
  return String(value ?? '').slice(0, 10);
}

function parseDateMs(value: string | null | undefined): number | null {
  const date = normalizeDateOnly(value);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return null;
  const ms = Date.parse(`${date}T00:00:00Z`);
  return Number.isFinite(ms) ? ms : null;
}

function cloudBandColor(value: number | null | undefined): string {
  if (typeof value !== 'number') return '#64748b';
  if (value <= 10) return '#16a34a';
  if (value <= 25) return '#84cc16';
  if (value <= 45) return '#f59e0b';
  return '#dc2626';
}


type TrueColorRuntimeStatus = {
  state: 'idle' | 'checking' | 'ready' | 'unavailable' | 'error';
  message: string;
  endpoint?: string;
};

const TRUECOLOR_UNAVAILABLE_MESSAGE = 'الصورة الخام غير جاهزة من raster-service — شغّل تجهيز 3/6/12/24 شهر أو تحقّق من إعدادات CDSE.';

function summarizeTwoYearTimeline(dates: FieldImageryDateOption[]): { items: FieldImageryDateOption[]; ready: number; pending: number; avgCloud: number | null } {
  const byDate = new Map<string, FieldImageryDateOption>();
  for (const raw of dates) {
    const date = normalizeDateOnly(raw.date);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) continue;
    const prev = byDate.get(date);
    if (!prev) {
      byDate.set(date, { ...raw, date, indices: raw.indices ? [...new Set(raw.indices)] : undefined });
      continue;
    }
    byDate.set(date, {
      ...prev,
      has_cog: Boolean(prev.has_cog || raw.has_cog),
      cloud_pct: typeof prev.cloud_pct === 'number' ? prev.cloud_pct : raw.cloud_pct,
      cloud_cover: typeof prev.cloud_cover === 'number' ? prev.cloud_cover : raw.cloud_cover,
      scene_id: prev.scene_id ?? raw.scene_id ?? null,
      indices: [...new Set([...(prev.indices ?? []), ...(raw.indices ?? [])])],
    });
  }
  const valid = [...byDate.values()]
    .map((item) => ({ item, ms: parseDateMs(item.date) }))
    .filter((entry): entry is { item: FieldImageryDateOption; ms: number } => entry.ms != null)
    .sort((a, b) => b.ms - a.ms);
  // العرض البصري لا يقتصر على «آخر تاريخ/يوليو»؛ يعرض كل التواريخ الجاهزة التي
  // أرجعها الخادم حتى حدّ السنتين/الـlimit. الخادم يحدّد النطاق الزمني الفعلي.
  const items = valid.map((entry) => entry.item);
  const ready = items.filter((item) => item.has_cog).length;
  const pending = Math.max(0, items.length - ready);
  const cloudValues = items
    .map((item) => typeof item.cloud_pct === 'number' ? item.cloud_pct : (typeof item.cloud_cover === 'number' ? item.cloud_cover : null))
    .filter((value): value is number => value != null);
  const avgCloud = cloudValues.length ? cloudValues.reduce((a, b) => a + b, 0) / cloudValues.length : null;
  return { items, ready, pending, avgCloud };
}

const BACKFILL_MONTH_OPTIONS = [3, 6, 12, 24] as const;

function monthLabel(date: string): string {
  const d = normalizeDateOnly(date);
  return /^\d{4}-\d{2}-\d{2}$/.test(d) ? `${d.slice(0, 4)}-${d.slice(5, 7)}` : '—';
}

const PIN_CATEGORIES = ['آفة', 'مرض', 'نقص تغذية', 'إجهاد مائيّ', 'عشب ضارّ', 'أخرى'];

// ── طبقة التربة (SoilGrids) — الخصائص الثمانية المدعومة + أعماقها (عقد raster-service) ──
// التسميات العربيّة للقوائم المنسدلة (name_ar الرسميّ من الخادم يُعرَض للطبقة النشطة عبر
// tilejson.name_ar). الأعماق مطابقة لعقد الخادم؛ الافتراضيّ 0-5cm.
const SOIL_PROPERTIES: { key: SoilProperty; label: string }[] = [
  { key: 'phh2o', label: 'الحموضة (pH)' },
  { key: 'clay', label: 'الطين (Clay)' },
  { key: 'sand', label: 'الرمل (Sand)' },
  { key: 'silt', label: 'الطمي (Silt)' },
  { key: 'soc', label: 'الكربون العضويّ (SOC)' },
  { key: 'cec', label: 'السعة التبادليّة (CEC)' },
  { key: 'nitrogen', label: 'النيتروجين (Nitrogen)' },
  { key: 'bdod', label: 'الكثافة الظاهريّة (BDOD)' },
];
const SOIL_DEPTHS = ['0-5cm', '5-15cm', '15-30cm', '30-60cm', '60-100cm', '100-200cm'];

type MapHubLocationState = {
  fieldId?: string;
  openCdse?: boolean;
  indicator?: string;
  from?: string;
  showWeather?: boolean;
};

function MapHubCore() {
  const location = useLocation();
  const initialSearch = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const routeState = (location.state ?? {}) as MapHubLocationState;
  const routeFieldId = routeState.fieldId ?? initialSearch.get('field_id') ?? initialSearch.get('fieldId') ?? undefined;
  const {
    options: fields,
    isLoading,
    isError,
    refetch,
    fieldId,
    setFieldId,
    routeFieldIsInvalid,
    storedFieldIsInvalid,
    selectionReason,
  } = useSelectedField({ routeFieldId });
  const { user, tenantId } = useAuthStore();
  const mutateAllowed = canMutate(user?.role);

  const detailQ = useFieldDetail(fieldId || undefined);

  // ── حالة العرض (تُستعاد تلقائيّاً من localStorage — «العودة لنفس البيئة») ──────
  const savedWorkspace = useMemo(() => loadWorkspace(), []);
  const [mode, setMode] = useState<'2d' | '3d'>(savedWorkspace?.mode === '3d' ? '3d' : '2d');
  const [basemapId, setBasemapId] = useState<string>(savedWorkspace?.basemapId ?? (BASEMAPS[0]?.id ?? 'satellite'));
  const routeIndicator = routeState.indicator ?? initialSearch.get('index') ?? initialSearch.get('indicator') ?? undefined;
  const requestedCdseOpen = routeState.openCdse === true || initialSearch.get('source') === 'my-fields' || !!routeIndicator;
  // الطقس لا يُفتَح افتراضيّاً عند فتح حقل من «حقولي» — الافتراضيّ صورة القمر
  // الصناعيّ (CDSE/NDVI) مع أسطورتها. يُفتَح الطقس فقط بطلب صريح (weather=1/state).
  const requestedWeatherOpen = routeState.showWeather === true
    || initialSearch.get('weather') === '1'
    || initialSearch.get('weather') === 'true';
  // فتح «حقل جديد» عبر رابط عميق (من شاشة «حقولي») — زرّ الإنشاء انتقل إلى حقولي.
  const requestedAddOpen = initialSearch.get('add') === '1';
  // الافتراضيّ عند فتح حقل: صورة الحقل الخام TrueColor من raster-service داخل حدود الحقل.
  // المؤشرات NDVI/NDMI… overlays تفسيرية تُختار فوقها، والطقس لا يُفتح إلا صراحةً.
  const [activeIndicator, setActiveIndicator] = useState<string | null>(
    requestedCdseOpen ? (routeIndicator ?? RAW_IMAGERY_INDEX_ID) : (savedWorkspace?.activeIndicator ?? RAW_IMAGERY_INDEX_ID),
  );
  const [imageryTs, setImageryTs] = useState(0); // cache-bust للبلاطات بعد معالجة Sentinel/COG
  const [selectedImageryDate, setSelectedImageryDate] = useState<string>('latest');
  const [availableImageryDates, setAvailableImageryDates] = useState<FieldImageryDateOption[]>([]);
  const [timelineImageryDates, setTimelineImageryDates] = useState<FieldImageryDateOption[]>([]);
  // نافذة شريط الصور التاريخيّ (بالأشهر). تُقاد بزرّ الفترة المختار (3/6/12/24) — فبدل
  // سحب 24 شهراً دائماً، يعرض الشريط تواريخ المزوّد ضمن الفترة المطلوبة فقط.
  const [timelineMonths, setTimelineMonths] = useState<number>(24);
  const [trueColorRuntime, setTrueColorRuntime] = useState<TrueColorRuntimeStatus>({ state: 'idle', message: 'لم يتم اختيار حقل بعد.' });
  const [historicalBackfillBusy, setHistoricalBackfillBusy] = useState(false);
  const [historicalBackfillStatus, setHistoricalBackfillStatus] = useState<string | null>(null);
  const fieldViewStatus = routeFieldIsInvalid
    ? 'الرابط يشير إلى حقل غير متاح لهذا المستخدم؛ تم استخدام الحقل النشط المتاح.'
    : storedFieldIsInvalid
      ? 'الحقل المحفوظ لم يعد متاحاً؛ تم اختيار حقل متاح تلقائياً.'
      : selectionReason === 'route'
        ? 'تم فتح الحقل من رابط FieldView مباشر.'
        : null;
  const [showImageryTimeline, setShowImageryTimeline] = useState(false);
  const [opacity, setOpacity] = useState(savedWorkspace?.opacity ?? 0.75);
  const [compare, setCompare] = useState(savedWorkspace?.compare ?? false);
  const [leftLayer, setLeftLayer] = useState<string>(savedWorkspace?.leftLayer ?? (INDICATOR_LAYERS[0]?.id ?? 'ndvi'));
  const [rightLayer, setRightLayer] = useState<string>(savedWorkspace?.rightLayer ?? (INDICATOR_LAYERS[1]?.id ?? 'ndmi'));
  // نمط المقارنة: «مؤشّران» (الافتراض، مؤشّرَان مختلفان في نفس التاريخ) أو «تاريخان»
  // (نفس المؤشّر بين تاريخَين مخزَّنَين — مقارنة زمنيّة حقيقيّة). التاريخ الأيمن للنمط الثاني.
  const [compareMode, setCompareMode] = useState<'indicators' | 'dates'>('indicators');
  const [compareRightDate, setCompareRightDate] = useState<string>('latest');
  const [drawTools, setDrawTools] = useState(savedWorkspace?.drawTools ?? false);
  const [pinMode, setPinMode] = useState(savedWorkspace?.pinMode ?? false);
  // ── طبقات التراكب (مستقلّة؛ تُستعاد من المخزن) ──────────
  const [showWeather, setShowWeather] = useState(requestedWeatherOpen); // لا نستعيد الطقس من workspace كي لا يصبح افتراضياً
  const [showAlerts, setShowAlerts] = useState(savedWorkspace?.showAlerts ?? false);
  const [showDevices, setShowDevices] = useState(savedWorkspace?.showDevices ?? false);
  const [showEquipment, setShowEquipment] = useState(false);
  const [showTasks, setShowTasks] = useState(false);
  // ── طبقات التضاريس (DEM حقيقيّ من raster-service) — ثلاثة مبدّلات مستقلّة ──────
  // صدق صارم: البلاطات/الكنتور تُعرَض فقط حين available/computed؛ وإلّا نُظهر
  // رسالة user_message من الخادم (لا اختراع تضاريس). لا تُستعاد من workspace (افتراضيّ مُطفأ).
  const [showHillshade, setShowHillshade] = useState(false);
  const [showSlope, setShowSlope] = useState(false);
  const [showContours, setShowContours] = useState(false);
  const [hillshadeTj, setHillshadeTj] = useState<TerrainTileJson | null>(null);
  const [slopeTj, setSlopeTj] = useState<TerrainTileJson | null>(null);
  const [contoursData, setContoursData] = useState<FieldContours | null>(null);
  const [contoursNote, setContoursNote] = useState<string | null>(null);
  // ── طبقة التربة (SoilGrids) — تقدير عالميّ (~250م) لإرشاد أخذ العيّنات فقط ──────
  // صدق صارم: البلاطة تُعرَض فقط حين available:true؛ وإلّا نُظهر user_message من الخادم
  // (لا اختراع قيم تربة). الـdisclaimer يُعرَض دوماً حين المبدّل مفعّل. لا تُستعاد من
  // workspace (افتراضيّ مُطفأ). الافتراضيّ عمق 0-5cm وخاصّيّة الحموضة (phh2o).
  const [showSoil, setShowSoil] = useState(false);
  const [soilProperty, setSoilProperty] = useState<SoilProperty>('phh2o');
  const [soilDepth, setSoilDepth] = useState<string>(SOIL_DEPTHS[0]);
  const [soilTj, setSoilTj] = useState<SoilTileJson | null>(null);
  // ── نقاط أخذ العيّنات المقترَحة (🧪) — طبقة مستقلّة عن بلاطة التربة. لا تُستعاد من
  // workspace (افتراضيّ مُطفأ). تُجلَب من fetchSoilSamplingPlan للحقل المختار بـbbox
  // حدوده؛ computed:false/فارغ ⇒ لا نقاط + ملاحظة صادقة (لا اختراع نقاط).
  const [showSoilSamples, setShowSoilSamples] = useState(false);
  const [soilSamplePoints, setSoilSamplePoints] = useState<Array<{ id: string; lat: number; lng: number; label: string; reason?: string }>>([]);
  const [soilSamplesBusy, setSoilSamplesBusy] = useState(false);
  const [soilSamplesNote, setSoilSamplesNote] = useState<string | null>(null);
  // OneSoil-style وضع FieldView: «فلاح» (ملخّص أساسيّ) أو «خبير» (كلّ الأدوات).
  // يُحفَظ محلّيّاً — لا يلمس نوع لقطة مساحة العمل. الافتراضيّ فلاح (بساطة أوّلاً).
  const [fieldMode, setFieldMode] = useState<'farmer' | 'expert'>(() => {
    try { return localStorage.getItem('sahool:fieldview:mode') === 'expert' ? 'expert' : 'farmer'; } catch { return 'farmer'; }
  });
  const setFieldModePersist = useCallback((m: 'farmer' | 'expert') => {
    setFieldMode(m);
    try { localStorage.setItem('sahool:fieldview:mode', m); } catch { /* تجاهُل حظر التخزين */ }
  }, []);
  const [showPivots, setShowPivots] = useState(false);
  const [pivotDesigner, setPivotDesigner] = useState(false);
  const [pivotRadiusM, setPivotRadiusM] = useState(400);
  const [pivotStartAngleDeg, setPivotStartAngleDeg] = useState(0);
  const [pivotEndAngleDeg, setPivotEndAngleDeg] = useState(360);
  const [pivotRingCount, setPivotRingCount] = useState(4);
  const [pivotSpanCount, setPivotSpanCount] = useState(8);
  const [pivotDrafts, setPivotDrafts] = useState<DrawFeature[]>([]);
  const [pivotPersisted, setPivotPersisted] = useState<PersistedDrawFeature[]>([]);
  const [zonePersisted, setZonePersisted] = useState<PersistedDrawFeature[]>([]);
  const [zoneDesigner, setZoneDesigner] = useState(false);
  const [zoneKind, setZoneKind] = useState<AgriculturalZoneKind>('management-zone');
  const [zoneRate, setZoneRate] = useState(120);
  const [zoneRateUnit, setZoneRateUnit] = useState('kg/ha');
  const [zoneSyncBusy, setZoneSyncBusy] = useState(false);
  const [pivotSyncBusy, setPivotSyncBusy] = useState(false);
  // دبابيس الاستكشاف الدائمة (v94): تُجلَب من الخادم وتُحفَظ (RLS، معزولة بالمستأجِر)
  // فتبقى عبر الجلسات والأجهزة — لا حالة جلسة محلّيّة. نمط SatellitePage: مُخزَّنة من
  // الخادم + تفاؤليّة محلّيّة تُدمَج بلا تكرار حتى تظهر من إعادة الجلب. صدق: القاعدة غير
  // مفعّلة ⇒ pins:[] + note_ar (لا اختراع مشاهدات).
  const scoutingPinsQ = useScoutingPins(fieldId);
  const createScoutPin = useCreateScoutingPin(fieldId);
  const [optimisticPins, setOptimisticPins] = useState<ScoutPin[]>([]);
  useEffect(() => { setOptimisticPins([]); }, [fieldId]);
  const serverPins = useMemo<ScoutPin[]>(
    () => (scoutingPinsQ.data?.pins ?? []).map((r: ScoutingPinRecord) => ({
      id: r.pin_id, lat: r.lat, lng: r.lng, note: r.note_ar ?? '', category: r.issue_category,
    })),
    [scoutingPinsQ.data],
  );
  const pins = useMemo<ScoutPin[]>(() => {
    const ids = new Set(serverPins.map((p) => p.id));
    return [...serverPins, ...optimisticPins.filter((p) => !ids.has(p.id))];
  }, [serverPins, optimisticPins]);
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
  // Token يلغي polling الخلفيّ عند تغيير الحقل أو تفكيك المكوّن؛ يمنع تحديث Timeline لحقل قديم.
  const backfillPollTokenRef = useRef(0);
  const twoYearTimeline = useMemo(() => summarizeTwoYearTimeline(timelineImageryDates), [timelineImageryDates]);
  const dateSelectorDates = availableImageryDates.length > 0 ? availableImageryDates : timelineImageryDates;

  useEffect(() => {
    return () => { backfillPollTokenRef.current += 1; };
  }, []);

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
      setTimelineImageryDates([]);
      setSelectedImageryDate('latest');
      return;
    }
    let cancelled = false;
    // FINDING-006: نمرّر المؤشّر النشط كي يقصر الخادم التواريخ على ما له COG لهذا
    // المؤشّر تحديداً — فلا يُعرَض تاريخ «جاهز» لمؤشّر آخر فتظهر بلاطة شفّافة عند اختياره.
    const idx = activeIndicator && activeIndicator !== RAW_IMAGERY_INDEX_ID ? activeIndicator : undefined;
    Promise.all([
      fetchFieldImageryAvailableDates(fieldId, idx, 240),
      // TIMELINE-PROVIDER-DATES (طلب المستخدم 2026-07-12): شريط الصور التاريخيّ يعرض
      // محور الالتقاط الحقيقيّ كاملاً حسب الطبقة المختارة — الجاهز لهذا المؤشّر يحمل
      // صورته، وتواريخ المزوّد غير المعالَجة تظهر بتاريخها «ينتظر COG» بلا صورة.
      fetchFieldImageryAvailableDates(fieldId, idx, 240, { includeProvider: true, months: timelineMonths }),
    ])
      .then(([dates, allDates]) => {
        if (cancelled) return;
        // تصفية دفاعيّة على العميل أيضاً: أبقِ التواريخ التي تملك المؤشّر النشط فعليّاً
        // (أو التي لا تحمل قائمة indices — لا نُخفي بلا دليل من الخادم).
        const filtered = idx
          ? dates.filter((d) => !d.indices || d.indices.length === 0 || d.indices.includes(idx))
          : dates;
        const sorted = [...filtered].sort((a, b) => b.date.localeCompare(a.date));
        const timelineSorted = [...(allDates.length ? allDates : filtered)].sort((a, b) => b.date.localeCompare(a.date));
        setAvailableImageryDates(sorted);
        setTimelineImageryDates(timelineSorted);
        setSelectedImageryDate((prev) => {
          if (prev === 'latest') return prev;
          return timelineSorted.some((d) => d.date === prev) ? prev : 'latest';
        });
      })
      .catch(() => {
        if (!cancelled) {
          setAvailableImageryDates([]);
          setTimelineImageryDates([]);
        }
      });
    return () => { cancelled = true; };
  }, [fieldId, mode, activeIndicator, timelineMonths]);

  // عند اختيار مؤشّر وحقل، نطلب معالجة/تحديث صور Sentinel ثم نكسر كاش البلاطات.
  // هذا لا يصنع قيماً وهمية: إذا لم تنتج الخلفية COG حقيقي، ستظل البلاطات شفافة.
  useEffect(() => {
    if (!fieldId || !activeIndicator || mode !== '2d') return;
    const key = `${tenantId ?? UNAUTH_TENANT_KEY}:${fieldId}:${activeIndicator}:${selectedImageryDate}`;
    if (imageryRefreshKeyRef.current === key) return;
    // FINDING-007 + v8-F5: مجرّد اختيار تاريخ لا يُطلق معالجة صامتة (توليد COG جديد
    // كأثر جانبيّ للاختيار). القاعدة:
    //   • «latest» فقط ⇒ نطلب تحديثاً (نضمن أحدث مشهد) — فعلٌ ضمنيّ مقبول.
    //   • تاريخ محدَّد جاهز (has_cog) ⇒ نبدّل الطبقة فقط (bump imageryTs، لا معالجة).
    //   • تاريخ محدَّد غير جاهز ⇒ **لا** نُطلق معالجة تلقائيّاً؛ نعيد القراءة (تظهر
    //     «غير متاح» بصدق) ونُبلّغ المستخدم أنّ التجهيز صريح (زرّ backfill التاريخيّ).
    imageryRefreshKeyRef.current = key;
    if (selectedImageryDate !== 'latest') {
      const readyOption = availableImageryDates.find((d) => d.date === selectedImageryDate);
      setImageryTs(Date.now());
      if (!readyOption?.has_cog) {
        toastStore.add(
          'info',
          'التاريخ غير مُجهَّز',
          'هذا التاريخ لا يملك صورة جاهزة بعد. استخدم خيارات تجهيز 3/6/12/24 شهر لتشغيل معالجة صريحة.',
        );
      }
      return;
    }
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
  }, [fieldId, activeIndicator, mode, tenantId, selectedImageryDate, availableImageryDates]);

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


  // الحقل المختار (يُشتقّ من القائمة + الاختيار المشترك) — مُعرَّف قبل المُعالِجات التي
  // تستعمله (تجهيز صور سنتين) لتفادي «used before declaration».
  const selected = fields.find((f) => f.id === fieldId);
  const operationalOverlayState = useMemo<OperationalOverlayState>(() => ({
    weather: showWeather,
    alerts: showAlerts,
    devices: showDevices,
    equipment: showEquipment,
    tasks: showTasks,
  }), [showWeather, showAlerts, showDevices, showEquipment, showTasks]);
  const isOverlayBlocked = useCallback((id: OperationalOverlayId) => isOperationalOverlayBlocked(id, operationalOverlayState), [operationalOverlayState]);
  const overlayBlockedTitle = useCallback((id: OperationalOverlayId) => mapClutterBlockedTitle(isOverlayBlocked(id)), [isOverlayBlocked]);


  useEffect(() => {
    backfillPollTokenRef.current += 1;
  }, [selected?.id]);

  // ── تضاريس: TileJSON للتظليل/الانحدار (فحص التوفّر + أسطورة الانحدار) ──────────
  // يُطلَب عند التفعيل فقط. available:false ⇒ نخزّن الردّ لعرض user_message الصادق
  // (بلا بلاطة). خطأ الشبكة ⇒ حالة غير متاحة صريحة (لا اختراع تضاريس).
  useEffect(() => {
    if (!showHillshade) return;
    let cancelled = false;
    fetchTerrainTileJson('hillshade', tenantId)
      .then((tj) => { if (!cancelled) setHillshadeTj(tj); })
      .catch(() => { if (!cancelled) setHillshadeTj({ tiles: [], available: false, layer: 'hillshade', user_message: 'تعذّر الوصول إلى خدمة التضاريس (Hillshade).' }); });
    return () => { cancelled = true; };
  }, [showHillshade, tenantId]);

  useEffect(() => {
    if (!showSlope) return;
    let cancelled = false;
    fetchTerrainTileJson('slope', tenantId)
      .then((tj) => { if (!cancelled) setSlopeTj(tj); })
      .catch(() => { if (!cancelled) setSlopeTj({ tiles: [], available: false, layer: 'slope', user_message: 'تعذّر الوصول إلى خدمة التضاريس (Slope).' }); });
    return () => { cancelled = true; };
  }, [showSlope, tenantId]);

  // ── تربة (SoilGrids): TileJSON للخاصّيّة/العمق (فحص التوفّر + أسطورة + إخلاء مسؤوليّة) ──
  // يُطلَب عند التفعيل فقط (وعند تغيّر الخاصّيّة/العمق). available:false ⇒ نخزّن الردّ
  // لعرض user_message الصادق (بلا بلاطة). خطأ الشبكة ⇒ حالة غير متاحة صريحة (لا اختراع تربة).
  useEffect(() => {
    if (!showSoil) return;
    let cancelled = false;
    fetchSoilTileJson(soilProperty, soilDepth, tenantId)
      .then((tj) => { if (!cancelled) setSoilTj(tj); })
      .catch(() => {
        if (!cancelled) setSoilTj({
          available: false,
          property: soilProperty,
          name_ar: SOIL_PROPERTIES.find((p) => p.key === soilProperty)?.label ?? soilProperty,
          unit: '',
          depth: soilDepth,
          legend: [],
          disclaimer: 'بيانات SoilGrids تقديريّة (~250م) للإرشاد بأخذ العيّنات فقط — ليست بديلاً عن تحليل مختبر.',
          user_message: 'تعذّر الوصول إلى خدمة التربة (SoilGrids).',
        });
      });
    return () => { cancelled = true; };
  }, [showSoil, soilProperty, soilDepth, tenantId]);

  // ── كنتور: يُجلب للحقل المختار من bbox حدوده. لا حقل/هندسة ⇒ لا طلب + ملاحظة.
  // computed:false / features:[] ⇒ نعرض user_message الصادق (لا خطوط مخترعة).
  useEffect(() => {
    if (!showContours) { setContoursData(null); setContoursNote(null); return; }
    if (!selected?.id || !selected.geometry) {
      setContoursData(null);
      setContoursNote('اختر حقلاً ذا حدود مرسومة لحساب خطوط الكنتور من نموذج الارتفاع.');
      return;
    }
    const poly = geomToPolygon(selected.geometry); // [lat,lng][]
    if (!poly || poly.length < 3) {
      setContoursData(null);
      setContoursNote('حدود الحقل مطلوبة لحساب خطوط الكنتور — ارسم/استورد الحدود أوّلاً.');
      return;
    }
    let minLat = Infinity, minLon = Infinity, maxLat = -Infinity, maxLon = -Infinity;
    for (const [lat, lng] of poly) {
      if (lat < minLat) minLat = lat; if (lat > maxLat) maxLat = lat;
      if (lng < minLon) minLon = lng; if (lng > maxLon) maxLon = lng;
    }
    const bbox: [number, number, number, number] = [minLon, minLat, maxLon, maxLat];
    let cancelled = false;
    setContoursNote(null);
    fetchFieldContours(selected.id, bbox, 10, selected.geometry)
      .then((fc) => {
        if (cancelled) return;
        setContoursData(fc);
        if (!fc.computed || !Array.isArray(fc.features) || fc.features.length === 0) {
          setContoursNote(fc.user_message || fc.reason || 'لا يوجد نموذج ارتفاع (DEM) لهذا الحقل — لا خطوط كنتور.');
        }
      })
      .catch(() => {
        if (!cancelled) { setContoursData(null); setContoursNote('تعذّر حساب خطوط الكنتور من خدمة التضاريس.'); }
      });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showContours, selected?.id, JSON.stringify(selected?.geometry ?? null)]);

  // نقاط أخذ العيّنات المقترَحة (🧪) — تُجلَب فقط حين المبدّل مفعّل + حقل ذو حدود.
  // bbox يُشتقّ من مضلّع الحقل (geomToPolygon)؛ computed:false/فارغ ⇒ لا نقاط + ملاحظة
  // صادقة (لا اختراع نقاط عند غياب مصدر SoilGrids).
  useEffect(() => {
    if (!showSoilSamples) { setSoilSamplePoints([]); setSoilSamplesNote(null); setSoilSamplesBusy(false); return; }
    if (!selected?.id || !selected.geometry) {
      setSoilSamplePoints([]);
      setSoilSamplesNote('اختر حقلاً ذا حدود مرسومة لاقتراح نقاط أخذ العيّنات.');
      return;
    }
    const poly = geomToPolygon(selected.geometry); // [lat,lng][]
    if (!poly || poly.length < 3) {
      setSoilSamplePoints([]);
      setSoilSamplesNote('حدود الحقل مطلوبة لاقتراح نقاط أخذ العيّنات — ارسم/استورد الحدود أوّلاً.');
      return;
    }
    let minLat = Infinity, minLon = Infinity, maxLat = -Infinity, maxLon = -Infinity;
    for (const [lat, lng] of poly) {
      if (lat < minLat) minLat = lat; if (lat > maxLat) maxLat = lat;
      if (lng < minLon) minLon = lng; if (lng > maxLon) maxLon = lng;
    }
    const bbox: [number, number, number, number] = [minLon, minLat, maxLon, maxLat];
    let cancelled = false;
    setSoilSamplesBusy(true);
    setSoilSamplesNote(null);
    fetchSoilSamplingPlan(selected.id, bbox, { depth: soilDepth, samplesPerZone: 2, geometry: selected.geometry })
      .then((plan) => {
        if (cancelled) return;
        const feats = Array.isArray(plan.features) ? plan.features : [];
        if (!plan.computed || feats.length === 0) {
          setSoilSamplePoints([]);
          setSoilSamplesNote(plan.user_message || plan.reason || 'لا مصدر تربة مُهيّأ لهذا الحقل — لا نقاط عيّنات مقترَحة.');
          return;
        }
        const pts = feats
          .filter((f) => f.geometry?.type === 'Point' && Array.isArray(f.geometry.coordinates))
          .map((f) => {
            const [lon, lat] = f.geometry.coordinates as [number, number];
            const props = f.properties || ({} as typeof f.properties);
            return {
              id: props?.point_id || `${lon},${lat}`,
              lat,
              lng: lon,
              label: props?.point_id || 'عيّنة تربة',
              reason: props?.reason_ar,
            };
          });
        setSoilSamplePoints(pts);
        setSoilSamplesNote(pts.length === 0 ? 'لا نقاط عيّنات قابلة للعرض.' : null);
      })
      .catch(() => {
        if (!cancelled) { setSoilSamplePoints([]); setSoilSamplesNote('تعذّر جلب خطّة أخذ العيّنات من خدمة التربة.'); }
      })
      .finally(() => { if (!cancelled) setSoilSamplesBusy(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showSoilSamples, selected?.id, soilDepth, JSON.stringify(selected?.geometry ?? null)]);

  // روابط قوالب بلاطات التضاريس — تُبنى فقط حين available:true (وإلّا null فتُخفى الطبقة).
  const hillshadeTilesUrl = showHillshade && hillshadeTj?.available ? hillshadeTileUrl(tenantId) : null;
  const slopeTilesUrl = showSlope && slopeTj?.available ? slopeTileUrl(tenantId) : null;
  // رابط قالب بلاطات التربة — يُبنى فقط حين available:true (وإلّا null فتُخفى الطبقة
  // ويُعرَض user_message الصادق). لا اختراع تربة عند غياب المصدر.
  const soilTilesUrl = showSoil && soilTj?.available ? soilTileUrl(soilProperty, soilDepth, tenantId) : null;

  const handleSelectImageryTimelineItem = useCallback((date: string, _item?: FieldImageryDateOption) => {
    const normalized = normalizeDateOnly(date);
    // اختيار thumbnail يبدّل تاريخ المشهد فقط. لا نغيّر المؤشر التحليلي المختار
    // حتى تبقى الخريطة على NDVI/NDMI/... الذي اختاره المستخدم، بينما المصغّرات
    // نفسها تُعرض دائمًا True Color كمعاينة بصرية طبيعية للحقل.
    setSelectedImageryDate(normalized || 'latest');
    setImageryTs(Date.now());
  }, []);

  const handlePrepareTwoYearImagery = useCallback(async (months = 24) => {
    if (!selected?.id) {
      toastStore.add('warning', 'اختر حقلاً أولاً', 'لا يمكن تجهيز الصور التاريخية بدون حقل نشط.');
      return;
    }
    if (!selected.geometry) {
      toastStore.add('warning', 'حدود الحقل مطلوبة', 'الـ backfill يحتاج clip_polygon_geojson مشتقاً من حدود الحقل.');
      return;
    }
    if (historicalBackfillBusy) return;
    const pollFieldId = selected.id;
    const pollToken = backfillPollTokenRef.current + 1;
    backfillPollTokenRef.current = pollToken;
    // اربط نافذة الشريط بالفترة المختارة (3/6/12/24) — لا تُظهِر 24 شهراً دائماً.
    setTimelineMonths(months);
    let finalRefreshImageryTimeline: null | (() => Promise<void>) = null;
    setHistoricalBackfillBusy(true);
    setHistoricalBackfillStatus(`جارٍ إنشاء خطة/مهمة backfill لمدة ${months} شهر…`);
    try {
      // الـbackfill يحسب COGs للمؤشّرات + الصورة الخام truecolor (تُحفَظ الآن كـCOG RGBA
      // في raster-service فيقبلها العقد). نُرشِّح للمجموعة المدعومة كي لا يُرجَع 400 لمؤشّر
      // غير مدعوم. NDVI/NDMI يبقيان أساساً مضموناً غير فارغ. تجهيز truecolor يمكّن /tiles
      // المحفوظ للصورة الخام (بدل تصيير CDSE الحيّ لكلّ بلاطة).
      const BACKFILL_SUPPORTED_INDICES = [
        RAW_IMAGERY_INDEX_ID, 'ndvi', 'ndmi', 'savi', 'evi', 'gndvi', 'ndre',
        'reci', 'gci', 'arvi', 'sipi', 'nbr', 'ccci', 'vari', 'gli', 'bsi',
        'msi', 'msavi', 'ndwi', 'salinity',
      ];
      const toBackfillIndex = (idx: string) => (idx === 'salinity' ? 'ndsi' : idx);
      const CORE_BACKFILL_INDICES = [
        RAW_IMAGERY_INDEX_ID, 'ndvi', 'ndre', 'ndmi', 'msavi', 'ndwi', 'salinity',
      ];
      const requestedBackfillIndices = Array.from(
        new Set([
          ...CORE_BACKFILL_INDICES,
          ...(activeIndicator ? [activeIndicator] : []),
        ]),
      );
      const indices = Array.from(
        new Set(
          requestedBackfillIndices
            .filter((i) => BACKFILL_SUPPORTED_INDICES.includes(i))
            .map(toBackfillIndex),
        ),
      );
      if (indices.length === 0) indices.push('truecolor', 'ndvi', 'ndre', 'ndmi', 'msavi', 'ndwi', 'ndsi');
      const payload = {
        preset: 'custom' as const,
        months,
        indices,
        // سياسة NDVI الأساسية: اسحب مشاهد Sentinel-2 كل 3-5 أيام عندما تكون
        // نسبة المشهد الصافي >=50% (أي cloud<=50%). العامل ينتقي حتى 8 مشاهد/شهر
        // مع تباعد >=3 أيام قدر الإمكان؛ >=70% صافي تُعد جودة عالية في البيانات.
        max_cloud_pct: 50,
        limit_per_month: 8,
        apply_cloud_mask: true,
        clip_polygon_geojson: selected.geometry,
        dry_run: false,
      };
      const result = await runHistoricalImageryBackfill(pollFieldId, payload);
      const scheduled = Number(result?.jobs_scheduled ?? result?.jobs_created ?? result?.selected_scenes ?? 0);
      // v10-F10/v20260706: المسار اللاتزامنيّ يُرجِع run_id. لا نكتفي برسالة "أُدرجت"؛
      // نستطلع حالة التشغيل من بوابة المنصّة ثم نعيد تحميل available-dates/timeline عند
      // اكتمال العامل، حتى يرى المستخدم تواريخ الـbackfill دون refresh يدوي.
      const isAsync = (result as { mode?: string })?.mode === 'async';
      const runId = Number((result as { run_id?: number })?.run_id ?? 0);
      // يجب أن يطابق منطق التحميل الأوّليّ (سطر ~486): طبقة الصورة الخام (truecolor)
      // لا تملك COG مخزّناً، فتمرير معرّفها يُصفّي التواريخ على مؤشّر غير موجود ⇒
      // شريط زمنيّ فارغ بعد الـbackfill. نُحوّله إلى undefined فيُجلَب كامل المحور.
      const baseRefreshIndex = activeIndicator ?? indices[0];
      const refreshIndex =
        baseRefreshIndex && baseRefreshIndex !== RAW_IMAGERY_INDEX_ID ? baseRefreshIndex : undefined;
      const refreshImageryTimeline = async () => {
        const [dates, allDates] = await Promise.all([
          fetchFieldImageryAvailableDates(pollFieldId, refreshIndex, 240).catch(() => [] as FieldImageryDateOption[]),
          fetchFieldImageryAvailableDates(pollFieldId, refreshIndex, 240, { includeProvider: true, months }).catch(() => [] as FieldImageryDateOption[]),
        ]);
        if (Array.isArray(dates) && dates.length > 0) {
          setAvailableImageryDates([...dates].sort((a, b) => b.date.localeCompare(a.date)));
        }
        if (Array.isArray(allDates) && allDates.length > 0) {
          setTimelineImageryDates([...allDates].sort((a, b) => b.date.localeCompare(a.date)));
        }
        setImageryTs(Date.now());
      };
      finalRefreshImageryTimeline = refreshImageryTimeline;
      const status = isAsync
        ? `تمّ إدراج تشغيلة backfill لمدة ${months} شهر في الطابور (run_id=${runId || '?'}); جارٍ متابعة التقدّم حتى تكتمل وتُزامَن التواريخ تلقائياً.`
        : scheduled > 0
          ? `تم تجهيز مهمة ${months} شهر: ${scheduled} عنصر/مشهد مجدول.`
          : `تم إرسال طلب تجهيز ${months} شهر؛ تحقق من حالة raster-service والتواريخ المتاحة بعد المعالجة.`;
      setHistoricalBackfillStatus(status);
      toastStore.add(isAsync ? 'info' : 'success', isAsync ? `أُدرِجت تشغيلة ${months} شهر في الطابور` : `بدأ تجهيز ${months} شهر تاريخية`, status);

      if (isAsync && runId > 0) {
        const sleep = (ms: number) => new Promise(resolve => window.setTimeout(resolve, ms));
        let lastStatus = 'planned';
        let transientErrors = 0;
        for (let attempt = 0; attempt < 80; attempt += 1) {
          if (backfillPollTokenRef.current !== pollToken) break;
          await sleep(attempt < 6 ? 2500 : 5000);
          if (backfillPollTokenRef.current !== pollToken) break;
          let run;
          try {
            run = await fetchHistoricalImageryBackfillStatus(pollFieldId, runId);
            transientErrors = 0;
          } catch (pollError) {
            transientErrors += 1;
            if (transientErrors <= 5 && attempt < 79) {
              setHistoricalBackfillStatus(`backfill #${runId}: تعذّر استطلاع الحالة مؤقتاً (${transientErrors}/5)؛ سنعيد المحاولة…`);
              continue;
            }
            throw pollError;
          }
          lastStatus = String(run.status || lastStatus);
          const persisted = Number(run.items_persisted ?? 0);
          const failed = Number(run.items_failed ?? 0);
          const skipped = Number(run.items_skipped ?? 0);
          setHistoricalBackfillStatus(`backfill #${runId}: ${lastStatus} — حُفظ ${persisted}، فشل ${failed}، تخطّي ${skipped}`);
          // أعِد تحميل التواريخ تدريجياً أثناء المعالجة أيضاً، لأن بعض العناصر تُحفَظ قبل نهاية التشغيل.
          if (attempt % 2 === 1 || isTerminalBackfillStatus(lastStatus)) {
            await refreshImageryTimeline();
          }
          if (isTerminalBackfillStatus(lastStatus)) {
            if (lastStatus === 'failed') {
              const detail = run.error ? ` — ${run.error}` : '';
              toastStore.add('error', `فشل backfill #${runId}`, `انتهت التشغيلة بالحالة failed${detail}`);
            } else {
              toastStore.add(lastStatus === 'completed_with_errors' ? 'warning' : 'success', `اكتمل backfill #${runId}`, `تمت مزامنة Timeline والبلاطات للحقل.`);
            }
            break;
          }
        }
      } else {
        // المسار المتزامن/القديم: إعادة تحميل فورية كافية.
        await refreshImageryTimeline();
      }
    } catch (e) {
      const detail = asApiError(e).message || 'تعذّر تشغيل backfill التاريخي. تحقق من token raster-service أو حدود الحقل.';
      setHistoricalBackfillStatus(detail);
      toastStore.add('error', `فشل تجهيز ${months} شهر تاريخية`, detail);
    } finally {
      if (backfillPollTokenRef.current === pollToken && finalRefreshImageryTimeline) {
        try { await finalRefreshImageryTimeline(); } catch { /* best-effort final sync */ }
      }
      if (backfillPollTokenRef.current === pollToken) setHistoricalBackfillBusy(false);
    }
  }, [activeIndicator, historicalBackfillBusy, selected]);

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

  const indicatorActive = mode === '2d' && !compare ? activeIndicator : null;

  // إصلاح «الطبقة الورديّة»: حين يكون للتاريخ المختار COG محفوظ للمؤشّر النشط نقرأ الطبقة
  // المحفوظة من raster_assets عبر /tiles بدل تصيير CDSE الحيّ /cdse-tiles. نشترط إدراج
  // المؤشّر صراحةً في indices (لا ارتداد «indices فارغة ⇒ نعم»): عند الشكّ نبقى على المسار
  // الحيّ الذي يُصيّر دائماً. TrueColor يُحفَظ الآن كـCOG RGBA مثل المؤشرات؛ وsalinity
  // تُحفَظ باسم NDSI. لا تبديل بلا مؤشّر نشط.
  const _persistNeedle = indicatorActive
    ? indicatorActive === 'salinity'
      ? 'NDSI'
      : indicatorActive.toUpperCase()
    : null;
  const _dateHasIndicatorCog = (d: { has_cog?: boolean; indices?: string[] }) =>
    !!d.has_cog &&
    !!_persistNeedle &&
    Array.isArray(d.indices) &&
    d.indices.some((i) => String(i).toUpperCase() === _persistNeedle);
  const selectedDateHasCog = !_persistNeedle
    ? false
    : selectedImageryDate !== 'latest'
      ? availableImageryDates.some(
          (d) => d.date === selectedImageryDate && _dateHasIndicatorCog(d),
        )
      : availableImageryDates.some(_dateHasIndicatorCog);

  // المشهد المختار (لعرض تاريخ الالتقاط الحقيقيّ). عند 'latest' نعرض أحدث مشهد جاهز.
  const selectedScene =
    selectedImageryDate !== 'latest'
      ? availableImageryDates.find((d) => d.date === selectedImageryDate) ?? null
      : (dateSelectorDates.find((d) => d.has_cog) ?? dateSelectorDates[0] ?? null);
  // تاريخ الالتقاط بصدق: وقت المشهد الحقيقيّ (STAC) إن توفّر، وإلّا التاريخ وحده (بلا
  // اختلاق ساعة). لا يظهر شيء إن لم نعرف مشهداً.
  const acquisitionLabel = (() => {
    if (!selectedScene) return null;
    const iso = selectedScene.acquisition_datetime;
    if (iso) {
      const dt = new Date(iso);
      if (!Number.isNaN(dt.getTime())) {
        return new Intl.DateTimeFormat('ar', { dateStyle: 'medium', timeStyle: 'short' }).format(dt);
      }
    }
    return selectedScene.date;
  })();

  // قائمة الحقول المُرشَّحة بالبحث (اسم/محصول) — لوحة الحقول الباحثة.
  const visibleFields = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return fields;
    return fields.filter((f) =>
      f.name.toLowerCase().includes(q) || (f.crop ?? '').toLowerCase().includes(q));
  }, [fields, search]);


  // v54: تحقق Runtime من أن العرض الافتراضي TrueColor ليس مجرد حالة UI؛ بل
  // يطلب /tilejson (COG Element84) من raster-service لنفس الحقل/التاريخ/المؤشر. عند عدم
  // الجاهزية نعرض رسالة صادقة بدلاً من ترك خريطة الأساس تبدو كصورة حقل محلّلة.
  useEffect(() => {
    if (!fieldId || indicatorActive !== RAW_IMAGERY_INDEX_ID) {
      setTrueColorRuntime({ state: 'idle', message: 'التحقق خاص بصورة TrueColor الخام عند اختيار حقل.' });
      return;
    }
    let cancelled = false;
    // فحص الجاهزية عبر /tilejson (COG من Element84) — لا CDSE. حقل بلا حدود مرسومة
    // لا يُنتِج COG في backfill ⇒ tilejson سيُعيد available=false تلقائيّاً.
    // نُظهر رسالة مبكّرة واضحة إن كانت الهندسة غائبة بدل انتظار الاستجابة.
    const clipParams = cdseClipParams(selected?.geometry as { type?: string; coordinates?: unknown } | null);
    if (!clipParams.poly) {
      setTrueColorRuntime({
        state: 'unavailable',
        message: 'لا توجد حدود مرسومة لهذا الحقل. المؤشّرات على مستوى البكسل تُقصّ على حدود الحقل — ارسم أو استورد الحدود أوّلاً (إضافة/تعديل الحقل) ثمّ ستظهر الطبقة.',
        endpoint: 'tilejson',
      });
      return;
    }
    setTrueColorRuntime({ state: 'checking', message: 'جارٍ التحقق من جاهزية TrueColor عبر Element84/raster-service…', endpoint: 'tilejson' });
    const params = {
      index: RAW_IMAGERY_INDEX_ID,
      ...(selectedImageryDate && selectedImageryDate !== 'latest' ? { date: selectedImageryDate } : {}),
      ...(tenantId ? { tid: tenantId } : {}),
    };
    rasterApi
      .get(`/v1/fields/${fieldId}/tilejson`, { params })
      .then((r) => {
        if (cancelled) return;
        const data = r.data as { available?: boolean; user_message?: string; note?: string; reason?: string; resolved_date?: string | null };
        if (data?.available === false) {
          setTrueColorRuntime({
            state: 'unavailable',
            message: data.user_message || data.note || data.reason || TRUECOLOR_UNAVAILABLE_MESSAGE,
            endpoint: 'tilejson',
          });
          return;
        }
        const resolved = data?.resolved_date ? ` · التاريخ: ${data.resolved_date}` : '';
        setTrueColorRuntime({ state: 'ready', message: `TrueColor جاهز كصور Sentinel-2 خام من Element84 (COG محلّيّ داخل حدود الحقل)${resolved}.`, endpoint: 'tilejson' });
      })
      .catch(() => {
        if (!cancelled) setTrueColorRuntime({ state: 'error', message: TRUECOLOR_UNAVAILABLE_MESSAGE, endpoint: 'tilejson' });
      });
    return () => { cancelled = true; };
    // أعِد الفحص عند تغيّر هندسة الحقل (بصمة مستقرّة — المرجع كائن غير مستقرّ).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fieldId, indicatorActive, selectedImageryDate, tenantId,
      JSON.stringify(cdseClipParams(selected?.geometry as { type?: string; coordinates?: unknown } | null))]);

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


  const selectedActiveSeasonId = useMemo(() => {
    const d = detailQ.data as unknown as Record<string, unknown> | undefined;
    const pickId = (value: unknown): string | null => {
      if (!value || typeof value !== 'object') return null;
      const obj = value as Record<string, unknown>;
      const raw = obj.season_id ?? obj.id;
      return typeof raw === 'string' && raw.trim() ? raw : null;
    };
    const direct = pickId(d?.active_season) ?? pickId(d?.current_season);
    if (direct) return direct;
    const seasons = d?.seasons;
    if (Array.isArray(seasons)) {
      const active = seasons.find((season) => {
        const s = season as Record<string, unknown>;
        return s.status === 'active' || s.active === true || !s.season_end;
      });
      return pickId(active);
    }
    return null;
  }, [detailQ.data]);

  const mapDataStatus = useMemo(() => {
    if (!fieldId) return { tone: 'warn' as const, label: 'اختر حقلاً', hint: 'لن تُحمّل المؤشرات قبل تحديد حقل.' };
    if (!indicatorActive) return { tone: 'info' as const, label: 'لا طبقة نشطة', hint: 'افتح صورة الحقل الخام أو اختر مؤشراً تفسيرياً.' };
    if (indicatorActive === RAW_IMAGERY_INDEX_ID) return { tone: trueColorRuntime.state === 'ready' ? 'ok' as const : trueColorRuntime.state === 'checking' ? 'info' as const : 'warn' as const, label: 'صورة الحقل الخام TrueColor', hint: trueColorRuntime.message };
    // المؤشّرات البكسليّة (NDVI…) تُقصّ على حدود الحقل. بلا هندسة مرسومة لا طبقة —
    // نُعلن السبب الصادق بدل الادّعاء أنّها «ستُحمَّل داخل حدود الحقل».
    if (!cdseClipParams(selected?.geometry as { type?: string; coordinates?: unknown } | null).poly) {
      return { tone: 'warn' as const, label: 'حدود الحقل مفقودة', hint: 'لا توجد حدود مرسومة لهذا الحقل — المؤشّرات على مستوى البكسل تُقصّ على الحدود. ارسم أو استورد الحدود أوّلاً.' };
    }
    return { tone: 'ok' as const, label: 'مؤشر نشط', hint: `سيتم تحميل ${LAYER_LEGEND[indicatorActive]?.short ?? indicatorActive} داخل حدود الحقل.` };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fieldId, indicatorActive, trueColorRuntime, JSON.stringify(cdseClipParams(selected?.geometry as { type?: string; coordinates?: unknown } | null))]);

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

  // ── عرض الفلاح (P1): 4 مؤشّرات من إشارات حيّة حقيقيّة (NDVI · رطوبة تربة · نيتروجين · طقس).
  // استخراج دفاعيّ — عند غياب أيّ إشارة تُمرَّر null فتُعرَض 'غير متاح' بلا اختلاق. ──
  const ndviQ = useCurrentNDVI(fieldId ?? '');
  const soilMoistureQ = useFieldSoilMoisture(fieldId ?? null);
  const nRecQ = useSoilNRecommendation(fieldId ?? '');
  const farmerMetricsInput = useMemo(() => {
    const nd = ndviQ.data as { ndvi?: number; mean_ndvi?: number } | undefined;
    const ndvi = typeof nd?.ndvi === 'number' ? nd.ndvi : typeof nd?.mean_ndvi === 'number' ? nd.mean_ndvi : null;
    const soilMoisturePct = soilMoistureQ.data?.reading?.soil_moisture_pct ?? null;
    const nd2 = nRecQ.data as { status?: string; nitrogen_status?: string; recommended_n_kg_ha?: number } | undefined;
    const nStatusRaw = nd2?.status ?? nd2?.nitrogen_status;
    let nitrogenStatus: 'adequate' | 'deficit' | 'excess' | null = null;
    if (nStatusRaw === 'adequate' || nStatusRaw === 'deficit' || nStatusRaw === 'excess') nitrogenStatus = nStatusRaw;
    else if (typeof nd2?.recommended_n_kg_ha === 'number') nitrogenStatus = nd2.recommended_n_kg_ha > 0 ? 'deficit' : 'adequate';
    const wd = weatherQ.data as { daily?: Array<{ temp_max_c?: number; wind_speed_m_s?: number; rain_mm?: number; precipitation_mm?: number }> } | undefined;
    const today = wd?.daily?.[0];
    const weather = today
      ? { tempMaxC: today.temp_max_c ?? null, windMs: today.wind_speed_m_s ?? null, rainMm: today.rain_mm ?? today.precipitation_mm ?? null }
      : null;
    return { ndvi, soilMoisturePct, nitrogenStatus, weather };
  }, [ndviQ.data, soilMoistureQ.data, nRecQ.data, weatherQ.data]);

  // ── Field Water Brain: قرار ريّ من الرطوبة + مجموع مطر الأيّام القادمة + الحرارة. ──
  const waterBrainInput = useMemo(() => {
    const wd = weatherQ.data as { daily?: Array<{ temp_max_c?: number; rain_mm?: number; precipitation_mm?: number }> } | undefined;
    const upcoming = (wd?.daily ?? []).slice(0, 3);
    const forecastRainMm = upcoming.length
      ? upcoming.reduce((s, d) => s + (d.rain_mm ?? d.precipitation_mm ?? 0), 0)
      : null;
    return {
      soilMoisturePct: farmerMetricsInput.soilMoisturePct,
      forecastRainMm,
      tempMaxC: farmerMetricsInput.weather?.tempMaxC ?? null,
    };
  }, [weatherQ.data, farmerMetricsInput]);

  // ── Zone & VRA readiness (P2): مسار Field → Zone → Action من إشارات حقيقيّة
  // (مشاهد جاهزة للعنقدة + عدد الوصفات المحفوظة). يوجّه لمصمّم المناطق القائم. ──
  // وضع الخبير فقط: لا نجلب بيانات البطاقات المتقدّمة في وضع الفلاح (توفير طلبات).
  const expertMode = fieldMode === 'expert';
  const prescriptionsQ = useFieldPrescriptions(fieldId ?? '', expertMode && !!fieldId);
  const imageryReadyCount = availableImageryDates.filter((d) => d.has_cog).length;
  // استكشاف الحقل: تصنيف المشاكل الشائعة لمحصول الحقل النشط (Taranis).
  const scoutingQ = useCropScoutingIssues(expertMode ? (selected?.crop || undefined) : undefined);
  // مركز الموسم: مراحل نموّ الموسم النشط + إجراء الطور (Cropin) — نقاط منصّة حيّة.
  const phenologyQ = useFieldPhenology(expertMode ? (fieldId ?? null) : null);
  const stageActionsQ = useFieldStageActions(expertMode ? (fieldId ?? null) : null);
  // كفاءة مياه الحقل: إجماليّ الريّ المُطبَّق (mm) من الدفتر — لتقدير تكلفة الريّ في طبقة الأعمال.
  const waterEfficiencyQ = useFieldWaterEfficiency(expertMode ? (fieldId ?? null) : null);
  // سجلّ التتبّع: مواسم الحقل + العمليّات المكتملة (Farmonaut) — تقرير قابل للمشاركة.
  const seasonsQ = useSeasons(expertMode ? (fieldId ?? undefined) : undefined);
  const activeSeason = useMemo(
    () => (seasonsQ.data ?? []).find((s) => s.status === 'active') ?? seasonsQ.data?.[0] ?? null,
    [seasonsQ.data],
  );
  // ربحيّة الموسم: تعكس التكاليف/الإيرادات الفعليّة المُخزَّنة (farm-ledger v100–v102) في FieldView.
  // مبوَّبة بوضع الخبير + وجود موسم؛ الخطّافات تلتقط 404 (الميزة مُطفأة) كحالة صادقة لا خطأ.
  const activeSeasonId = activeSeason?.season_id ?? null;
  const ledgerSummaryQ = useFarmLedgerSummary(fieldId ?? null, activeSeasonId, expertMode && !!activeSeasonId);
  const profitabilityQ = useSeasonProfitability(activeSeasonId, expertMode && !!activeSeasonId);
  const varianceQ = useSeasonVariance(activeSeasonId, expertMode && !!activeSeasonId);
  const economicStateQ = useSeasonEconomicState(
    activeSeasonId,
    typeof selected?.area === 'number' ? selected.area : null,
    expertMode && !!activeSeasonId,
  );
  const completedOps = useMemo(
    () => (tasksQ.data?.tasks ?? [])
      .filter((t) => t.field_id === fieldId && t.status === 'completed')
      .map((t) => ({ label: t.task_type, date: t.recommended_date })),
    [tasksQ.data, fieldId],
  );
  // توفّر الأدلّة الحقيقيّ لطبقة الأهداف — يُحسَب من الاستعلامات الحيّة فقط (لا افتراض تفاؤليّ):
  // كلّ مصدر = true حين تكون بياناته حاضرة فعلاً، وإلّا يُترَك false فتمنع اللوحةُ الإجراءَ بصدق.
  const objectiveAvailability = useMemo<EvidenceAvailability>(() => ({
    imagery: imageryReadyCount > 0,
    weather: !!weatherQ.data?.current,
    moisture: soilMoistureQ.data?.reading != null,
    alerts: Array.isArray(alertsQ.data),
    tasks: Array.isArray(tasksQ.data?.tasks),
    // لا نعتبر crop/area وحدها «سجلّات»؛ الربحيّة تحتاج أثراً تشغيليّاً فعليّاً (عمليّات
    // مكتملة أو قياس كفاءة ماء) — يمنع فتح هدف الربحيّة بدليل وهميّ.
    records: completedOps.length > 0 || !!waterEfficiencyQ.data,
    // جاهزيّة مسار المناطق: مناطق محفوظة فعلاً أو صور جاهزة لبناء مناطق جديدة.
    zones: zonePersisted.length > 0 || imageryReadyCount > 0,
    season: !!phenologyQ.data?.available || (seasonsQ.data?.length ?? 0) > 0,
    planning: !!selected?.crop,
    // GDD يحتاج محصولاً + طقساً/موسماً حتّى لا يظهر هدف المرحلة الحراريّة بلا سياق.
    gdd: !!selected?.crop && !!weatherQ.data?.current && (!!phenologyQ.data?.available || (seasonsQ.data?.length ?? 0) > 0),
  }), [imageryReadyCount, weatherQ.data, soilMoistureQ.data, alertsQ.data, tasksQ.data, completedOps.length, waterEfficiencyQ.data, zonePersisted.length, phenologyQ.data, seasonsQ.data, selected?.crop]);
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

  // ── دبابيس الاستكشاف (دائمة، v94 — تُحفَظ على الخادم) ──────────────
  // الإضافة: دبّوس تفاؤليّ محلّيّ فوريّ + POST /api/v1/fields/{id}/pins (idempotent عبر
  // pin_id)؛ نجاح الطلب يُبطِل مخبّأ useScoutingPins ⇒ إعادة جلب فتظهر مُخزَّنة، والفشل
  // ⇒ تراجُع فوريّ عن التفاؤليّ. لا حقل مختار ⇒ عرض تفاؤليّ فقط (لا وجهة حفظ).
  const handleAddPin = useCallback((lat: number, lng: number) => {
    const pinId = `pin_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    setOptimisticPins((prev) => [...prev, { id: pinId, lat, lng, note: '', category: pinCategory }]);
    if (!fieldId) return;
    createScoutPin.mutate(
      { pin_id: pinId, field_id: fieldId, lat, lng, issue_category: pinCategory, note_ar: null },
      { onError: () => setOptimisticPins((prev) => prev.filter((p) => p.id !== pinId)) },
    );
  }, [pinCategory, fieldId, createScoutPin]);

  // «مسح» يُزيل الدبابيس التفاؤليّة غير المُثبَّتة بعد فقط — المُخزَّنة على الخادم دائمة
  // (لا نقطة حذف جماعيّ). صدق: لا يُدَّعى أنّه يحذف المُخزَّنة.
  const handleClearPins = useCallback(() => setOptimisticPins([]), []);

  // ── v37-v41: تحميل تصاميم Pivot ومناطق الإدارة/الوصفات المحفوظة + الطابور المحلي للحقل المختار ───────
  useEffect(() => {
    let alive = true;
    if (!selected?.id) {
      setPivotPersisted([]);
      setZonePersisted([]);
      return () => { alive = false; };
    }
    listDrawingFeatures(selected.id)
      .then((features) => {
        if (!alive) return;
        setPivotPersisted(features.filter((f) => f.kind === 'pivot'));
        setZonePersisted(features.filter((f) => ['management-zone', 'prescription-zone', 'exclusion-zone'].includes(f.kind)));
      })
      .catch(() => {
        if (!alive) return;
        setPivotPersisted([]);
        setZonePersisted([]);
      });
    return () => { alive = false; };
  }, [selected?.id]);

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
      seasonId: selectedActiveSeasonId ?? undefined,
      name: `Pivot ${selected.name}`,
    });
    setPivotDrafts((prev) => [...prev, feature]);
    setShowPivots(true);
    toastStore.add('success', 'تم إنشاء تصميم Pivot', `المساحة التقريبية ${(feature.measurements?.areaHa ?? 0).toFixed(2)} هـ`);
  }, [pivotEndAngleDeg, pivotRadiusM, pivotRingCount, pivotSpanCount, pivotStartAngleDeg, selected, selectedActiveSeasonId]);

  const handleClearPivotDrafts = useCallback(() => setPivotDrafts([]), []);

  const handleSavePivotDrafts = useCallback(async () => {
    if (pivotDrafts.length === 0) return;
    if (!selected?.id) {
      toastStore.add('warning', 'اختر حقلاً أولاً', 'لا يمكن حفظ تصميم Pivot بدون حقل مرتبط.');
      return;
    }
    setPivotSyncBusy(true);
    try {
      const saved = await Promise.all(
        pivotDrafts.map((draft) => createDrawingFeature({
          ...draft,
          draft: false,
          properties: {
            ...draft.properties,
            fieldId: selected.id,
            seasonId: draft.properties.seasonId ?? selectedActiveSeasonId ?? undefined,
            workflow: 'design-pivot',
          },
          updatedAt: new Date().toISOString(),
        })),
      );
      setPivotPersisted((prev) => {
        const byId = new Map(prev.map((f) => [f.id, f]));
        for (const f of saved) byId.set(f.id, f);
        return Array.from(byId.values());
      });
      setPivotDrafts([]);
      setShowPivots(true);
      toastStore.add('success', 'تم حفظ تصاميم Pivot', `${saved.length} تصميم محفوظ ومربوط بالحقل${selectedActiveSeasonId ? ' والموسم' : ''}.`);
    } catch (e) {
      toastStore.add('error', 'فشل حفظ Pivot', apiErrorMessage(e, 'تعذّر حفظ تصاميم Pivot في الخادم.'));
    } finally {
      setPivotSyncBusy(false);
    }
  }, [pivotDrafts, selected?.id, selectedActiveSeasonId]);

  const handleCreateZoneFromField = useCallback(async () => {
    if (!selected?.id) {
      toastStore.add('warning', 'اختر حقلاً أولاً', 'إنشاء مناطق الإدارة/الوصفات يحتاج حقلاً مختاراً.');
      return;
    }
    const geometry = normalizeFieldGeometryForZone(selected.geometry);
    if (!geometry) {
      toastStore.add('warning', 'لا توجد حدود حقل', 'لا يمكن إنشاء Zone بدون هندسة حقل Polygon/MultiPolygon.');
      return;
    }
    const isPrescription = zoneKind === 'prescription-zone';
    const feature = buildAgriculturalZoneFeature({
      kind: zoneKind,
      geometry,
      fieldId: selected.id,
      seasonId: selectedActiveSeasonId ?? undefined,
      crop: selected.crop,
      sourceLayer: activeIndicator ?? undefined,
      rate: isPrescription ? zoneRate : undefined,
      rateUnit: isPrescription ? zoneRateUnit : undefined,
      name: isPrescription ? `وصفة ${selected.name}` : zoneKind === 'exclusion-zone' ? `استبعاد ${selected.name}` : `منطقة إدارة ${selected.name}`,
      draft: false,
    });
    setZoneSyncBusy(true);
    try {
      const saved = await createDrawingFeature(feature);
      setZonePersisted((prev) => [saved, ...prev.filter((f) => f.id !== saved.id)]);
      setShowPivots(true);
      toastStore.add('success', 'تم حفظ Zone', `${feature.properties.name} · ${(feature.measurements?.areaHa ?? 0).toFixed(2)} هـ`);
    } catch (e) {
      toastStore.add('error', 'فشل حفظ Zone', apiErrorMessage(e, 'تعذّر حفظ منطقة الإدارة/الوصفة في الخادم.'));
    } finally {
      setZoneSyncBusy(false);
    }
  }, [activeIndicator, selected, selectedActiveSeasonId, zoneKind, zoneRate, zoneRateUnit]);

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
    map_view?: { zoom: number; lat: number; lng: number };
    boundary_metadata?: Record<string, unknown>;
    idempotency_key?: string;
  }) => {
    try {
      const fieldPayload = {
        name: data.name, crop: data.crop, soil_type: data.soil_type, manager: data.manager,
        field_code: data.field_code ?? null, water_source: data.water_source ?? null,
        irrigation_type: data.irrigation_type ?? null, pivot: data.pivot ?? null,
        country: data.country ?? null, region: data.region ?? null, geometry: data.geometry,
        boundary_metadata: data.boundary_metadata ?? undefined,
        idempotency_key: (data as Record<string, unknown>).idempotency_key,
      };
      const r = await kongApi.post('/api/v1/fields', withoutIdempotency(fieldPayload), idempotencyConfig(fieldPayload));
      const rec = r.data as Record<string, unknown>;
      const newId = String(rec.field_id ?? '');
      // حفظ مشهد الخريطة (zoom + مركز) بمعرّف الحقل المُنشأ — يُطار إليه عند فتحه لاحقاً.
      if (data.map_view) saveFieldMapView(newId, data.map_view);
      setShowAddField(false);
      toastStore.add('success', '✅ تم إضافة الحقل', data.name);
      await refetch();
      // انتقل إلى الحقل المُنشأ حديثاً واعرضه بالإطار الافتراضيّ (لا حقل سابق).
      if (newId) {
        markDefaultViewOnce(newId);
        setFieldId(newId);
      }
    } catch (e) {
      // استخرج السبب الصادق من الخادم (detail.message_ar) — مثل «يوجد حقل بالاسم
      // نفسه» أو «حدود الحقل تتداخل مع…» (409) — بدل رسالة أكسيوس الخام
      // «Request failed with status code 409» التي لا تُفهِم المستخدِم السبب.
      const msg = apiErrorMessage(e, 'تعذّر حفظ الحقل — تحقّق من القاعدة/الصلاحيّة أو صحّة الحدود.');
      toastStore.add('error', '⚠️ فشل حفظ الحقل', msg);
      throw new Error(msg);
    }
  }, [refetch, setFieldId]);

  const handleImportField = useCallback(async (payload: unknown) => {
    try {
      const r = await kongApi.post('/api/v1/fields/import', withoutIdempotency(payload as Record<string, unknown>), idempotencyConfig(payload as Record<string, unknown>));
      const newId = String((r.data as Record<string, unknown>)?.field_id ?? '');
      setShowAddField(false);
      toastStore.add('success', '✅ تم استيراد الحقل', '');
      await refetch();
      // انتقل إلى الحقل المستورَد حديثاً واعرضه بالإطار الافتراضيّ.
      if (newId) { markDefaultViewOnce(newId); setFieldId(newId); }
    } catch (e) {
      // السبب الصادق من الخادم (detail.message_ar) بدل رسالة أكسيوس الخام (409/422…).
      const msg = apiErrorMessage(e, 'تعذّر استيراد الحقل — تحقّق من صحّة الملفّ والحدود والصلاحيّة.');
      throw new Error(msg);
    }
  }, [refetch, setFieldId]);


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

      {fieldViewStatus && (
        <div
          className="mb-3 rounded-xl px-3 py-2 text-xs"
          data-testid="fieldview-status"
          style={{ background: '#064e3b33', border: '1px solid #10b98155', color: '#d1fae5' }}
        >
          {fieldViewStatus}
        </div>
      )}

      {/* FieldView Smart Deck — أفضل إجراء تالٍ للحقل النشط (صور/استكشاف/عمليّات/سجلّ/سياق).
          يظهر فقط عند وجود حقل نشط؛ العدّادات غير المتاحة تُترَك undefined فتسقط البطاقة
          إلى اقتراح صادق بدل رقم ملفَّق. الأزرار موصولة بأفعال MapHub الحقيقيّة فقط. */}
      {selected && (
        <div className="mb-3 inline-flex items-center gap-1 rounded-xl p-0.5" style={{ background: T.card, border: `1px solid ${T.line}` }} data-testid="fieldview-mode-toggle">
          {(['farmer', 'expert'] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setFieldModePersist(m)}
              className="px-3 py-1 rounded-lg text-xs font-bold"
              style={{ background: fieldMode === m ? '#14532d' : 'transparent', color: fieldMode === m ? '#bbf7d0' : T.muted }}
              aria-pressed={fieldMode === m}
            >
              {m === 'farmer' ? 'وضع الفلاح' : 'وضع الخبير'}
            </button>
          ))}
        </div>
      )}

      {selected && <FarmerMetricsCard {...farmerMetricsInput} />}

      {selected && <FieldWaterBrainCard {...waterBrainInput} />}

      {selected && (
        <FieldHealthReportCard
          fieldId={fieldId}
          fieldName={selected.name}
          crop={selected.crop}
          areaHa={typeof selected.area === 'number' ? selected.area : null}
          imageryDates={availableImageryDates}
          activeAlertsCount={Array.isArray(alertsQ.data) ? alertsQ.data.length : undefined}
          openTasksCount={Array.isArray(tasksQ.data?.tasks) ? tasksQ.data.tasks.length : undefined}
          equipmentCount={Array.isArray(equipmentQ.data) ? equipmentQ.data.length : undefined}
          weatherReady={!!weatherQ.data?.current}
          agentContextReady={!!fieldId}
          routeFieldIsInvalid={routeFieldIsInvalid}
          storedFieldIsInvalid={storedFieldIsInvalid}
          selectionReason={selectionReason}
        />
      )}

      {/* طبقة الأهداف (Field Objective Engine): تحوّل FieldView من «أداة تعرض بيانات» إلى
          «متعاون يحقّق هدفاً» — نيّة ⇒ خطّة (فحص→تفسير→إجراء→مراجعة) مربوطة بأدلّة حقيقيّة،
          تمنع التوصية حتّى اكتمال الدليل، وتحوّلها إلى مهمّة قابلة للمتابعة بدورة حياة صريحة. */}
      {selected && fieldMode === 'expert' && (
        <FieldObjectivePanel
          contextKey={fieldId}
          availability={objectiveAvailability}
          onCreateTask={(objectiveId) => {
            // مسار المهمّة الحيّ الوحيد في MapHub: فتح وضع تثبيت دليل ميدانيّ لكشف الإجهاد.
            // نعيد false لأيّ هدف لا نملك له مسار تنفيذ حيّ هنا حتّى لا تتقدّم دورة الحياة كذباً.
            if (objectiveId === 'diagnose_field_stress') {
              setPinMode(true); setCompare(false); setDrawTools(false);
              return true;
            }
            return false;
          }}
        />
      )}

      {/* التقويم الزراعيّ اليمنيّ (display_only — سياق تراثيّ لا يدخل القرار): المنزلة
          القمريّة + الشهر الحميريّ + أمثال المنزلة + نافذة زراعة محصول الحقل. كان
          backend كاملاً (calendars/proverbs) بلا أيّ قارئ — التميّز المحلّيّ لساهول. */}
      {selected && <YemeniCalendarCard cropLabel={selected.crop} />}

      {selected && fieldMode === 'expert' && (
        <FieldViewInsightStrip
          fieldId={fieldId}
          fieldName={selected.name}
          crop={selected.crop}
          areaHa={typeof selected.area === 'number' ? selected.area : null}
          imageryDates={availableImageryDates}
          activeAlertsCount={Array.isArray(alertsQ.data) ? alertsQ.data.length : undefined}
          openTasksCount={Array.isArray(tasksQ.data?.tasks) ? tasksQ.data.tasks.length : undefined}
          equipmentCount={Array.isArray(equipmentQ.data) ? equipmentQ.data.length : undefined}
          weatherReady={!!weatherQ.data?.current}
          agentContextReady={!!fieldId}
          routeFieldIsInvalid={routeFieldIsInvalid}
          storedFieldIsInvalid={storedFieldIsInvalid}
          selectionReason={selectionReason}
          onBackfill={mutateAllowed ? handlePrepareTwoYearImagery : undefined}
          onOpenTimeline={() => setShowImageryTimeline(true)}
          onShowAlerts={() => setShowAlerts(true)}
        />
      )}

      {selected && fieldMode === 'expert' && (
        <ZoneVraEntryCard
          hasField={!!fieldId}
          imageryReadyCount={imageryReadyCount}
          prescriptionCount={prescriptionsQ.data?.total ?? 0}
          onOpenZones={() => { setZoneDesigner(true); setShowPivots(true); }}
        />
      )}

      {selected && fieldMode === 'expert' && (
        <OperationsCenterCard
          fieldId={fieldId ?? null}
          tasks={tasksQ.data?.tasks ?? []}
          equipment={equipmentQ.data ?? []}
          alerts={Array.isArray(alertsQ.data) ? alertsQ.data : []}
          onOpenAlerts={() => setShowAlerts(true)}
        />
      )}

      {selected && fieldMode === 'expert' && (
        <FieldEconomicsCard
          areaHa={typeof selected.area === 'number' ? selected.area : null}
          irrigationMm={waterEfficiencyQ.data?.efficiency?.irrigation_mm_total ?? null}
        />
      )}

      {/* ربحيّة الموسم من السجلّ الفعليّ (farm-ledger) — أرقام مُخزَّنة لا تقدير، بعكس البطاقة أعلاه. */}
      {selected && fieldMode === 'expert' && (
        <SeasonProfitabilityCard
          hasSeason={!!activeSeasonId}
          profitability={profitabilityQ.data ?? null}
          summary={ledgerSummaryQ.data ?? null}
          variance={varianceQ.data ?? null}
          economicState={economicStateQ.data ?? null}
          areaHa={typeof selected.area === 'number' ? selected.area : null}
          loading={profitabilityQ.isLoading || ledgerSummaryQ.isLoading}
        />
      )}

      {/* إدخال السجلّ الماليّ (عمليّة/موازنة/إيراد): يكتمل به قوس الربحيّة إدخالاً —
          كانت نقاط POST بلا واجهة (الإدخال API فقط). للخبير المخوَّل بالتعديل فقط. */}
      {selected && fieldMode === 'expert' && mutateAllowed && (
        <LedgerEntryCard
          fieldId={fieldId ?? null}
          seasonId={activeSeasonId}
          todayIso={new Date().toISOString().slice(0, 10)}
          enabled={expertMode}
        />
      )}

      {selected && fieldMode === 'expert' && (
        <FieldScoutingCard
          crop={selected.crop}
          issues={scoutingQ.data?.issues ?? []}
          loading={scoutingQ.isLoading}
          onLogEvidence={() => { setPinMode(true); setCompare(false); setDrawTools(false); }}
        />
      )}

      {selected && fieldMode === 'expert' && (
        <SeasonCommandCard
          phenology={phenologyQ.data ?? null}
          stageAction={stageActionsQ.data?.available ? (stageActionsQ.data.suggestions?.[0]?.action_ar ?? null) : null}
          loading={phenologyQ.isLoading}
        />
      )}

      {/* بطاقة المحصول: تعكس المعرفة المرجعيّة المُخزَّنة (crop-cards YAML — Kc/ملوحة/GDD/
          أصناف يمنيّة) على محصول الحقل النشط — كانت قدرة خلفيّة يتيمة عن الواجهة. */}
      {selected && fieldMode === 'expert' && (
        <CropKnowledgeCard
          cropLabel={selected.crop}
          sowingDate={activeSeason?.sowing_date ?? null}
          enabled={expertMode}
        />
      )}

      {selected && fieldMode === 'expert' && (
        <TraceabilityCard
          fieldName={selected.name}
          crop={selected.crop}
          areaHa={typeof selected.area === 'number' ? selected.area : null}
          season={activeSeason}
          completedOps={completedOps}
          irrigationMm={waterEfficiencyQ.data?.efficiency?.irrigation_mm_total ?? null}
          prescriptionCount={prescriptionsQ.data?.total ?? null}
        />
      )}

      {/* بطاقة المعرفة الزراعيّة: الإكثار المناسب للمحصول + ممارسات ما بعد الحصاد +
          (للبنّ فقط) دليل/أصناف/آفات البنّ اليمنيّ — كانت طبقة خلفيّة يتيمة. */}
      {selected && fieldMode === 'expert' && (
        <AgroKnowledgeCard cropLabel={selected.crop} enabled={expertMode} />
      )}

      {/* حاسبات قياس حقليّة (إنبات · تخزين بذور · عمق بذر · رطوبة حبوب · ارتفاع البنّ)
          — من قياسات المستخدم الفعليّة فقط، لا افتراضات. */}
      {selected && fieldMode === 'expert' && (
        <AgroCalculatorsCard cropLabel={selected.crop} />
      )}

      {/* منضدة التشخيص الحقليّ: أعراض ⇒ مرشّحون مرتّبون (تشخيص أوّليّ لا قاطع) +
          خطط IPM المتدرّجة (الكيميائيّ ملاذ أخير) + تقييم ملوحة FAO من قياسات المستخدم. */}
      {selected && fieldMode === 'expert' && (
        <DiagnosticsCard fieldId={fieldId ?? null} cropLabel={selected.crop} enabled={expertMode} />
      )}

      {/* حوكمة التربة: الحلقة المغلقة الكنسيّة (soil-service P4) — مستوى الأدلّة وبوّابة
          الجودة والاستخدامات المحجوبة وعدّادات التنفيذ/التحقّق/التعلّم. قراءة فقط. */}
      {selected && fieldMode === 'expert' && (
        <SoilGovernanceCard fieldId={fieldId ?? null} enabled={expertMode} />
      )}
      {/* شفافيّة متحكّم الريّ الهرميّ (MPC) — قدرات مُنمذَجة/مُؤجَّلة + توصية-فقط. قراءة فقط. */}
      {selected && fieldMode === 'expert' && (
        <MpcGovernanceCard enabled={expertMode} />
      )}

      {/* سيناريوهات «ماذا لو؟»: حرارة/مطر/تاريخ زراعة/توأم ماء — محاكاة افتراضات
          المستخدم، الخادم يعلن أنّها ليست تنبّؤاً معايَراً والإخلاء يُعرَض بارزاً. */}
      {selected && fieldMode === 'expert' && (
        <WhatIfScenariosCard
          fieldId={fieldId ?? null}
          cropLabel={selected.crop}
          areaHa={typeof selected.area === 'number' ? selected.area : null}
          enabled={expertMode}
        />
      )}

      {/* «ماذا أزرع؟»: اقتراح الدورة الزراعيّة + ملاءمة الشهر — planting/rotation
          كانت بلا مسار عمليّ في الواجهة. أحكام الخادم تُعرَض لا يُعاد الحكم. */}
      {selected && fieldMode === 'expert' && (
        <PlantingAdvisorCard
          cropLabel={selected.crop}
          todayIso={new Date().toISOString().slice(0, 10)}
          enabled={expertMode}
        />
      )}

      {/* مخاطر المناخ والماء: حساسيّة المراحل المائيّة (FAO-56) + نوافذ المخاطر الموسميّة
          وساعات البرودة (إقليم يختاره المستخدم) + المناطق المشابهة — كانت بلا قارئ. */}
      {selected && fieldMode === 'expert' && (
        <ClimateRiskCard fieldId={fieldId ?? null} cropLabel={selected.crop} enabled={expertMode} />
      )}

      {/* حصاد المياه وطريقة الريّ: إمكانات حصاد المطر (من قياس المستخدم) + الطرق
          التراثيّة اليمنيّة ودليلها + ملامح طرق الريّ FAO — كان backend بلا قارئ. */}
      {selected && fieldMode === 'expert' && (
        <WaterHarvestingCard cropLabel={selected.crop} enabled={expertMode} />
      )}

      {/* مساعدات قرار الريّ والعيّنات: ثقة القراءة/التوصية + قرار رطوبة RWC +
          الإجمالي المسحوب + مراجع العيّنة — نقاط P0/P1 كانت بلا قارئ واجهة. */}
      {selected && fieldMode === 'expert' && (
        <IrrigationDecisionAidsCard cropLabel={selected.crop} enabled={expertMode} />
      )}

      {/* مرشَّح توصية الريّ الواعي بالاستنزاف (WS-D.2): POST
          /api/v1/fields/{id}/irrigation-recommendation — توصية مرشَّحة لا مُنفَّذة
          (الملكيّة لخدمة القرار)؛ يعالج insufficient_data/inconsistent_state بصدق. */}
      {selected && fieldMode === 'expert' && (
        <IrrigationDecisionCard fieldId={fieldId ?? null} cropLabel={selected.crop} enabled={expertMode} />
      )}

      {/* سلامة المدخلات ومعرفة المحاصيل: فحص كيميائيّ (حكم الخادم حرفيّاً) + تقويم
          الزراعة + آفات التخزين + عالية القيمة/المتخصّصة ومرشّحو الإدخال — P1 بلا قارئ. */}
      {selected && fieldMode === 'expert' && (
        <CropSafetyKnowledgeCard cropLabel={selected.crop} enabled={expertMode} />
      )}

      {/* التحليلات الزراعيّة-البيئيّة: مخاطر/دورة/دليل قرارات + سلسلة Kc (قراءة وحفظاً)
          + تغذية راجعة نبات-تربة + مقارنة مواسم + تصعيد + نسب أصل الحقل. */}
      {selected && fieldMode === 'expert' && (
        <AgroAnalyticsCard fieldId={fieldId ?? null} cropLabel={selected.crop} enabled={expertMode} />
      )}

      {/* عمليّات الماء والحقل: إجهاد/نصيحة متكاملة + ميزان FAO-56 + سيول واردة +
          تحليل ماء الريّ + تنبيهات/طبقات الطقس + خطّة 4R + إدامة النتيجة + geo-locate. */}
      {selected && fieldMode === 'expert' && (
        <WaterFieldOpsCard fieldId={fieldId ?? null} cropLabel={selected.crop} enabled={expertMode} />
      )}

      {/* المحاصيل المتخصّصة والتوقيت التراثيّ: عالية القيمة/متخصّصة/عطريّة/أعلاف + بطاقة
          الإدخال وملاءمة الحقل + تخطيط البستان واقتصاده + النجوم/التقويم الثقافيّ/الإقليميّ. */}
      {selected && fieldMode === 'expert' && (
        <SpecialtyCropsCard cropLabel={selected.crop} enabled={expertMode} />
      )}

      {/* المديريّات والطقس والتهيئة: معرفة إقليميّة (نوافذ الآفات) + توصية موقع +
          ملخّص طقس الحقل وتحليلات السجلّ ودليل الزراعة + استبيان التهيئة. */}
      {selected && fieldMode === 'expert' && (
        <DistrictsWeatherCard fieldId={fieldId ?? null} cropLabel={selected.crop} enabled={expertMode} />
      )}

      {/* اتّساق البيانات والدورة وWOFOST والعمليّات: فحوص الاتّساق (ريّ + حداثة) +
          تقييم الدورة ومبادئها + إرشاد تكيّف WOFOST + تقرير العمليّات + توصية ريّ +
          الحالة التشغيليّة + تحسين المحفظة + التحقّق من الهندسة. */}
      {selected && fieldMode === 'expert' && (
        <AgronomyConsistencyCard fieldId={fieldId ?? null} cropLabel={selected.crop} enabled={expertMode} />
      )}

      {/* المعرفة الزراعيّة الاختصاصيّة (P3): ملاءمة المحاصيل + تركيب حالة (dry-run) +
          الإكثار الخضري والأصل + الأساليب + صمود الجفاف + تقييم البذار + العيّنات. */}
      {selected && fieldMode === 'expert' && (
        <CropPropagationCard cropLabel={selected.crop} enabled={expertMode} />
      )}

      {/* عمليّات GIS الهندسيّة + التحكيم الزمني + محاكاة ماذا-لو + مخاطر المرحلة +
          إعادة البناء + رابط النَّسَب + تحليل التجارب (P3، خلف أعلام ميزات). */}
      {selected && fieldMode === 'expert' && (
        <GisTemporalOpsCard fieldId={fieldId ?? null} cropLabel={selected.crop} enabled={expertMode} />
      )}

      {/* التعلُّم والدليل (P3، إرشاديّ صرف): تفعيل التعلُّم · معايرة · مزج سابقة · عتبات ·
          تغذية راجعة · تظافر قرائن · بوّابة ثقة · تسجيل مشاهدة · طبقات · تغطية مؤشّرات. */}
      {selected && fieldMode === 'expert' && (
        <LearningEvidenceCard fieldId={fieldId ?? null} cropLabel={selected.crop} enabled={expertMode} />
      )}

      {/* مراجعة الحدود: تهديف ثقة حتميّ (يُخزَّن) + شبكة جوار — backend حوكمة الحدود
          كان أقوى من الواجهة (score/graph بلا قارئ). */}
      {selected && fieldMode === 'expert' && (
        <BoundaryReviewCard fieldId={fieldId ?? null} enabled={expertMode} mutateAllowed={mutateAllowed} />
      )}

      {/* بطاقة ذكاء الحقل الموحّدة (V65): تجمع أحدث مشهد/حالة المزوّدين/NDVI-تاريخيّ/
          العجز المائيّ/التنبيهات/الثقة في بطاقة واحدة، مع إظهار المفقود صراحةً. */}
      {selected && fieldMode === 'expert' && (
        <FieldIntelligenceCardView fieldId={fieldId ?? null} enabled={expertMode} />
      )}
      {/* بطاقة الرياح السائدة + المصدّات (V73-UI): من أين تأتي الرياح غالباً؟ وكيف أوجّه
          مصدّاً شجريّاً؟ من تاريخ NASA POWER — صدق: المحسوب بقيمته والمتعذّر بسببه. */}
      {selected && fieldMode === 'expert' && (
        <WindbreakCard fieldId={fieldId ?? null} enabled={expertMode} />
      )}
      {/* خطر انجراف الرشّ (V79-UI): الحقول المجاورة كمناطق حسّاسة + هل الرشّ ينجرف نحوها
          downwind من الريح السائدة — «لا ترشّ نحو X الآن». صدق: بلا ريح/جوار يُعلَن. */}
      {selected && fieldMode === 'expert' && (
        <DriftRiskCard fieldId={fieldId ?? null} enabled={expertMode} />
      )}
      {/* رسم أدلّة الحقل (V74-UI): أدلّة حاضرة بمصادرها + فجوات معرفة بأسبابها —
          يفسّر التوصية ويُثبت مصدر كلّ معلومة (يعيد استخدام استعلام analyze). */}
      {selected && fieldMode === 'expert' && (
        <EvidenceGraphCard fieldId={fieldId ?? null} enabled={expertMode} />
      )}
      {/* تاريخ الأدلّة (E1-UI): تطوّر الأدلّة/الفجوات/الثقة عبر اللقطات المحفوظة +
          أكثر الفجوات تكراراً عبر الحقول (تحليلات v149). صدق: بلا لقطات/تحليلات يُعلَن. */}
      {selected && fieldMode === 'expert' && (
        <EvidenceHistoryCard fieldId={fieldId ?? null} enabled={expertMode} />
      )}
      {/* بطاقة أدلّة الموسم (الحقيقة التشغيليّة الموحّدة field_season_state_projection) —
          تُعرَض عند وجود موسم نشط للحقل المحدَّد في وضع الخبير. */}
      {selected && fieldMode === 'expert' && activeSeasonId && (
        <SeasonEvidenceCard
          fieldId={fieldId ?? null}
          seasonId={activeSeasonId}
          enabled={expertMode}
        />
      )}

      {/* تتبّع الحصاد المُخزَّن: دفعات + سلسلة حيازة append-only + دفتر مدخلات —
          كان backend v65 كاملاً (harvest-lots/custody/input-traceability) بلا قارئ واجهة. */}
      {selected && fieldMode === 'expert' && (
        <HarvestTraceabilityCard
          fieldId={fieldId ?? null}
          seasonId={activeSeasonId}
          enabled={expertMode}
        />
      )}

      {/* P3: مقارنات طبقات جاهزة ذات معنى زراعيّ — تظهر في وضع المقارنة وتُوجّه المحرّك القائم. */}
      {compare && (
        <div className="mb-3 flex flex-wrap items-center gap-1.5" data-testid="compare-presets">
          {/* مبدّل نمط المقارنة: مؤشّران في تاريخ واحد ↔ مؤشّر واحد بين تاريخَين (مقارنة زمنيّة). */}
          <div className="flex items-center gap-1" data-testid="compare-mode-toggle">
            {(['indicators', 'dates'] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setCompareMode(m)}
                className="px-2 py-1 rounded-lg text-[11px] font-semibold border"
                style={{ borderColor: compareMode === m ? '#22c55e88' : T.line, color: T.ink, background: compareMode === m ? '#14532d' : T.card }}
              >
                {m === 'indicators' ? 'مؤشّران' : 'تاريخان'}
              </button>
            ))}
          </div>
          {compareMode === 'indicators' ? (
            <>
              <span className="text-[11px] font-bold" style={{ color: T.muted }}>مقارنات جاهزة:</span>
              {buildComparePresets(INDICATOR_LAYERS.map((l) => l.id)).map((p) => {
                const active = leftLayer === p.left && rightLayer === p.right;
                return (
                  <button
                    key={p.id}
                    type="button"
                    title={p.why}
                    onClick={() => { setLeftLayer(p.left); setRightLayer(p.right); }}
                    className="px-2 py-1 rounded-lg text-[11px] font-semibold border"
                    style={{ borderColor: active ? '#22c55e88' : T.line, color: T.ink, background: active ? '#14532d' : T.card }}
                  >
                    {p.label}
                  </button>
                );
              })}
            </>
          ) : (
            <div className="flex items-center gap-1.5" data-testid="compare-dates-indicator">
              <span className="text-[11px] font-bold" style={{ color: T.muted }}>المؤشّر:</span>
              <LayerSwitcher layers={INDICATOR_LAYERS.map((l) => ({ id: l.id, label: LAYER_LEGEND[l.id]?.short ?? l.label }))} active={leftLayer} onChange={setLeftLayer} />
              <span className="text-[11px]" style={{ color: T.muted }}>— قارِنه بين تاريخَين مخزَّنَين.</span>
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3" data-testid="maphub-summary">
        <SummaryStat label="إجمالي الحقول" value={String(fields.length)} />
        <SummaryStat label="المساحة الكلية" value={`${fieldSummary.totalArea.toFixed(1)} هـ`} />
        <SummaryStat label="محاصيل مختلفة" value={String(fieldSummary.cropCount)} />
        <SummaryStat label="حقول بهندسة" value={`${fieldSummary.withGeometry}/${fields.length}`} />
      </div>

      <RoleAwareMapSurface role={user?.role}>
        <FieldContextStrip
          fieldId={fieldId}
          fieldName={selected?.name ?? null}
          cropName={selected?.crop ?? null}
          activeSeasonId={activeSeasonId}
          activeLayerId={indicatorActive}
        />

        <PriorityQueuePanel
          fieldId={fieldId}
          activeSeasonId={activeSeasonId}
          hasAlerts={alertMarkers.length > 0}
          hasTasks={operationalMarkers.length > 0}
          hasWeatherWindow={Boolean(weatherMarker)}
        />

        <MapActionPalette
          fieldId={fieldId}
          canMutate={mutateAllowed}
          hasGeometry={Boolean(selected?.geometry)}
          hasActiveSeason={Boolean(activeSeasonId)}
          hasAlerts={alertMarkers.length > 0}
          hasTasks={operationalMarkers.length > 0}
          onPinScouting={() => { setPinMode(true); setDrawTools(false); }}
          onOpenTimeline={() => setShowImageryTimeline(true)}
          onOpenAlerts={() => setShowAlerts(true)}
          onAddField={() => setShowAddField(true)}
        />
      </RoleAwareMapSurface>

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

          {/* ── العمود المركزيّ: أدوات + خريطة ──
              min-w-0: مسار الشبكة 1fr افتراضه min-width:auto، فيُتيح لشريط الصور
              (overflow-x-auto) أن يوسّع المسار بدل التمرير — ما يغيّر عرض الخريطة
              ويكسر تمرير الشريط. min-w-0 يحصر التمرير داخل الشريط ويثبّت عرض الخريطة. */}
          <div className="space-y-3 min-w-0">
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

            {indicatorActive === RAW_IMAGERY_INDEX_ID && trueColorRuntime.state !== 'ready' && (
              <Card pad={10}>
                <div dir="rtl" data-testid="truecolor-runtime-readiness" className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="text-xs font-bold" style={{ color: trueColorRuntime.state === 'checking' ? '#93c5fd' : '#fbbf24' }}>
                      تحقق صورة الحقل الخام
                    </div>
                    <div className="text-[11px] mt-1" style={{ color: T.faint }}>{trueColorRuntime.message}</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => handlePrepareTwoYearImagery(24)}
                    disabled={historicalBackfillBusy || !selected?.geometry}
                    className="px-2 py-1 rounded-lg text-xs font-semibold disabled:opacity-60 disabled:cursor-not-allowed"
                    style={{ background: historicalBackfillBusy ? '#475569' : '#854d0e', border: '1px solid #f59e0b66', color: '#fff7ed' }}
                    data-testid="truecolor-backfill-cta"
                  >
                    {historicalBackfillBusy ? 'جارٍ التجهيز…' : 'تجهيز صورة TrueColor'}
                  </button>
                </div>
              </Card>
            )}

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

                  {!compare && activeIndicator && fieldId && (
                    <div className="flex items-center gap-2" data-testid="two-year-imagery-backfill">
                      <button
                        type="button"
                        onClick={() => handlePrepareTwoYearImagery(24)}
                        disabled={historicalBackfillBusy || !selected?.geometry}
                        className="px-2 py-1 rounded-lg text-xs font-semibold disabled:opacity-60 disabled:cursor-not-allowed"
                        style={{ background: historicalBackfillBusy ? '#475569' : '#854d0e', border: '1px solid #f59e0b66', color: '#fff7ed' }}
                        title="يشغّل backfill تاريخي؛ اختر 3 أو 6 أو 12 أو 24 شهر"
                      >
                        {historicalBackfillBusy ? 'جارٍ التجهيز…' : 'تجهيز 24 شهر'}
                      </button>
                      <div className="flex items-center gap-1" data-testid="imagery-backfill-month-options">
                        {BACKFILL_MONTH_OPTIONS.map((months) => (
                          <button
                            key={months}
                            type="button"
                            onClick={() => handlePrepareTwoYearImagery(months)}
                            disabled={historicalBackfillBusy || !selected?.geometry}
                            className="px-2 py-1 rounded-lg text-[11px] font-semibold disabled:opacity-60"
                            style={{ background: T.card, border: `1px solid ${T.line}`, color: T.muted }}
                            title={`تجهيز ${months} شهر من الصور التاريخية`}
                          >
                            {months} شهر
                          </button>
                        ))}
                      </div>
                      {historicalBackfillStatus && (
                        <span className="text-[11px] max-w-[260px] truncate" style={{ color: T.faint }} title={historicalBackfillStatus}>
                          {historicalBackfillStatus}
                        </span>
                      )}
                    </div>
                  )}

                  {!compare && activeIndicator && dateSelectorDates.length > 0 && (
                    <div className="flex items-center gap-2" data-testid="imagery-date-switcher">
                      <span className="text-xs font-semibold" style={{ color: T.muted }}>المشهد</span>
                      <select
                        value={selectedImageryDate}
                        onChange={(e) => handleSelectImageryTimelineItem(e.target.value)}
                        className="px-2 py-1 rounded-lg text-xs"
                        style={{ background: T.card, border: `1px solid ${T.line}`, color: T.ink }}
                        aria-label="تاريخ صورة القمر الصناعي"
                      >
                        <option value="latest">الأحدث</option>
                        {dateSelectorDates.map((d) => (
                          <option key={d.date} value={d.date}>
                            {d.date}{typeof d.cloud_pct === 'number' ? ` · غيوم ${Math.round(d.cloud_pct)}%` : ''}{d.has_cog ? ' · جاهز' : ''}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        onClick={() => setShowImageryTimeline((v) => !v)}
                        className="px-2 py-1 rounded-lg text-xs font-semibold"
                        style={{ background: showImageryTimeline ? '#14532d' : T.card, border: `1px solid ${showImageryTimeline ? '#22c55e66' : T.line}`, color: showImageryTimeline ? '#bbf7d0' : T.ink }}
                        data-testid="two-year-imagery-timeline-toggle"
                        title="يعرض كل المشاهد الجاهزة التي تم سحبها، وليس شهر يوليو فقط"
                      >
                        Timeline الصور
                      </button>
                    </div>
                  )}

                  {!compare && activeIndicator && acquisitionLabel && (
                    <div
                      className="flex items-center gap-1 text-xs"
                      style={{ color: T.muted }}
                      data-testid="imagery-acquisition-date"
                    >
                      <Satellite className="w-3.5 h-3.5" style={{ color: T.green }} />
                      <span>تاريخ الالتقاط: {acquisitionLabel}</span>
                    </div>
                  )}

                  <FieldTimelineShell
                    fieldId={fieldId}
                    activeSeasonId={activeSeasonId}
                    kind="imagery"
                    visible={!compare && Boolean(activeIndicator) && showImageryTimeline && twoYearTimeline.items.length > 0}
                  >
                    <div
                      className="w-full rounded-xl border p-3"
                      style={{ background: '#0f172acc', borderColor: T.line }}
                      data-testid="two-year-imagery-timeline"
                    >
                      <div className="flex flex-wrap items-center gap-2 justify-between mb-3">
                        <div className="flex items-center gap-2">
                          <History className="w-4 h-4" style={{ color: T.green }} />
                          <div>
                            <div className="text-xs font-bold" style={{ color: T.ink }}>Timeline الصور الجوية · السلسلة التاريخية</div>
                            <div className="text-[11px]" style={{ color: T.faint }}>
                              {twoYearTimeline.items.length} مشهد · جاهز {twoYearTimeline.ready} · قيد التجهيز {twoYearTimeline.pending}
                              {twoYearTimeline.avgCloud != null ? ` · متوسط غيوم ${Math.round(twoYearTimeline.avgCloud)}%` : ''}
                            </div>
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => setSelectedImageryDate('latest')}
                          className="px-2 py-1 rounded-lg text-[11px]"
                          style={{ background: T.card, border: `1px solid ${T.line}`, color: T.muted }}
                        >
                          الأحدث
                        </button>
                      </div>
                      <div className="flex gap-2 overflow-x-auto pb-1" data-testid="imagery-timeline-items">
                        {twoYearTimeline.items.map((d) => {
                          const cloud = typeof d.cloud_pct === 'number' ? d.cloud_pct : (typeof d.cloud_cover === 'number' ? d.cloud_cover : null);
                          const active = selectedImageryDate === d.date;
                          return (
                            <button
                              key={`${d.date}-${d.scene_id ?? 'scene'}`}
                              type="button"
                              onClick={() => handleSelectImageryTimelineItem(d.date, d)}
                              className="min-w-[132px] rounded-xl border px-3 py-2 text-right"
                              style={{ background: active ? '#123524' : '#111827', borderColor: active ? '#22c55e99' : T.line, color: T.ink }}
                              title={d.scene_id ?? d.date}
                            >
                              {/* مصغّرة فقط لتاريخ محفوظ (has_cog): تواريخ المزوّد المعلّقة
                                  «تنتظر COG» بلا صورة. المؤشّر: truecolor إن كان محفوظاً لهذا
                                  التاريخ، وإلّا أوّل مؤشّر محفوظ — فلا مصغّرة truecolor فارغة
                                  لتاريخ له مؤشّر تحليليّ فقط. */}
                              {selected && d.has_cog && (
                                <div className="mb-2 h-16 w-full overflow-hidden rounded-lg border" style={{ borderColor: active ? '#22c55e66' : '#334155', background: '#020617' }}>
                                  <img
                                    src={fieldCdseThumbnailUrl(
                                      selected.id,
                                      d.indices?.includes('truecolor') ? 'truecolor' : (d.indices?.[0] ?? activeIndicator ?? 'ndvi'),
                                      d.date,
                                      tenantId ?? null,
                                      selected.geometry ?? null,
                                      null,
                                      160,
                                    )}
                                    alt={`مصغّرة صورة الحقل ${d.date}`}
                                    className="h-full w-full object-cover"
                                    loading="lazy"
                                    onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
                                  />
                                </div>
                              )}
                              <div className="flex items-center justify-between gap-2">
                                <span className="text-xs font-bold">{d.date}</span>
                                <span className="text-[10px]" style={{ color: T.faint }}>{monthLabel(d.date)}</span>
                                <span className="h-2.5 w-2.5 rounded-full" style={{ background: cloudBandColor(cloud) }} />
                              </div>
                              <div className="mt-1 flex items-center justify-between text-[10px]" style={{ color: T.faint }}>
                                <span>{cloud != null ? `غيوم ${Math.round(cloud)}%` : 'غيوم —'}</span>
                                <span>{d.has_cog ? 'جاهز' : 'ينتظر COG'}</span>
                              </div>
                            </button>
                          );
                        })}
                      </div>
                      {selectedScene && <SceneProvenanceCard scene={selectedScene} />}
                    </div>
                  </FieldTimelineShell>

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
                    <MapHubToolToggle testid="btn-compare" active={compare} onClick={() => { setCompare((v) => !v); setPinMode(false); setDrawTools(false); setPivotDesigner(false); setZoneDesigner(false); }} icon={compare ? <Columns2 className="w-3.5 h-3.5" /> : <Square className="w-3.5 h-3.5" />} label="مقارنة" />
                    {/* حصر متبادل: الرسم/القياس والدبابيس يستهلكان نقرات الخريطة معاً، فتفعيل
                        أحدهما يُعطّل الآخر (والمقارنة) — وإلّا كلّ نقرة قياس تُسقط دبّوساً بالخطأ. */}
                    <MapHubToolToggle testid="btn-draw" active={drawTools} onClick={() => { setDrawTools((v) => !v); setPinMode(false); setCompare(false); setPivotDesigner(false); setZoneDesigner(false); }} icon={<Ruler className="w-3.5 h-3.5" />} label="رسم/قياس" />
                    <MapHubToolToggle testid="btn-pins" active={pinMode} onClick={() => { setPinMode((v) => !v); setCompare(false); setDrawTools(false); setPivotDesigner(false); setZoneDesigner(false); }} icon={<Crosshair className="w-3.5 h-3.5" />} label="دبابيس" />
                    <MapHubToolToggle testid="btn-pivot-designer" active={pivotDesigner} onClick={() => { setPivotDesigner((v) => !v); setPinMode(false); setCompare(false); setDrawTools(false); setShowPivots(true); setZoneDesigner(false); }} icon={<Target className="w-3.5 h-3.5" />} label="تصميم Pivot" />
                    <MapHubToolToggle testid="btn-zone-designer" active={zoneDesigner} onClick={() => { setZoneDesigner((v) => !v); setPivotDesigner(false); setPinMode(false); setCompare(false); setDrawTools(false); setShowPivots(true); }} icon={<Combine className="w-3.5 h-3.5" />} label="Zones" />
                  </div>
                </div>

                <OperationalOverlayControls
                  isVisible={!compare}
                  showWeather={showWeather}
                  showAlerts={showAlerts}
                  showDevices={showDevices}
                  showEquipment={showEquipment}
                  showTasks={showTasks}
                  showPivots={showPivots}
                  showHillshade={showHillshade}
                  showSlope={showSlope}
                  showContours={showContours}
                  showSoil={showSoil}
                  showSoilSamples={showSoilSamples}
                  soilSamplesBusy={soilSamplesBusy}
                  selectedHasGeometry={!!selected?.geometry}
                  selectedHasPoint={!!selectedPoint}
                  alertsUnplaceable={alertsUnplaceable}
                  devicesUnplaceable={devicesUnplaceable}
                  equipmentUnplaceable={equipmentUnplaceable}
                  tasksUnplaceable={tasksUnplaceable}
                  pivotMarkersCount={pivotMarkers.length}
                  soilSamplesNote={soilSamplesNote}
                  hillshadeUnavailableMessage={showHillshade && hillshadeTj && !hillshadeTj.available ? (hillshadeTj.user_message || 'التضاريس غير مُهيّأة — لا نموذج ارتفاع (DEM).') : null}
                  slopeUnavailableMessage={showSlope && slopeTj && !slopeTj.available ? (slopeTj.user_message || 'طبقة الانحدار غير مُهيّأة — لا نموذج ارتفاع (DEM).') : null}
                  contoursNote={contoursNote}
                  isOverlayBlocked={isOverlayBlocked}
                  overlayBlockedTitle={overlayBlockedTitle}
                  setShowWeather={setShowWeather}
                  setShowAlerts={setShowAlerts}
                  setShowDevices={setShowDevices}
                  setShowEquipment={setShowEquipment}
                  setShowTasks={setShowTasks}
                  setShowPivots={setShowPivots}
                  setShowHillshade={setShowHillshade}
                  setShowSlope={setShowSlope}
                  setShowContours={setShowContours}
                  setShowSoil={setShowSoil}
                  setShowSoilSamples={setShowSoilSamples}
                />

                {/* أسطورة الانحدار (Slope) — من tilejson.legend حين الطبقة مُفعَّلة ومتاحة (المهمّة C) */}
                {!compare && showSlope && slopeTj?.available && slopeTj.legend && slopeTj.legend.length > 0 && (
                  <div className="flex flex-wrap items-center gap-3 mt-2" data-testid="slope-legend">
                    <span className="text-xs font-semibold" style={{ color: T.muted }}>مفتاح الانحدار</span>
                    {slopeTj.legend.map((s, i) => (
                      <span key={`slope-legend-${i}`} className="inline-flex items-center gap-1 text-[11px]" style={{ color: T.faint }}>
                        <span style={{ width: 12, height: 12, borderRadius: 3, background: s.color, border: `1px solid ${T.line}`, display: 'inline-block' }} />
                        {s.label}
                      </span>
                    ))}
                  </div>
                )}

                {/* لوحة التربة (SoilGrids) — خاصّيّة + عمق + إخلاء مسؤوليّة إلزاميّ + أسطورة (المهمّة B) */}
                {!compare && showSoil && (
                  <div data-testid="soil-panel" className="mt-3 pt-3 space-y-2" style={{ borderTop: `1px solid ${T.line}` }}>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-semibold" style={{ color: T.muted }}>طبقة التربة (SoilGrids)</span>
                      <label className="text-[11px] grid gap-1" style={{ color: T.muted }}>
                        الخاصّيّة
                        <select
                          data-testid="soil-property-select"
                          value={soilProperty}
                          onChange={(e) => setSoilProperty(e.target.value as SoilProperty)}
                          className="px-2 py-1 rounded-lg text-xs"
                          style={{ background: T.card, border: `1px solid ${T.line}`, color: T.ink }}
                        >
                          {SOIL_PROPERTIES.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
                        </select>
                      </label>
                      <label className="text-[11px] grid gap-1" style={{ color: T.muted }}>
                        العمق
                        <select
                          data-testid="soil-depth-select"
                          value={soilDepth}
                          onChange={(e) => setSoilDepth(e.target.value)}
                          className="px-2 py-1 rounded-lg text-xs"
                          style={{ background: T.card, border: `1px solid ${T.line}`, color: T.ink }}
                        >
                          {SOIL_DEPTHS.map((d) => <option key={d} value={d}>{d}</option>)}
                        </select>
                      </label>
                      {soilTj?.available && (
                        <Pill tone="ok">{soilTj.name_ar}{soilTj.unit ? ` · ${soilTj.unit}` : ''}</Pill>
                      )}
                    </div>

                    {/* حالة صادقة: المصدر غير مُهيّأ (available:false) ⇒ رسالة الخادم (لا بلاطة) */}
                    {soilTj && !soilTj.available && (
                      <div className="text-[11px]" data-testid="soil-unavailable" style={{ color: T.faint }}>
                        {soilTj.user_message || 'طبقة التربة غير متاحة — مصدر SoilGrids غير مُهيّأ.'}
                      </div>
                    )}

                    {/* أسطورة التربة (قيمة + لون) — من tilejson.legend حين الطبقة متاحة */}
                    {soilTj?.available && soilTj.legend && soilTj.legend.length > 0 && (
                      <div className="flex flex-wrap items-center gap-3" data-testid="soil-legend">
                        <span className="text-xs font-semibold" style={{ color: T.muted }}>مفتاح التربة</span>
                        {soilTj.legend.map((s, i) => (
                          <span key={`soil-legend-${i}`} className="inline-flex items-center gap-1 text-[11px]" style={{ color: T.faint }}>
                            <span style={{ width: 12, height: 12, borderRadius: 3, background: s.color, border: `1px solid ${T.line}`, display: 'inline-block' }} />
                            {s.value}
                          </span>
                        ))}
                      </div>
                    )}

                    {/* إخلاء المسؤوليّة الإلزاميّ — يُعرَض دوماً حين الطبقة مفعّلة (صدق صارم:
                        SoilGrids تقدير ~250م لإرشاد أخذ العيّنات فقط، لا بديل عن مختبر). */}
                    {soilTj?.disclaimer && (
                      <div
                        data-testid="soil-disclaimer"
                        className="text-[11px] rounded-lg px-2 py-1.5"
                        style={{ color: T.warn, background: 'rgba(234,179,8,.08)', border: `1px solid ${T.line}` }}
                      >
                        ⚠️ {soilTj.disclaimer}
                      </div>
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
                      (تُحفَظ على الخادم وتبقى عبر الجلسات؛ «مسح» يزيل غير المحفوظ فقط)
                    </span>
                  </div>
                )}

                {zoneDesigner && (
                  <div data-testid="zone-designer-panel" className="mt-3 pt-3 space-y-2" style={{ borderTop: `1px solid ${T.line}` }}>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-semibold" style={{ color: T.muted }}>Management / Prescription Zones</span>
                      <Pill tone="info">{zonePersisted.length} محفوظة</Pill>
                      <Pill tone={activeIndicator ? 'ok' : 'warn'}>{activeIndicator ? `مصدر: ${activeIndicator.toUpperCase()}` : 'بدون source layer'}</Pill>
                      <Pill tone={selectedActiveSeasonId ? 'ok' : 'warn'}>{selectedActiveSeasonId ? 'مربوطة بالموسم' : 'لا موسم نشط'}</Pill>
                      <button
                        type="button" onClick={handleCreateZoneFromField} disabled={zoneSyncBusy}
                        data-testid="btn-create-zone-from-field"
                        className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-lg disabled:opacity-60"
                        style={{ color: T.ok, border: `1px solid ${T.line}` }}
                      >
                        حفظ Zone من حدود الحقل
                      </button>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                      <label className="text-[11px] grid gap-1" style={{ color: T.muted }}>
                        النوع
                        <select
                          value={zoneKind}
                          onChange={(e) => setZoneKind(e.target.value as AgriculturalZoneKind)}
                          className="px-2 py-1 rounded-lg text-xs"
                          style={{ background: T.card, border: `1px solid ${T.line}`, color: T.ink }}
                        >
                          <option value="management-zone">منطقة إدارة</option>
                          <option value="prescription-zone">منطقة وصفة</option>
                          <option value="exclusion-zone">منطقة استبعاد</option>
                        </select>
                      </label>
                      <NumberField label="معدل الوصفة" value={zoneRate} min={0} max={5000} step={5} onChange={setZoneRate} />
                      <label className="text-[11px] grid gap-1" style={{ color: T.muted }}>
                        وحدة المعدل
                        <input
                          value={zoneRateUnit}
                          onChange={(e) => setZoneRateUnit(e.target.value)}
                          className="px-2 py-1 rounded-lg text-xs"
                          style={{ background: T.card, border: `1px solid ${T.line}`, color: T.ink }}
                        />
                      </label>
                      <div className="text-[11px] flex items-end" style={{ color: T.faint }}>
                        v40 يستخدم حدود الحقل كـ Zone أولية؛ التحرير/التقسيم التفصيلي لاحقاً عبر Geoman.
                      </div>
                    </div>
                  </div>
                )}

                {(pivotDesigner || pivotDrafts.length > 0) && (
                  <div data-testid="pivot-designer-panel" className="mt-3 pt-3 space-y-2" style={{ borderTop: `1px solid ${T.line}` }}>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-semibold" style={{ color: T.muted }}>مصمم Pivot</span>
                      <Pill tone="info">{pivotDrafts.length + pivotPersisted.length} تصميم</Pill>
                      {pivotDesigner && <span className="text-[11px]" style={{ color: T.faint }}>انقر على الخريطة لاختيار مركز المحوري</span>}
                      <Pill tone={selectedActiveSeasonId ? 'ok' : 'warn'}>{selectedActiveSeasonId ? 'مربوط بالموسم' : 'لا موسم نشط'}</Pill>
                      {pivotDrafts.length > 0 && (
                        <>
                          <button
                            type="button" onClick={handleSavePivotDrafts} disabled={pivotSyncBusy}
                            data-testid="btn-save-pivot-drafts"
                            className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-lg disabled:opacity-60"
                            style={{ color: T.ok, border: `1px solid ${T.line}` }}
                          >
                            حفظ Pivot
                          </button>
                          <button
                            type="button" onClick={handleClearPivotDrafts}
                            className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-lg"
                            style={{ color: T.danger, border: `1px solid ${T.line}` }}
                          >
                            <Trash2 className="w-3 h-3" /> مسح تصاميم Pivot
                          </button>
                        </>
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
            <MapCanvasBoundary
              mode={mode === '3d' ? 'terrain3d' : compare ? 'compare' : GL_ENGINE ? 'maplibre' : 'leaflet'}
              fieldId={fieldId}
              indicatorId={indicatorActive}
              hasGeometry={Boolean(selected?.geometry)}
            >
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
                {compareMode === 'dates' ? (
                  <>
                    {/* مقارنة زمنيّة: نفس المؤشّر (leftLayer) بين تاريخَين مخزَّنَين مختلفَين.
                        كلّ لوحة تُمرَّر تاريخها الخاصّ إلى CompareMap (يسار=المختار، يمين=compareRightDate). */}
                    <SideBySide
                      leftLabel={
                        <select
                          value={selectedImageryDate}
                          onChange={(e) => handleSelectImageryTimelineItem(e.target.value)}
                          className="px-2 py-1 rounded-lg text-xs"
                          style={{ background: T.card, border: `1px solid ${T.line}`, color: T.ink }}
                          aria-label="تاريخ اللوحة اليسرى"
                          data-testid="compare-left-date"
                        >
                          <option value="latest">الأحدث</option>
                          {dateSelectorDates.map((d) => (
                            <option key={d.date} value={d.date}>{d.date}{d.has_cog ? ' · جاهز' : ''}</option>
                          ))}
                        </select>
                      }
                      rightLabel={
                        <select
                          value={compareRightDate}
                          onChange={(e) => setCompareRightDate(e.target.value)}
                          className="px-2 py-1 rounded-lg text-xs"
                          style={{ background: T.card, border: `1px solid ${T.line}`, color: T.ink }}
                          aria-label="تاريخ اللوحة اليمنى"
                          data-testid="compare-right-date"
                        >
                          <option value="latest">الأحدث</option>
                          {dateSelectorDates.map((d) => (
                            <option key={d.date} value={d.date}>{d.date}{d.has_cog ? ' · جاهز' : ''}</option>
                          ))}
                        </select>
                      }
                      left={<CompareMap fields={fields} selectedId={fieldId} basemapId={basemapId} indicatorId={leftLayer} opacity={opacity} imageryTs={imageryTs} imageryDate={selectedImageryDate === 'latest' ? null : selectedImageryDate} tenantId={tenantId} />}
                      right={<CompareMap fields={fields} selectedId={fieldId} basemapId={basemapId} indicatorId={leftLayer} opacity={opacity} imageryTs={imageryTs} imageryDate={compareRightDate === 'latest' ? null : compareRightDate} tenantId={tenantId} />}
                    />
                    <div className="text-[11px] mt-2" style={{ color: T.muted }}>
                      نفس المؤشّر ({LAYER_LEGEND[leftLayer]?.short ?? leftLayer}) بين تاريخَين مخزَّنَين — مقارنة زمنيّة حقيقيّة (للعرض فقط).
                    </div>
                  </>
                ) : (
                  <>
                    <SideBySide
                      leftLabel={<LayerSwitcher layers={INDICATOR_LAYERS.map((l) => ({ id: l.id, label: LAYER_LEGEND[l.id]?.short ?? l.label }))} active={leftLayer} onChange={setLeftLayer} />}
                      rightLabel={<LayerSwitcher layers={INDICATOR_LAYERS.map((l) => ({ id: l.id, label: LAYER_LEGEND[l.id]?.short ?? l.label }))} active={rightLayer} onChange={setRightLayer} />}
                      left={<CompareMap fields={fields} selectedId={fieldId} basemapId={basemapId} indicatorId={leftLayer} opacity={opacity} imageryTs={imageryTs} imageryDate={selectedImageryDate === 'latest' ? null : selectedImageryDate} tenantId={tenantId} />}
                      right={<CompareMap fields={fields} selectedId={fieldId} basemapId={basemapId} indicatorId={rightLayer} opacity={opacity} imageryTs={imageryTs} imageryDate={selectedImageryDate === 'latest' ? null : selectedImageryDate} tenantId={tenantId} />}
                    />
                    <div className="text-[11px] mt-2" style={{ color: T.muted }}>
                      طبقتان حقيقيّتان لنفس الحقل والتاريخ المختار — للموازنة البصريّة.
                    </div>
                  </>
                )}
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
                      preferPersistedCog={selectedDateHasCog}
                      tenantId={tenantId}
                      pivotDesignerEnabled={pivotDesigner}
                      onAddPivotDraft={handleAddPivotDraft}
                      pivotDrafts={showPivots ? [...pivotPersisted, ...zonePersisted, ...pivotDrafts] : []}
                      hillshadeTilesUrl={hillshadeTilesUrl}
                      slopeTilesUrl={slopeTilesUrl}
                      soilTilesUrl={soilTilesUrl}
                      soilSamplePoints={showSoilSamples ? soilSamplePoints : []}
                      contours={showContours ? contoursData : null}
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
                    preferPersistedCog={selectedDateHasCog}
                    tenantId={tenantId}
                    hillshadeTilesUrl={hillshadeTilesUrl}
                    slopeTilesUrl={slopeTilesUrl}
                    terrainOpacity={opacity}
                    soilTilesUrl={soilTilesUrl}
                    soilOpacity={opacity}
                    soilSamplePoints={showSoilSamples ? soilSamplePoints : []}
                    contours={showContours ? contoursData : null}
                    pivotDesignerEnabled={pivotDesigner}
                    onAddPivotDraft={handleAddPivotDraft}
                    pivotDrafts={showPivots ? [...pivotPersisted, ...zonePersisted, ...pivotDrafts] : []}
                  />
                )}
                {/* أسطورة المقياس العموديّة الموحَّدة (يمين الخريطة) — تظهر فقط عند
                    تفعيل مؤشّر مُلوَّن (لا فوق صورة الحقل المجرّدة). نفس مكوّن ونمط
                    FieldIndicatorMap، بنطاقات مطابقة لتصيير raster. */}
                {indicatorActive && indicatorActive !== RAW_IMAGERY_INDEX_ID && (() => {
                  const [vmin, vmax, invert] = INDEX_DOMAIN[indicatorActive] ?? [-0.2, 0.9, false];
                  return (
                    <div style={{ position: 'absolute', top: '50%', insetInlineEnd: 12, transform: 'translateY(-50%)', zIndex: 600, pointerEvents: 'none' }}>
                      <MapIndicatorLegend index={indicatorActive} vmin={vmin} vmax={vmax} invert={invert} />
                    </div>
                  );
                })()}
              </div>
            )}
            </MapCanvasBoundary>

            <div className="text-[11px]" style={{ color: T.muted }}>
              السطح الموحّد «الحقول والخريطة» — بلاطات <code>/raster</code> الحقيقيّة فوق حدود <code>/fields</code>.
              أدوات القياس من turf، الدبابيس محلّيّة (لا اختراع نقطة قراءة خلفيّة).
            </div>
          </div>
        </div>
      )}

      {/* درج تفاصيل الحقل المنزلق */}
      <FieldDrawerShell fieldId={fieldId} open={detailOpen}>
        <FieldDetailDrawer
          fieldId={detailOpen ? fieldId : null}
          fieldName={selected?.name ?? ''}
          open={detailOpen}
          onClose={() => setDetailOpen(false)}
        />
      </FieldDrawerShell>

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


export default function MapHub() {
  return (
    <MapHubShell>
      <MapHubCore />
    </MapHubShell>
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

function CompareMap({
  fields, selectedId, basemapId, indicatorId, opacity, imageryTs, imageryDate, tenantId,
}: {
  fields: ReturnType<typeof useSelectedField>['options'];
  selectedId: string; basemapId: string; indicatorId: string; opacity: number; imageryTs?: number; imageryDate?: string | null; tenantId?: string | null;
}) {
  const legend = indicatorId === RAW_IMAGERY_INDEX_ID ? undefined : LAYER_LEGEND[indicatorId];
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
