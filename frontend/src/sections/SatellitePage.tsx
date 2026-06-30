// SAHOOL v9 — SatellitePage.tsx (v4 · صحّة الحقل طراز FieldView)
// ✅ سطح «صحّة الحقل» بثلاثة أوضاع عبر مبدّل مقسَّم (LayerSwitcher):
//    • الاستطلاع (Scouting): تباين مناطقيّ (management zones) + دبابيس مشاهدات
//      محلّيّة للجلسة (لا GET للقراءة في الخادم — TODO موثّق).
//    • النباتيّ (Vegetation): NDVI/NDMI زمنيّاً ببلاطات المؤشّر + شريط زمنيّ.
//    • اللون الحقيقيّ (True-Color): صور الأساس فقط (طبقة المؤشّر مخفيّة).
// ✅ شريط/منزلق زمنيّ (DateScrubber) يصفّح تواريخ COG الحقيقيّة من raster-service.
// ✅ خريطة Leaflet حقيقيّة (FieldIndicatorMap) ببلاطات مؤشّر من raster-service.
// ✅ الحقول من القاعدة (useSelectedField). كلّ البيانات حقيقيّة أو حالة فارغة صادقة.
import { useState, useEffect, useMemo, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Satellite, Layers, RefreshCw, Loader2, Wifi, Map as MapIcon, GitCompareArrows, Ruler,
  Sprout, Leaf, Image as ImageIcon, Play, Pause, AlertTriangle,
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import {
  useVegetationTimeseries, useAnalyzeVegetation, useCurrentNDVI,
  useIndicatorGrid, useFieldTimeseries, useFieldChange, useFieldPrescription, useRefreshFieldImagery, type GridIndex,
} from '../hooks/useApi';
import FieldIndicatorMap from '../components/FieldIndicatorMap';
import DataFreshnessBadge from '../components/maphub/DataFreshnessBadge';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';
import { geomToPolygon } from '../lib/geo';
import { useSelectedField } from '../hooks/useSelectedField';
import { apiErrorMessage } from '../services/api';
import { useIndicatorsCatalog } from '../hooks/useApi';
import type { CatalogIndicator } from '../hooks/useApi';
import { LayerSwitcher } from '../components/ds';
import {
  DateScrubber, ScoutingMap, ScoutingPinPanel,
  type ScrubberPoint, type ScoutPin, type PinCategory,
  type PinPersistence, type PinSeverity,
} from '../components/fieldhealth';
import { useScoutingPins, useCreateScoutingPin, useCropScoutingIssues } from '../hooks/useScouting';
import type { ScoutingPinRecord } from '../hooks/useScouting';

// مبدّل الطبقات مدفوع بكتالوج المؤشّرات الخلفيّ (renderable=طبقة بلاطات مكانيّة)
// لا بقائمة مُبرمَجة — مصدر حقيقة واحد للقابل للرسم (لا طبقة ميتة ولا مفقودة).
// العرض فقط (لون/أيقونة/وصف) محلّيّ؛ الاسم والتوفّر من الكتالوج.
interface IndOption { id: string; name: string; desc: string; color: string; icon: string }

const IND_META: Record<string, { color: string; icon: string; desc: string }> = {
  ndvi:     { color:'#16a34a', icon:'🌿', desc:'الغطاء النباتي' },
  evi:      { color:'#dc2626', icon:'📊', desc:'الغطاء المحسّن' },
  ndre:     { color:'#a855f7', icon:'🧪', desc:'النيتروجين (red-edge)' },
  msavi:    { color:'#ea580c', icon:'🏜', desc:'تصحيح تربة ذاتي' },
  savi:     { color:'#f59e0b', icon:'🏜', desc:'تصحيح التربة' },
  gndvi:    { color:'#22c55e', icon:'🌱', desc:'NDVI أخضر' },
  ndwi:     { color:'#3b82f6', icon:'💧', desc:'محتوى المياه' },
  ndmi:     { color:'#0ea5e9', icon:'💦', desc:'محتوى الرطوبة' },
  msi:      { color:'#0891b2', icon:'🌡', desc:'الإجهاد المائي (SWIR/NIR)' },
  salinity: { color:'#b45309', icon:'🧂', desc:'مؤشّر الملوحة' },
};
const IND_META_DEFAULT = { color:'#6b7280', icon:'🛰️', desc:'' };

// قائمة احتياطيّة (الطبقات القابلة للرسم) إن تعذّر الكتالوج — كي لا تنكسر الخريطة.
const FALLBACK_RENDERABLE = ['ndvi','evi','ndre','msavi','savi','gndvi','ndwi','ndmi','msi','salinity'];

// أوضاع «صحّة الحقل» الثلاثة (FieldView Field Health).
type HealthMode = 'scouting' | 'vegetation' | 'truecolor';

function ndviColor(v: number) {
  if (v > 0.7) return '#16a34a';
  if (v > 0.5) return '#65a30d';
  if (v > 0.3) return '#ca8a04';
  if (v > 0.1) return '#f97316';
  return '#dc2626';
}
function ndviLabel(v: number) {
  if (v > 0.7) return 'ممتاز';
  if (v > 0.5) return 'جيد';
  if (v > 0.3) return 'مقبول';
  return 'منخفض';
}

// لون شدّة منطقة الإدارة (low→high) — للعرض في لوحة الاستطلاع.
const ZONE_COLOR: Record<string, string> = {
  low: '#dc2626', medium: '#f59e0b', high: '#16a34a',
};
function zoneColor(zone: string): string {
  return ZONE_COLOR[zone] ?? '#0ea5e9';
}

export default function SatellitePage() {
  // «الحقل النشط» المشترك (useSelectedField): قائمة الحقول + الاختيار المشترك +
  // الافتراض للأوّل — يتبع المستخدم عبر الشاشات بدل اختيار محليّ يضيع عند التنقّل.
  const { options: fields, isLoading: fieldsLoading, isError: fieldsError, refetch, fieldId, setFieldId } = useSelectedField();

  // وضع صحّة الحقل (افتراضيّاً النباتيّ — السلوك السابق للصفحة).
  const [mode, setMode] = useState<HealthMode>('vegetation');

  const [activeIndex, setActiveIndex] = useState('ndvi');
  const [days,        setDays]        = useState(30);
  const [showLayers,  setShowLayers]  = useState(true);
  // أدوات الرسم/القياس على الخريطة (مضلّع→مساحة · خطّ→طول). off افتراضيّاً.
  const [measureTools, setMeasureTools] = useState(false);
  // أثر زرّ «تحليل الآن» المرئيّ (نجاح/خطأ) — كان الزرّ يبدو بلا استجابة.
  const [analyzeMsg, setAnalyzeMsg] = useState<{ ok: boolean; text: string } | null>(null);

  // ── دبابيس الاستطلاع الدائمة (v94 — تُجلَب من الخادم وتُحفَظ، تبقى عبر الجلسات) ──
  // GET /api/v1/scouting/pins?field_id=… يُرجِع المُخزَّنة (RLS)؛ الإنشاء عبر POST
  // /api/v1/fields/{id}/pins (تفاؤليّ + إعادة جلب). صدق: القاعدة غير مفعّلة ⇒ note_ar.
  const pinsQ = useScoutingPins(fieldId);
  const createPin = useCreateScoutingPin(fieldId);

  // إعداد الدبّوس التالي (FieldView pin UX): فئة · دوام · شدّة · مشكلة · ملاحظة.
  const [pinCategory, setPinCategory] = useState<PinCategory>('disease');
  const [pinPersistence, setPinPersistence] = useState<PinPersistence>('seasonal');
  const [pinSeverity, setPinSeverity] = useState<PinSeverity>('medium');
  const [pinIssueCode, setPinIssueCode] = useState<string>('');
  const [pinNote, setPinNote] = useState<string>('');

  // دبابيس تفاؤليّة محلّيّة (قبل تأكيد إعادة الجلب) — تُدمَج مع المُخزَّنة بلا تكرار.
  const [optimisticPins, setOptimisticPins] = useState<ScoutPin[]>([]);
  // تبديل الحقل يُفرِغ التفاؤليّة (المُخزَّنة تأتي من استعلام الحقل الجديد).
  useEffect(() => { setOptimisticPins([]); setPinIssueCode(''); }, [fieldId]);

  // المُخزَّنة من الخادم → ScoutPin (مفتاح pin_id؛ persisted=true).
  const serverPins: ScoutPin[] = useMemo(
    () => (pinsQ.data?.pins ?? []).map((r: ScoutingPinRecord) => ({
      id: r.pin_id,
      lat: r.lat,
      lon: r.lng,
      category: (r.issue_category as PinCategory),
      note: r.note_ar ?? '',
      createdAt: r.created_at,
      persistence: (r.persistence as PinPersistence),
      severity: (r.severity as PinSeverity),
      issueCode: r.issue_code,
      persisted: true,
    })),
    [pinsQ.data],
  );

  // الدمج: المُخزَّنة + التفاؤليّة التي لم تظهر بعد في استجابة الخادم (بمعرّف pin_id).
  const pins: ScoutPin[] = useMemo(() => {
    const serverIds = new Set(serverPins.map((p) => p.id));
    return [...serverPins, ...optimisticPins.filter((p) => !serverIds.has(p.id))];
  }, [serverPins, optimisticPins]);

  const handleDropPin = useCallback((lat: number, lon: number) => {
    const pinId = `pin_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const optimistic: ScoutPin = {
      id: pinId, lat, lon, category: pinCategory, note: pinNote,
      createdAt: new Date().toISOString(), persistence: pinPersistence,
      severity: pinSeverity, issueCode: pinIssueCode || null, persisted: false,
    };
    setOptimisticPins((prev) => [...prev, optimistic]);
    createPin.mutate(
      {
        pin_id: pinId, field_id: fieldId, lat, lng: lon,
        issue_category: pinCategory, severity: pinSeverity, persistence: pinPersistence,
        issue_code: pinIssueCode || null, note_ar: pinNote || null,
      },
      {
        // عند نجاح الإنشاء تُعيد useCreateScoutingPin إبطال المخبّأ ⇒ إعادة جلب؛
        // نزيل التفاؤليّ عند ظهوره من الخادم (effect أدناه). الفشل ⇒ تراجُع فوريّ.
        onError: () => setOptimisticPins((prev) => prev.filter((p) => p.id !== pinId)),
      },
    );
  }, [fieldId, pinCategory, pinPersistence, pinSeverity, pinIssueCode, pinNote, createPin]);

  // تنظيف التفاؤليّة بعد أن تصبح مُخزَّنة فعليّاً (ظهرت في استجابة الخادم).
  useEffect(() => {
    const serverIds = new Set(serverPins.map((p) => p.id));
    setOptimisticPins((prev) => prev.filter((p) => !serverIds.has(p.id)));
  }, [serverPins]);

  // إخفاء من العرض فقط (لا DELETE في الخادم) — يُعيد الظهور عند إعادة الجلب إن كان
  // مُخزَّناً. للتفاؤليّ (غير محفوظ) يُزيله نهائيّاً.
  const [hiddenIds, setHiddenIds] = useState<Set<string>>(new Set());
  useEffect(() => { setHiddenIds(new Set()); }, [fieldId]);
  const handleRemovePin = useCallback((id: string) => {
    setOptimisticPins((prev) => prev.filter((p) => p.id !== id));
    setHiddenIds((prev) => new Set(prev).add(id));
  }, []);
  const handleClearPins = useCallback(() => {
    setOptimisticPins([]);
    setHiddenIds(new Set(pins.map((p) => p.id)));
  }, [pins]);
  const visiblePins = useMemo(() => pins.filter((p) => !hiddenIds.has(p.id)), [pins, hiddenIds]);

  // طبقات قابلة للرسم من الكتالوج (renderable=true)، مزيّنة بعرض محلّيّ. عند
  // تعذّر الكتالوج تسقط لقائمة احتياطيّة فلا تنكسر الخريطة. الاسم من الكتالوج.
  const catalogQ = useIndicatorsCatalog();
  const indices: IndOption[] = useMemo(() => {
    const items = Array.isArray(catalogQ.data?.indicators) ? catalogQ.data.indicators : null;
    const base: { id: string; name: string }[] = items
      ? items.filter((i: CatalogIndicator) => i?.renderable).map((i: CatalogIndicator) => ({ id: String(i.id), name: String(i.name_ar ?? i.id) }))
      : FALLBACK_RENDERABLE.map((id) => ({ id, name: id.toUpperCase() }));
    return base.map(({ id, name }) => ({ id, name, ...(IND_META[id] ?? IND_META_DEFAULT) }));
  }, [catalogQ.data]);

  const field = fields.find((f) => f.id === fieldId) || fields[0];
  const idx   = indices.find((i) => i.id === activeIndex) || indices[0];
  const gridIndex = (idx?.id ?? 'ndvi') as GridIndex;

  // مشاكل محصول الحقل من الـtaxonomy (قائمة المشكلة في لوحة الدبابيس). تظهر القائمة
  // فقط عند مطابقة المحصول لمفتاح معروف بالخادم — وإلّا تُخفى (لا خيارات مخترَعة).
  const cropIssuesQ = useCropScoutingIssues(field?.crop);
  const issueOptions = useMemo(
    () => (cropIssuesQ.data?.issues ?? []).map((i) => ({ code: i.code, name_ar: i.name_ar })),
    [cropIssuesQ.data],
  );

  const { data: tsData,  isLoading: tsLoading }  = useVegetationTimeseries(fieldId, days);
  const { data: ndviNow }                        = useCurrentNDVI(fieldId);
  const { mutateAsync: analyze, isPending: analyzing } = useAnalyzeVegetation();
  // «تحليل الآن» مع أثر مرئيّ صريح: نجاح ⇒ يُبطِل المخبّأ (في الخطّاف) فيُحدَّث الشريط
  // الزمنيّ والقيم؛ خطأ ⇒ رسالة عربيّة صادقة بدل صمت. يختفي التنويه بعد ثوانٍ.
  const handleAnalyze = useCallback(async () => {
    if (!fieldId || analyzing) return;
    setAnalyzeMsg(null);
    try {
      await analyze({ fieldId });
      setAnalyzeMsg({ ok: true, text: 'اكتمل التحليل — حُدِّث الشريط الزمنيّ والقيم.' });
    } catch (e) {
      setAnalyzeMsg({ ok: false, text: apiErrorMessage(e, 'تعذّر التحليل — حاول مجدّداً') });
    }
  }, [fieldId, analyzing, analyze]);
  // إخفاء تنويه التحليل تلقائيّاً بعد مدّة وجيزة (لا يبقى عالقاً).
  useEffect(() => {
    if (!analyzeMsg) return;
    const t = setTimeout(() => setAnalyzeMsg(null), 6000);
    return () => clearTimeout(t);
  }, [analyzeMsg]);
  const { mutateAsync: refreshImagery, isPending: refreshingImagery } = useRefreshFieldImagery();

  // شبكة المؤشّر الحقيقيّة — لوسم مصدر البيانات بصدق (حقيقيّة / لا توجد بعد).
  const { data: gridResp } = useIndicatorGrid(fieldId, gridIndex, 'latest');
  const hasGrid = !!gridResp && gridResp.real_data && Array.isArray(gridResp.grid) && gridResp.grid.length > 0;

  // السلسلة الزمنيّة الحقيقيّة من raster-service (متوسّط المؤشّر لكلّ تاريخ COG).
  // صدق: لا COG ⇒ available=false (لا قيم مخترعة) — نُظهر حالة فارغة لا رسماً وهميّاً.
  const { data: rasterTs, isLoading: rasterTsLoading, isError: rasterTsError } =
    useFieldTimeseries(fieldId, gridIndex, '');
  const rasterPoints = rasterTs?.available ? (rasterTs.points ?? []) : [];
  // تواريخ COG الحقيقيّة المتاحة (لاختيار تاريخَي كشف التغيّر).
  const availableDates = useMemo(
    () => rasterPoints.map((p) => p.datetime).filter(Boolean),
    [rasterPoints],
  );

  // كشف التغيّر بين تاريخين (real grids only). الافتراض: الأقدم ↔ الأحدث.
  const [dateA, setDateA] = useState('');
  const [dateB, setDateB] = useState('');
  useEffect(() => {
    if (availableDates.length >= 2) {
      setDateA((prev) => (prev && availableDates.includes(prev) ? prev : availableDates[0]));
      setDateB((prev) =>
        prev && availableDates.includes(prev) ? prev : availableDates[availableDates.length - 1],
      );
    }
  }, [availableDates]);
  const { data: change, isLoading: changeLoading, isError: changeError } =
    useFieldChange(fieldId, gridIndex, dateA, dateB, { enabled: !!dateA && !!dateB && dateA !== dateB });

  // ── وصفة مناطق الإدارة (variability المناطقيّ) — لوضع الاستطلاع ──
  // تقسيم كوانتايل من شبكة المؤشّر (raster-service). real_data=false ⇒ توضيحيّ.
  const { data: rxResp } = useFieldPrescription(fieldId, gridIndex, 'latest', { nZones: 3, enabled: mode === 'scouting' && !!fieldId });
  const rxZones = useMemo(
    () => (Array.isArray(rxResp?.zones) ? rxResp.zones : []),
    [rxResp],
  );

  // نقطة سلسلة زمنيّة كما تقرؤها هذه الشاشة: تاريخ (موجود دائماً للنقطة) + NDVI اختياريّ.
  type TsPoint = { date: string; ndvi?: number };
  const tsRaw = tsData as { timeseries?: TsPoint[]; data?: TsPoint[] } | undefined;
  const ts: TsPoint[] = tsRaw?.timeseries || tsRaw?.data || [];
  const currentNdvi = ndviNow?.ndvi?.current ?? ts[ts.length - 1]?.ndvi ?? null;
  // الشريط الزمني يعرض المتوسّطات الحقيقيّة من raster-service عند توفّرها،
  // وإلّا يسقط إلى سلسلة vegetation-service. لا بيانات تركيبيّة.
  // cloud: نسبة الغيوم لكلّ تاريخ (raster فقط) — null في مصدر vegetation البديل.
  const stripPoints: ScrubberPoint[] = Array.isArray(rasterPoints) && rasterPoints.length
    ? rasterPoints.map((p) => ({ date: p.datetime, value: p.mean, cloud: p.cloudy_pct ?? null }))
    : (Array.isArray(ts) ? ts : []).map((t) => ({ date: t.date, value: t.ndvi ?? 0, cloud: null }));

  // هل يوفّر المصدر نسبة غيوم؟ (raster نعم، vegetation لا) — يضبط إتاحة المُبدِّل.
  const hasCloudData = stripPoints.some((p) => typeof p.cloud === 'number');

  // إخفاء الأيّام الغائمة (نمط FieldView): يُسقط النقاط التي تتجاوز عتبة الغيوم.
  const [hideCloudy, setHideCloudy] = useState(false);
  const CLOUD_THRESHOLD = 50;
  const visiblePoints = (hideCloudy && hasCloudData)
    ? stripPoints.filter((p) => !(typeof p.cloud === 'number' && p.cloud > CLOUD_THRESHOLD))
    : stripPoints;

  // قائمة التواريخ المرئيّة مُستقرّة المرجع (مفتاح نصّيّ) — كي لا يُعاد تشغيل
  // التأثير كلّ تصيير.
  const visibleDates = useMemo(
    () => visiblePoints.map((p) => p.date).filter(Boolean),
    [visiblePoints.map((p) => p.date).join('|')], // eslint-disable-line react-hooks/exhaustive-deps
  );

  // التاريخ المختار يقود طبقة الخريطة (تمرير/نقر الشريط). الافتراض: أحدث تاريخ مرئيّ.
  const [selectedDate, setSelectedDate] = useState('');
  useEffect(() => {
    if (!visibleDates.length) { setSelectedDate(''); return; }
    setSelectedDate((prev) =>
      prev && visibleDates.includes(prev) ? prev : visibleDates[visibleDates.length - 1],
    );
  }, [visibleDates]);

  // ── مُشغّل زمنيّ للصور الجوّيّة السابقة (نمط أفضل المنصّات الزراعيّة) ───────────
  // يتقدّم عبر التواريخ المتاحة (المُصفّاة من الغيوم) كأنيميشن، فيرى المزارع تطوّر
  // الغطاء عبر الزمن. يحترم تفضيل تقليل الحركة، ويتوقّف تلقائيّاً عند نقص التواريخ.
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    if (!playing || visibleDates.length < 2) return undefined;
    if (typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      setPlaying(false);
      return undefined;
    }
    const id = window.setInterval(() => {
      setSelectedDate((prev) => {
        const i = visibleDates.indexOf(prev);
        // يتقدّم نحو الأحدث ويعود للأقدم عند النهاية (تكرار دوريّ).
        return visibleDates[(i + 1) % visibleDates.length];
      });
    }, 1100);
    return () => window.clearInterval(id);
  }, [playing, visibleDates]);
  // توقّف التشغيل إن لم يعد هناك ما يكفي من تواريخ.
  useEffect(() => { if (visibleDates.length < 2 && playing) setPlaying(false); }, [visibleDates.length, playing]);

  // طبقة الخريطة: التاريخ المختار إن وُجِد، وإلّا "latest" (سلوك سابق).
  const mapDate = selectedDate || 'latest';

  // مضلّع الحقل + إطار احتياطيّ للخريطة من هندسة/مركز الحقل الحقيقيّ.
  const fieldPolygon = field ? geomToPolygon(field.geometry) : undefined;
  const fallbackBounds: [number, number, number, number] | undefined =
    field && field.lat != null && field.lon != null
      ? [field.lon - 0.01, field.lat - 0.01, field.lon + 0.01, field.lat + 0.01]
      : undefined;

  // وسم مصدر بيانات الشريط الزمنيّ (متوسّطات حقيقيّة من raster عند توفّرها).
  const scrubberBadge = rasterPoints.length > 0 ? (
    <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 999, background: '#052e16', color: '#4ade80', border: '1px solid #14532d' }}>
      متوسّطات حقيقيّة · {gridIndex.toUpperCase()}
    </span>
  ) : undefined;

  // مبدّل الأوضاع الثلاثة (LayerSwitcher من نظام التصميم).
  const modeLayers = [
    { id: 'scouting' as const,  label: 'الاستطلاع',     icon: <Sprout style={{ width: 13, height: 13 }} /> },
    { id: 'vegetation' as const, label: 'النباتيّ',      icon: <Leaf style={{ width: 13, height: 13 }} /> },
    { id: 'truecolor' as const,  label: 'اللون الحقيقيّ', icon: <ImageIcon style={{ width: 13, height: 13 }} /> },
  ];

  return (
    <div className="space-y-4 max-w-7xl mx-auto" dir="rtl">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3 justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-100">صحّة الحقل</h2>
          <p className="text-sm text-slate-400">Sentinel-2 L2A · Copernicus · كل 5 أيام</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1 px-2 py-1 rounded-full text-[11px] bg-emerald-950 text-emerald-400 border border-emerald-900">
            <Wifi className="w-3 h-3" /> Copernicus CDSE
          </span>
          {/* مُبدِّل أدوات القياس على الخريطة (مضلّع→مساحة · خطّ→طول). off افتراضيّاً. */}
          <button onClick={() => setMeasureTools((v) => !v)}
            aria-pressed={measureTools}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors"
            style={measureTools
              ? { background: '#0ea5e922', color: '#7dd3fc', borderColor: '#0ea5e966' }
              : { background: '#1e293b', color: '#94a3b8', borderColor: '#334155' }}>
            <Ruler className="w-3.5 h-3.5" /> أدوات القياس
          </button>
          <button onClick={handleAnalyze} disabled={analyzing || !fieldId}
            title={!fieldId ? 'اختر حقلاً أوّلاً' : 'يحلّل صور Sentinel-2 ويحدّث الشريط الزمنيّ والقيم'}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-white disabled:opacity-50"
            style={{ background: analyzing ? '#15803d' : '#16a34a' }}>
            {analyzing ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> تحليل...</> : <><RefreshCw className="w-3.5 h-3.5" /> تحليل الآن</>}
          </button>
          <button
            onClick={() => fieldId && refreshImagery({ fieldId })}
            disabled={refreshingImagery || !fieldId}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border disabled:opacity-50"
            style={{ background: '#1e293b', color: '#fbbf24', borderColor: '#92400e' }}
            title="يحسب مؤشّرات Sentinel-2 الحقيقيّة عبر CDSE (الافتراضيّ الأقوى) مع تحوّل تلقائيّ إلى Element84 عند تعذّره؛ معالجة COG حقيقيّة — لا قيم وهمية."
          >
            {refreshingImagery
              ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> تحديث الصور...</>
              : <><Satellite className="w-3.5 h-3.5" /> تحديث صور الأقمار</>}
          </button>
        </div>
      </div>

      {/* تنويه أثر «تحليل الآن» (نجاح/خطأ) — يضمن استجابة مرئيّة صريحة للزرّ */}
      {analyzeMsg && (
        <div className="rounded-lg px-3 py-2 text-sm border flex items-center gap-2"
          role="status"
          style={analyzeMsg.ok
            ? { background: '#052e1b', color: '#86efac', borderColor: '#22c55e55' }
            : { background: '#1a1400', color: '#fcd34d', borderColor: '#f59e0b55' }}>
          {analyzeMsg.ok ? <RefreshCw className="w-3.5 h-3.5" /> : <AlertTriangle className="w-3.5 h-3.5" />}
          {analyzeMsg.text}
        </div>
      )}

      {/* مبدّل أوضاع صحّة الحقل (استطلاع · نباتيّ · لون حقيقيّ) */}
      <div className="rounded-xl p-2.5 border flex items-center gap-3 flex-wrap" style={{ background:'#1e293b', borderColor:'#334155' }}>
        <LayerSwitcher layers={modeLayers} active={mode} onChange={setMode} />
        <span className="text-[11px] text-slate-500 mr-auto">
          {mode === 'scouting'   && 'تباين مناطقيّ + دبابيس مشاهدات (محلّيّة للجلسة)'}
          {mode === 'vegetation' && 'مؤشّر نباتيّ زمنيّ (NDVI/NDMI) — بلاطات + سلسلة'}
          {mode === 'truecolor'  && 'صور الأساس الحقيقيّة فقط (بلا طبقة مؤشّر)'}
        </span>
      </div>

      {/* لا حقول حقيقيّة بعد → حالة صادقة بدل خريطة وهميّة */}
      {fieldsLoading ? (
        <LoadingState message="جارٍ تحميل الحقول…" />
      ) : fieldsError ? (
        <ErrorState title="تعذّر تحميل الحقول من الخادم" onRetry={() => refetch()} />
      ) : fields.length === 0 ? (
        <EmptyState
          title="لا توجد حقول بعد"
          hint="أضِف حقلاً من شاشة «إدارة الحقول» (ارسم حدوده على الخريطة) لعرض مؤشّراته الفضائيّة."
        />
      ) : (
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Map column */}
        <div className="lg:col-span-3 space-y-3">
          {/* شريط مصدر البيانات: بلاطات حقيقيّة أم لا توجد بعد (صدق المصدر) */}
          {mode !== 'truecolor' && (
            <div className="flex items-center gap-2 text-[11px] px-3 py-2 rounded-lg border"
              style={hasGrid
                ? { background:'#13301f', borderColor:'#2d6a3e', color:'#9fe6b4' }
                : { background:'#3a2e14', borderColor:'#7a5a1a', color:'#f0d68a' }}>
              <MapIcon className="w-3.5 h-3.5" />
              {hasGrid
                ? `بلاطات حقيقيّة · Sentinel-2 (Element84)${gridResp?.date ? ` · ${gridResp.date}` : ''}`
                : 'لا توجد بلاطات مؤشّر لهذا الحقل بعد — اضغط «تحليل الآن» أو تحقّق من معالجة الراستر. الخريطة تعرض الأساس والحدود فقط.'}
            </div>
          )}

          {/* تحذير عدم تطابق توقيت بيانات الطبقة/المشهد (FieldView) — يقارن تاريخ
              مشهد الطبقة (gridResp.date = acquisition_date من raster-service) بالتاريخ
              المختار للعرض (selectedDate). mismatch ⇒ تحذير؛ match ⇒ شارة حداثة؛
              unknown (لا تاريخ طبقة / العرض «الأحدث») ⇒ لا شيء. صدق: المقارنة الكاملة
              (scene_id/field_revision) تنتظر تسطيح geometry_metadata على استجابة الراستر
              (TODO موثّق في lib/sceneFreshness.ts). */}
          {mode !== 'truecolor' && hasGrid && (
            <DataFreshnessBadge
              layerDate={gridResp?.date}
              displayDate={selectedDate}
              indexLabel={gridIndex.toUpperCase()}
            />
          )}

          {/* الخريطة — تتبدّل حسب الوضع، بانتقال framer-motion */}
          <AnimatePresence mode="wait">
            <motion.div
              key={mode}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.18 }}
            >
              {mode === 'scouting' ? (
                <ScoutingMap
                  fieldId={fieldId}
                  index={gridIndex}
                  date={mapDate}
                  fieldPolygon={fieldPolygon}
                  fallbackBounds={fallbackBounds}
                  pins={visiblePins}
                  onDropPin={handleDropPin}
                  onRemovePin={handleRemovePin}
                  height={400}
                />
              ) : mode === 'truecolor' ? (
                // اللون الحقيقيّ: صور الأساس (Esri World Imagery) فقط. طبقة المؤشّر
                // تبدأ بشفافيّة صفر (مخفيّة) — صدق: لا نُلفّق مشهد لون-حقيقيّ من
                // Sentinel، نعرض الأساس الجوّيّ. يمكن للمستخدم رفع الشفافيّة لكشف
                // المؤشّر فوق نفس الأساس إن رغب (نفس التاريخ الحقيقيّ، لا طلب وهميّ).
                <FieldIndicatorMap
                  key={`${fieldId}-truecolor`}
                  fieldId={fieldId}
                  index={gridIndex}
                  date={mapDate}
                  fieldPolygon={fieldPolygon}
                  fallbackBounds={fallbackBounds}
                  basemap="satellite"
                  initialOpacity={0}
                  height={400}
                  tools={measureTools}
                  tileSegment="cdse-tiles"
                  fieldGeometry={field?.geometry ?? null}
                  fieldBbox={fallbackBounds}
                />
              ) : (
                // وضع النباتيّ: بلاطات CDSE الحيّة (Sentinel Hub) مع قصّ poly.
                // CDSE_CLIENT_ID/SECRET موجودان ⇒ available=true ⇒ تُركَّب طبقة المؤشّر.
                <FieldIndicatorMap
                  key={fieldId}
                  fieldId={fieldId}
                  index={gridIndex}
                  date={mapDate}
                  fieldPolygon={fieldPolygon}
                  fallbackBounds={fallbackBounds}
                  basemap="satellite"
                  initialOpacity={0.75}
                  height={400}
                  tools={measureTools}
                  tileSegment="cdse-tiles"
                  fieldGeometry={field?.geometry ?? null}
                  fieldBbox={fallbackBounds}
                />
              )}
            </motion.div>
          </AnimatePresence>

          {/* الشريط الزمنيّ (date scrubber) — تواريخ COG حقيقيّة. يظهر للأوضاع
              التي تعتمد طبقة المؤشّر (استطلاع/نباتيّ)؛ اللون الحقيقيّ لا يحتاجه. */}
          {mode !== 'truecolor' && (
            <div className="space-y-2">
              {/* مبدّلات الفترة + إخفاء الغائم (نمط FieldView) */}
              <div className="flex items-center gap-2 flex-wrap">
                {hasCloudData && (
                  <label className="flex items-center gap-1.5 cursor-pointer select-none text-[11px] text-slate-300">
                    <input type="checkbox" checked={hideCloudy} onChange={(e)=>setHideCloudy(e.target.checked)} style={{ accentColor:'#16a34a' }} />
                    إخفاء الأيّام الغائمة
                  </label>
                )}
                {/* مُشغّل زمنيّ: تشغيل/إيقاف أنيميشن الصور الجوّيّة السابقة عبر التواريخ */}
                <button
                  type="button"
                  onClick={() => setPlaying((v) => !v)}
                  disabled={visibleDates.length < 2}
                  title={visibleDates.length < 2 ? 'يحتاج تاريخين على الأقلّ' : (playing ? 'إيقاف العرض الزمنيّ' : 'تشغيل العرض الزمنيّ للصور السابقة')}
                  aria-pressed={playing}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
                  style={{ background: playing ? '#16a34a' : '#16a34a22', color: playing ? '#fff' : '#4ade80', border: '1px solid #16a34a44' }}>
                  {playing ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
                  {playing ? 'إيقاف' : 'تشغيل'}
                </button>
                <div className="flex gap-1 mr-auto">
                  {[14,30,60].map(d=>(
                    <button key={d} onClick={()=>setDays(d)}
                      className="px-2 py-0.5 rounded text-[11px]"
                      style={{ background:days===d?'#16a34a22':'transparent', color:days===d?'#4ade80':'#64748b', border:`1px solid ${days===d?'#16a34a44':'#334155'}` }}>
                      {d}ي
                    </button>
                  ))}
                </div>
              </div>

              {(rasterTsLoading || tsLoading) ? (
                <div className="flex justify-center py-4 rounded-xl border" style={{ background:'#1e293b', borderColor:'#334155' }}>
                  <Loader2 className="w-5 h-5 text-emerald-500 animate-spin" />
                </div>
              ) : rasterTsError && !visiblePoints.length ? (
                <div className="rounded-xl border p-3" style={{ background:'#1e293b', borderColor:'#334155' }}>
                  <p className="text-amber-400/80 text-xs text-center">تعذّر جلب السلسلة الزمنيّة للمؤشّر.</p>
                </div>
              ) : !visiblePoints.length ? (
                // حالة فارغة صادقة بدل شريط بلا قيم: لا تواريخ مُعالَجة بعد لهذا الحقل.
                <div className="rounded-xl border p-3 flex items-center justify-center gap-2"
                  style={{ background:'#1e293b', borderColor:'#334155' }}>
                  <p className="text-xs text-center text-slate-400">
                    لا توجد قيم زمنيّة بعد لهذا الحقل — اضغط «تحليل الآن» لمعالجة صور Sentinel-2 وعرض الشريط الزمنيّ.
                  </p>
                  <button onClick={handleAnalyze} disabled={analyzing || !fieldId}
                    className="shrink-0 inline-flex items-center gap-1 px-2.5 py-1 rounded text-[11px] font-semibold text-white disabled:opacity-50"
                    style={{ background:'#16a34a' }}>
                    {analyzing ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
                    تحليل الآن
                  </button>
                </div>
              ) : (
                <DateScrubber
                  points={visiblePoints}
                  selected={selectedDate}
                  onSelect={setSelectedDate}
                  cloudThreshold={CLOUD_THRESHOLD}
                  badge={scrubberBadge}
                />
              )}
            </div>
          )}
        </div>

        {/* Side panel */}
        <div className="space-y-3">
          {/* Field selector (حقول حقيقيّة) */}
          <div className="rounded-xl p-3 border" style={{ background:'#1e293b', borderColor:'#334155' }}>
            <label className="block text-xs text-slate-400 mb-1">الحقل</label>
            <select value={fieldId} onChange={e=>setFieldId(e.target.value)}
              className="w-full px-3 py-2 rounded-lg text-sm"
              style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }}>
              {fields.map(f=><option key={f.id} value={f.id}>{f.name}</option>)}
            </select>
            <div className="grid grid-cols-2 gap-1.5 mt-2">
              {[
                {l:'NDVI',v:currentNdvi!=null?currentNdvi.toFixed(3):'لا بيانات',c:currentNdvi!=null?ndviColor(currentNdvi):'#94a3b8'},
                {l:'الحالة',v:currentNdvi!=null?ndviLabel(currentNdvi):'بانتظار التحليل',c:currentNdvi!=null?ndviColor(currentNdvi):'#94a3b8'},
                {l:'المساحة',v:field?`${field.area}هـ`:'—',c:'#94a3b8'},
                {l:'المحصول',v:field?field.crop:'—',c:'#94a3b8'},
              ].map((s,i)=>(
                <div key={i} className="rounded-lg px-2 py-1.5 text-center" style={{background:'#0f1117'}}>
                  <div className="text-xs font-bold" style={{color:s.c}}>{s.v}</div>
                  <div className="text-[10px] text-slate-500">{s.l}</div>
                </div>
              ))}
            </div>
          </div>

          {/* ── لوحة جانبيّة خاصّة بالوضع ── */}
          {mode === 'scouting' ? (
            <>
              {/* دبابيس الاستطلاع الدائمة (تُحفَظ وتُجلَب من الخادم — v94) */}
              <ScoutingPinPanel
                pins={visiblePins}
                activeCategory={pinCategory}
                onCategoryChange={setPinCategory}
                persistence={pinPersistence}
                onPersistenceChange={setPinPersistence}
                severity={pinSeverity}
                onSeverityChange={setPinSeverity}
                note={pinNote}
                onNoteChange={setPinNote}
                issueOptions={issueOptions}
                issueCode={pinIssueCode}
                onIssueChange={setPinIssueCode}
                onRemove={handleRemovePin}
                onClear={handleClearPins}
                isLoading={pinsQ.isLoading}
                isError={pinsQ.isError}
                dbDisabledNote={pinsQ.data?.note_ar ?? null}
              />

              {/* مناطق التباين (management zones) — من raster-service */}
              <div className="rounded-xl p-3 border" style={{ background:'#1e293b', borderColor:'#334155' }}>
                <div className="flex items-center gap-2 mb-2">
                  <Layers className="w-4 h-4 text-emerald-400" />
                  <span className="text-sm font-semibold text-slate-200">مناطق التباين</span>
                  <span className="text-[10px] text-slate-500 mr-auto">{gridIndex.toUpperCase()}</span>
                </div>
                {rxZones.length === 0 ? (
                  <p className="text-[11px] text-slate-500 py-2">
                    لا تقسيم مناطقيّ بعد — يلزم شبكة مؤشّر مُعالَجة (اضغط «تحليل الآن»).
                  </p>
                ) : (
                  <>
                    {!rxResp?.real_data && (
                      <p className="text-[10px] text-amber-400/80 mb-2">⚠️ عرض توضيحيّ (لا شبكة حقيقيّة) — لا تتّخذ قرارات بناءً عليه.</p>
                    )}
                    <div className="space-y-1.5">
                      {rxZones.map((z) => (
                        <div key={z.zone} className="flex items-center gap-2 rounded-lg px-2 py-1.5" style={{ background:'#0f1117' }}>
                          <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: zoneColor(z.zone) }} />
                          <span className="text-xs text-slate-200 flex-1">{z.zone}</span>
                          <span className="text-[10px] text-slate-400">{z.pct}%</span>
                          <span className="text-[10px] text-slate-500">
                            [{z.value_range[0].toFixed(2)}–{z.value_range[1].toFixed(2)}]
                          </span>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            </>
          ) : (
            <>
              {/* Layers (اختيار المؤشّر) — للأوضاع النباتيّة/اللون الحقيقيّ */}
              <div className="rounded-xl border overflow-hidden" style={{ background:'#1e293b', borderColor:'#334155' }}>
                <button onClick={()=>setShowLayers(!showLayers)}
                  className="w-full flex items-center justify-between px-3 py-2.5 hover:bg-slate-800 transition-colors">
                  <div className="flex items-center gap-2">
                    <Layers className="w-4 h-4 text-slate-400" />
                    <span className="text-sm font-semibold text-slate-200">الطبقات</span>
                  </div>
                  <span className="text-slate-500 text-xs">{showLayers?'▲':'▼'}</span>
                </button>
                {showLayers && (
                  <div className="px-2 pb-3 space-y-1">
                    {indices.map(ind=>(
                      <button key={ind.id}
                        onClick={()=> setActiveIndex(ind.id)}
                        className="w-full flex items-center gap-2 px-2.5 py-2 rounded-lg transition-all text-right"
                        style={{ background:activeIndex===ind.id?`${ind.color}22`:'transparent',
                          border:`1px solid ${activeIndex===ind.id?ind.color+'44':'transparent'}` }}>
                        <span>{ind.icon}</span>
                        <div className="flex-1">
                          <div className="text-sm" style={{color:activeIndex===ind.id?ind.color:'#94a3b8'}}>{ind.name}</div>
                          <div className="text-[10px] text-slate-600">{ind.desc}</div>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Legend */}
              <div className="rounded-xl p-3 border" style={{ background:'#1e293b', borderColor:'#334155' }}>
                <div className="text-[11px] text-slate-400 mb-1.5">مقياس {idx.name}</div>
                <div className="h-3 rounded-full" style={{ background:'linear-gradient(to right,#dc2626,#f97316,#f59e0b,#65a30d,#16a34a)' }} />
                <div className="flex justify-between text-[10px] text-slate-500 mt-1">
                  <span>0.2- (تربة)</span><span>0.9+ (صحي)</span>
                </div>
              </div>
            </>
          )}

          {/* كشف التغيّر بين تاريخين (per-pixel، بيانات COG حقيقيّة فقط) — للأوضاع
              المعتمدة على المؤشّر (لا في اللون الحقيقيّ). */}
          {mode !== 'truecolor' && (
          <div className="rounded-xl p-3 border" style={{ background:'#1e293b', borderColor:'#334155' }}>
            <div className="flex items-center gap-2 mb-2">
              <GitCompareArrows className="w-4 h-4 text-sky-400" />
              <span className="text-sm font-semibold text-slate-200">كشف التغيّر</span>
              <span className="text-[10px] text-slate-500 mr-auto">{gridIndex.toUpperCase()}</span>
            </div>

            {availableDates.length < 2 ? (
              <p className="text-[11px] text-slate-500 py-2">
                يلزم تاريخان مُعالَجان على الأقلّ لكشف التغيّر. شغّل «تحليل الآن» على تواريخ متعدّدة.
              </p>
            ) : (
              <>
                <div className="grid grid-cols-2 gap-2 mb-2">
                  <label className="block">
                    <span className="block text-[10px] text-slate-400 mb-1">من (الأقدم)</span>
                    <select value={dateA} onChange={(e)=>setDateA(e.target.value)}
                      className="w-full px-2 py-1.5 rounded-lg text-[11px]"
                      style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }}>
                      {availableDates.map((d)=><option key={d} value={d}>{d}</option>)}
                    </select>
                  </label>
                  <label className="block">
                    <span className="block text-[10px] text-slate-400 mb-1">إلى (الأحدث)</span>
                    <select value={dateB} onChange={(e)=>setDateB(e.target.value)}
                      className="w-full px-2 py-1.5 rounded-lg text-[11px]"
                      style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }}>
                      {availableDates.map((d)=><option key={d} value={d}>{d}</option>)}
                    </select>
                  </label>
                </div>

                {dateA === dateB ? (
                  <p className="text-[11px] text-amber-400/80 py-1">اختر تاريخين مختلفين.</p>
                ) : changeLoading ? (
                  <div className="flex justify-center py-3"><Loader2 className="w-4 h-4 text-sky-400 animate-spin" /></div>
                ) : changeError ? (
                  <p className="text-[11px] text-amber-400/80 py-1">تعذّر حساب التغيّر.</p>
                ) : change && !change.available ? (
                  <p className="text-[11px] text-amber-400/80 py-1">
                    {change.note || 'لا توجد بيانات COG حقيقيّة لأحد التاريخين — لا تغيّر مُفبرَك.'}
                  </p>
                ) : change && change.available ? (
                  <div className="space-y-2">
                    <div className="grid grid-cols-2 gap-2">
                      <div className="rounded-lg px-2 py-1.5 text-center" style={{ background:'#13301f', border:'1px solid #2d6a3e' }}>
                        <div className="text-base font-bold text-emerald-400">{(change.improved_pct ?? 0).toFixed(1)}%</div>
                        <div className="text-[10px] text-emerald-300/70">تحسّن</div>
                      </div>
                      <div className="rounded-lg px-2 py-1.5 text-center" style={{ background:'#3a1414', border:'1px solid #7a2a2a' }}>
                        <div className="text-base font-bold text-red-400">{(change.degraded_pct ?? 0).toFixed(1)}%</div>
                        <div className="text-[10px] text-red-300/70">تدهور</div>
                      </div>
                    </div>
                    <div className="flex justify-between text-[10px] text-slate-500">
                      <span>مستقرّ: {(change.stable_pct ?? 0).toFixed(1)}%</span>
                      <span>Δ متوسّط: {(change.mean_delta ?? 0).toFixed(3)}</span>
                    </div>
                    {change.cloud_warning && (
                      <p className="text-[10px] text-amber-400/80">
                        ⚠️ التغطية {(change.coverage_pct ?? 0).toFixed(0)}% فقط (غيوم/فجوات) — نتيجة جزئيّة.
                      </p>
                    )}
                    {change.interpretation_ar && (
                      <p className="text-[11px] text-slate-300 leading-relaxed border-t border-slate-700 pt-1.5">
                        {change.interpretation_ar}
                      </p>
                    )}
                  </div>
                ) : null}
              </>
            )}
          </div>
          )}
        </div>
      </div>
      )}

      {/* Time-series chart — للأوضاع المعتمدة على المؤشّر (لا في اللون الحقيقيّ) */}
      {mode !== 'truecolor' && (
      <div className="rounded-xl p-4 border" style={{ background:'#1e293b', borderColor:'#334155' }}>
        <div className="flex items-center gap-2 mb-4">
          <Satellite className="w-4 h-4 text-emerald-400" />
          <span className="text-sm font-semibold text-slate-200">السلسلة الزمنية — {idx.name}</span>
          {rasterPoints.length > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-900">
              متوسّطات COG حقيقيّة
            </span>
          )}
          <span className="text-[10px] text-slate-500 mr-auto">{stripPoints.length} اكتساب</span>
        </div>
        {(rasterTsLoading || tsLoading) ? (
          <div className="flex justify-center h-24 items-center"><Loader2 className="w-6 h-6 text-emerald-500 animate-spin" /></div>
        ) : stripPoints.length > 0 ? (
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={stripPoints}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="date" tick={{fill:'#64748b',fontSize:9}} tickLine={false} interval={Math.max(1,Math.floor(stripPoints.length/6))} />
              <YAxis domain={[0,1]} tick={{fill:'#64748b',fontSize:11}} tickLine={false} width={32} />
              <Tooltip contentStyle={{background:'#0f1117',border:'1px solid #334155',borderRadius:8,fontSize:12}} itemStyle={{color:'#e2e8f0'}} />
              <ReferenceLine y={0.5} stroke="#f59e0b" strokeDasharray="4 2" />
              <Line type="monotone" dataKey="value" stroke={idx.color} strokeWidth={2} dot={{r:3,fill:idx.color}} name={idx.name} />
            </LineChart>
          </ResponsiveContainer>
        ) : rasterTsError ? (
          <div className="text-center py-8 text-amber-400/80 text-sm">تعذّر جلب السلسلة الزمنيّة للمؤشّر.</div>
        ) : (
          <div className="text-center py-8 text-slate-500 text-sm">
            لا توجد متوسّطات مؤشّر بعد — اضغط "تحليل الآن" لبدء تحليل صور Sentinel-2.
          </div>
        )}
      </div>
      )}
    </div>
  );
}
