import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle, ChevronDown, ChevronLeft, FileSpreadsheet, Layers,
  MapPin, Recycle, ScatterChart, ShieldCheck, Sprout, Wheat,
} from 'lucide-react';
import {
  useConsistencyFreshness, useConsistencyIrrigation, useFieldOperationalState,
  useFieldPortfolioOptimize, useIrrigationRecommendation, useOperationReportCsv,
  useRotationEvaluate, useRotationPrinciples, useValidateGeometry,
  useWofostAdaptationGuidance, useWofostCropTypes,
} from '../../hooks/useAgronomyConsistency';
import type { PortfolioFieldInput } from '../../hooks/useAgronomyConsistency';
import {
  conflictRows, conflictSeverityBadge, executionModeBadge, fmtNum, freshnessWarningRows,
  geometryIssueBadge, geometryIssues, geometryValidationFacts, irrigationPolicyBadge,
  irrigationRecommendationFacts, parseMeasure, parsePctToFraction, pctFromFraction,
  portfolioFieldRows, portfolioStatusBadge, portfolioSummaryFacts, rotationRatingBadge,
  rotationReasons, supportedCropRows, unsupportedMessage, validityBadge, wofostKeyParams,
  wofostModelTypeRows,
} from '../../lib/agronomyConsistency';
import type { AgroConflict, DisplayFact } from '../../lib/agronomyConsistency';
import { useAuthRole, useTenantId } from '../../hooks/useAuth';
import { useFieldOptions } from '../../hooks/useFieldOptions';
import { canManage } from '../../lib/permissions';
import { T } from '../ds';

interface Props {
  /** الحقل النشط — للحالة التشغيليّة وتصدير تقرير العمليّة. null ⇒ حالة «اختر حقلاً». */
  fieldId?: string | null;
  /** تسمية محصول الحقل — سياق عرض/إدخال افتراضيّ (لا حكم). */
  cropLabel?: string | null;
  enabled?: boolean;
}

// ألوان بطاقات فرعيّة داكنة مطابقة لـWaterHarvestingCard/AgroAnalyticsCard (الطبقة الداكنة).
const CARD_BG = 'rgba(15,23,42,.35)';
const SUB_BG = 'rgba(2,6,23,.5)';

type SectionKey =
  | 'consistency' | 'rotation' | 'wofost' | 'irrigation'
  | 'field-state' | 'portfolio' | 'geometry' | 'report';

/** رأس قسم قابل للطيّ — العنوان والأيقونة وسهم الحالة (RTL: يسار = مفتوح). */
function SectionHeader({
  icon, title, open, onToggle,
}: { icon: React.ReactNode; title: string; open: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      className="flex w-full items-center justify-between gap-2 rounded-xl border px-2.5 py-1.5"
      style={{ borderColor: T.line, background: CARD_BG }}
    >
      <span className="inline-flex items-center gap-2 text-[12px] font-bold" style={{ color: T.ink }}>
        {icon} {title}
      </span>
      {open
        ? <ChevronDown className="w-4 h-4 shrink-0" style={{ color: T.faint }} aria-hidden="true" />
        : <ChevronLeft className="w-4 h-4 shrink-0" style={{ color: T.faint }} aria-hidden="true" />}
    </button>
  );
}

/** وسم حقيقة صغير (label: value) — نفس أسلوب WaterHarvestingCard/AgroAnalyticsCard. */
function FactPills({ facts }: { facts: DisplayFact[] }) {
  if (facts.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {facts.map((f) => (
        <span key={f.label} className="text-[11px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}>
          <span style={{ color: T.faint }}>{f.label}:</span> {f.value}
        </span>
      ))}
    </div>
  );
}

/** صفّ تناقض (شدّة + رسالة + دليل) — الأحكام والنصوص من الخادم حرفيّاً. */
function ConflictRow({ c }: { c: AgroConflict }) {
  const sev = conflictSeverityBadge(c.severity);
  return (
    <div className="flex flex-col gap-0.5 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
      <div className="flex flex-wrap items-center gap-2 text-[11px]">
        <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: sev.color, border: `1px solid ${T.line}` }}>{sev.label_ar}</span>
        {c.rule_id && <span style={{ color: T.faint }}>{c.rule_id}</span>}
      </div>
      {c.message_ar && <div className="text-[11px]" style={{ color: T.muted }}>{c.message_ar}</div>}
      {c.evidence_ar && <div className="text-[10px]" style={{ color: T.faint }}>{c.evidence_ar}</div>}
    </div>
  );
}

const inputCls = 'px-2 py-0.5 rounded-lg text-[11px]';
const inputStyle = { border: `1px solid ${T.line}`, background: SUB_BG, color: T.ink } as const;

/** حقل نصّ/رقم صغير موسوم — لا افتراض قيمة (فارغ ⇒ لا إرسال في موقع الاستدعاء). */
function LabeledInput({
  id, label, value, onChange, type = 'text', placeholder, width = 'w-24',
}: {
  id: string; label: string; value: string; onChange: (v: string) => void;
  type?: string; placeholder?: string; width?: string;
}) {
  return (
    <span className="inline-flex items-center gap-1">
      <label htmlFor={id} className="text-[11px] font-bold" style={{ color: T.ink }}>{label}:</label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder ?? 'من قياس'}
        className={`${width} ${inputCls}`}
        style={inputStyle}
        {...(type === 'number' ? { step: 'any' } : {})}
      />
    </span>
  );
}

const STAGE_OPTIONS: { key: string; label_ar: string }[] = [
  { key: 'initial', label_ar: 'ابتدائيّة' },
  { key: 'development', label_ar: 'نموّ' },
  { key: 'mid', label_ar: 'منتصف' },
  { key: 'late', label_ar: 'متأخّرة' },
];

const CONFIDENCE_OPTIONS: { key: string; label_ar: string }[] = [
  { key: '', label_ar: '— غير محدّد —' },
  { key: 'high', label_ar: 'عالية' },
  { key: 'medium', label_ar: 'متوسّطة' },
  { key: 'low', label_ar: 'منخفضة' },
  { key: 'very_low', label_ar: 'شبه معدومة' },
];

/**
 * بطاقة اتّساق القرار الزراعيّ (Agronomy Consistency): تعكس طبقة backend يتيمة (P2):
 * فحوص الاتّساق (ريّ + نضارة) · تقييم الدورة ومبادئها · إرشاد تكيّف WOFOST وأنواعه ·
 * توصية ريّ موحّدة · الحالة التشغيليّة للحقل · تحسين محفظة الحقول · التحقّق من صحّة الهندسة ·
 * تصدير تقرير العمليّات (CSV مدير). صدق صارم: الأحكام والنصوص من الخادم تُعرَض حرفيّاً؛
 * الأقسام قابلة للطيّ واستعلاماتها كسولة (لا تُطلَق قبل فتح القسم وتوفّر المدخلات)؛
 * 404 ⇒ «غير مُفعَّل» صادق؛ الأقسام المرتبطة بحقل تعرض «اختر حقلاً» عند غيابه.
 */
export default function AgronomyConsistencyCard({ fieldId, cropLabel, enabled = true }: Props) {
  const role = useAuthRole();
  const tenantId = useTenantId();
  const fieldOptionsQ = useFieldOptions();
  const fieldOptions = fieldOptionsQ.options;
  const isManager = canManage(role);

  const [open, setOpen] = useState<Set<SectionKey>>(new Set());
  const isOpen = (k: SectionKey) => open.has(k);
  const toggle = (k: SectionKey) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k); else next.add(k);
      return next;
    });

  // ── فحوص الاتّساق: توصية ريّ ──
  const [ciDelta, setCiDelta] = useState(''); // ٪ زيادة/خفض مقترح (يمرّ كما هو، ليس كسراً)
  const [ciRain, setCiRain] = useState('');
  const [ciMoist, setCiMoist] = useState(''); // ٪ من السعة ⇒ كسر
  const [ciEt0, setCiEt0] = useState('');
  const [ciConf, setCiConf] = useState(''); // ٪ ⇒ كسر
  const consistencyParams = useMemo(() => ({
    irrigation_delta_pct: parseMeasure(ciDelta),
    rain_forecast_mm: parseMeasure(ciRain),
    soil_moisture_ratio: parsePctToFraction(ciMoist),
    et0_mm: parseMeasure(ciEt0),
    recommendation_confidence: parsePctToFraction(ciConf),
  }), [ciDelta, ciRain, ciMoist, ciEt0, ciConf]);
  const consistencyQ = useConsistencyIrrigation(consistencyParams, isOpen('consistency'));

  // ── فحوص الاتّساق: نضارة البيانات ──
  const [fNdvi, setFNdvi] = useState('');
  const [fSoil, setFSoil] = useState('');
  const [fWx, setFWx] = useState('');
  const freshnessParams = useMemo(() => ({
    ndvi_age_days: parseMeasure(fNdvi),
    soil_age_days: parseMeasure(fSoil),
    weather_age_hours: parseMeasure(fWx),
  }), [fNdvi, fSoil, fWx]);
  const freshnessQ = useConsistencyFreshness(freshnessParams, isOpen('consistency'));

  // ── الدورة الزراعيّة ──
  const [rPrev, setRPrev] = useState('');
  const [rCand, setRCand] = useState('');
  const rotationQ = useRotationEvaluate(
    rPrev.trim() || null, rCand.trim() || null, isOpen('rotation'),
  );
  const rotReasons = useMemo(() => rotationReasons(rotationQ.data), [rotationQ.data]);
  const [showPrinciples, setShowPrinciples] = useState(false);
  const principlesQ = useRotationPrinciples(isOpen('rotation') && showPrinciples);
  const cropTable = useMemo(() => supportedCropRows(principlesQ.data), [principlesQ.data]);

  // ── WOFOST ──
  const [wCrop, setWCrop] = useState('');
  const guidanceQ = useWofostAdaptationGuidance(wCrop.trim() || null, isOpen('wofost'));
  const keyParams = useMemo(() => wofostKeyParams(guidanceQ.data), [guidanceQ.data]);
  const [showTypes, setShowTypes] = useState(false);
  const cropTypesQ = useWofostCropTypes(isOpen('wofost') && showTypes);
  const modelTypes = useMemo(() => wofostModelTypeRows(cropTypesQ.data), [cropTypesQ.data]);

  // ── توصية ريّ موحّدة ──
  const [irCrop, setIrCrop] = useState('');
  const [irStage, setIrStage] = useState('mid');
  const [irTmin, setIrTmin] = useState('');
  const [irTmax, setIrTmax] = useState('');
  const [irRain, setIrRain] = useState('');
  const [irForecast, setIrForecast] = useState('');
  const [irMoist, setIrMoist] = useState('');
  const [irEce, setIrEce] = useState('');
  const [irTol, setIrTol] = useState('');
  const [irWaterEc, setIrWaterEc] = useState('');
  const [irDrain, setIrDrain] = useState('');
  const [irEff, setIrEff] = useState(''); // ٪ ⇒ كسر
  const tMin = parseMeasure(irTmin);
  const tMax = parseMeasure(irTmax);
  const rainRecent = parseMeasure(irRain);
  const rainForecast = parseMeasure(irForecast);
  const irrigationInput = useMemo(() => {
    // حرارتان **ومطران** إجباريّون خادميّاً (لا افتراض).
    //
    // كان المطران يمرّان بـ`?? 0`: حقلٌ فارغٌ يُرسَل «صفر مطر». والصفرُ يُطرَح من
    // الاحتياج فترتفع الكمّيّة — أي أنّ **ترْكَ الحقل فارغاً كان يُنتِج توصيةً أسخى**،
    // وهو أسوأُ اتّجاهٍ للانحياز. والخادمُ صار يردّ ٥٠٣ عند غيابهما، فبقاءُ `?? 0` هنا
    // كان سيُخفي ذلك الفشلَ المُغلَق خلف رقمٍ مُختلَقٍ في المتصفّح.
    //
    // والنمطُ ليس جديداً: الملوحةُ والصرفُ أدناه تُمرَّر بلا تصفيرٍ منذ البداية، والحرارةُ
    // تحجب الطلبَ عند غيابها. فهذا **إلحاقُ المطر بالقاعدة القائمة** لا قاعدةٌ ثانية.
    if (tMin == null || tMax == null || rainRecent == null || rainForecast == null) return null;
    return {
      crop: (irCrop.trim() || cropLabel) || null,
      stage: irStage,
      t_min_c: tMin,
      t_max_c: tMax,
      rain_recent_mm: rainRecent,
      forecast_rain_mm: rainForecast,
      soil_moisture_pct: parseMeasure(irMoist),
      // ملوحة/غسل مشروطة — تُمرَّر فقط عند إدخالها (الغائب لا يُختلق)
      soil_ece: parseMeasure(irEce),
      crop_salt_tolerance_ece: parseMeasure(irTol),
      water_ec: parseMeasure(irWaterEc),
      drainage: irDrain.trim() || null,
      irrigation_efficiency: parsePctToFraction(irEff),
    };
  }, [tMin, tMax, rainRecent, rainForecast, irCrop, cropLabel, irStage, irMoist, irEce, irTol, irWaterEc, irDrain, irEff]);
  const irrigationQ = useIrrigationRecommendation(isOpen('irrigation') ? irrigationInput : null);
  const irrFacts = useMemo(() => irrigationRecommendationFacts(irrigationQ.data), [irrigationQ.data]);

  // ── الحالة التشغيليّة للحقل ──
  const [fsConf, setFsConf] = useState('');
  const [fsDelta, setFsDelta] = useState('');
  const [fsRain, setFsRain] = useState('');
  const [fsMoist, setFsMoist] = useState('');
  const [fsEt0, setFsEt0] = useState('');
  const [fsNdvi, setFsNdvi] = useState('');
  const [fsSoil, setFsSoil] = useState('');
  const [fsWx, setFsWx] = useState('');
  const fieldStateParams = useMemo(() => ({
    confidence_level: fsConf || null,
    irrigation_delta_pct: parseMeasure(fsDelta),
    rain_forecast_mm: parseMeasure(fsRain),
    soil_moisture_ratio: parsePctToFraction(fsMoist),
    et0_mm: parseMeasure(fsEt0),
    ndvi_age_days: parseMeasure(fsNdvi),
    soil_age_days: parseMeasure(fsSoil),
    weather_age_hours: parseMeasure(fsWx),
  }), [fsConf, fsDelta, fsRain, fsMoist, fsEt0, fsNdvi, fsSoil, fsWx]);
  const fieldStateQ = useFieldOperationalState(
    isOpen('field-state') ? (fieldId ?? null) : null, fieldStateParams,
  );
  const fs = fieldStateQ.data;
  const fsConflicts = useMemo(() => conflictRows(fs), [fs]);
  const fsFreshness = useMemo(() => freshnessWarningRows(fs), [fs]);

  // ── تحسين محفظة الحقول ──
  const [pfFields, setPfFields] = useState<PortfolioFieldInput[]>([]);
  const [pfId, setPfId] = useState(fieldId ?? '');
  const [pfMargin, setPfMargin] = useState('');
  const [pfDemand, setPfDemand] = useState('');
  const [pfArea, setPfArea] = useState('');
  const [pfTotal, setPfTotal] = useState('');
  useEffect(() => {
    if (fieldId && !pfId) setPfId(fieldId);
  }, [fieldId, pfId]);
  const addPfField = () => {
    const margin = parseMeasure(pfMargin);
    const demand = parseMeasure(pfDemand);
    if (!pfId.trim() || margin == null || demand == null) return;
    setPfFields((prev) => [...prev, {
      field_id: pfId.trim(),
      expected_margin: margin,
      water_demand_m3: demand,
      area_ha: parseMeasure(pfArea) ?? 1,
    }]);
    setPfId(fieldId ?? ''); setPfMargin(''); setPfDemand(''); setPfArea('');
  };
  const pfTotalWater = parseMeasure(pfTotal);
  const portfolioInput = useMemo(() => {
    if (pfFields.length === 0 || pfTotalWater == null) return null;
    return { fields: pfFields, total_water_m3: pfTotalWater };
  }, [pfFields, pfTotalWater]);
  const portfolioQ = useFieldPortfolioOptimize(isOpen('portfolio') ? portfolioInput : null);
  const pfRows = useMemo(() => portfolioFieldRows(portfolioQ.data), [portfolioQ.data]);
  const pfSummary = useMemo(() => portfolioSummaryFacts(portfolioQ.data), [portfolioQ.data]);

  // ── التحقّق من صحّة الهندسة ──
  const [geoText, setGeoText] = useState('');
  const [geoCrs, setGeoCrs] = useState('');
  const parsedGeo = useMemo<{ obj: object | null; error: string | null }>(() => {
    const t = geoText.trim();
    if (t === '') return { obj: null, error: null };
    try {
      const obj = JSON.parse(t);
      if (obj == null || typeof obj !== 'object') return { obj: null, error: 'المُدخَل ليس كائن GeoJSON.' };
      return { obj, error: null };
    } catch {
      return { obj: null, error: 'JSON غير صالح — تحقّق من الصيغة.' };
    }
  }, [geoText]);
  const geometryQ = useValidateGeometry(
    isOpen('geometry') ? parsedGeo.obj : null, geoCrs.trim() || null,
  );
  const geoFacts = useMemo(() => geometryValidationFacts(geometryQ.data), [geometryQ.data]);
  const geoIssueList = useMemo(() => geometryIssues(geometryQ.data), [geometryQ.data]);

  // ── تقرير العمليّات (CSV مدير) ──
  const [orName, setOrName] = useState('');
  const [orStart, setOrStart] = useState('');
  const [orEnd, setOrEnd] = useState('');
  const [orFieldLabel, setOrFieldLabel] = useState('');
  const reportMut = useOperationReportCsv();
  // Fail-closed (FE-07): بلا مستأجِر مُصادَق (tenantId === null) لا تقرير — لا نُلفّق 'default'.
  const reportReady = !!tenantId && !!fieldId && !!orName.trim() && !!orStart.trim() && !!orEnd.trim();
  const onExportReport = () => {
    if (!reportReady || !fieldId || !tenantId) return;
    reportMut.mutate({
      tenant_id: tenantId,
      operation_name_ar: orName.trim(),
      period_start: orStart.trim(),
      period_end: orEnd.trim(),
      lang: 'ar',
      // صفّ هويّة الحقل المختار؛ المقاييس تبقى على افتراضات الخادم (صفر) — لا تلفيق
      // لأرقام ريّ/تسميد لا نملكها هنا (التقرير الخلفيّ نقيّ يستقبل المقاييس من المستدعي).
      fields: [{
        field_id: fieldId,
        field_name_ar: orFieldLabel.trim() || cropLabel || fieldId,
        tenant_id: tenantId,
        crop: cropLabel || '',
      }],
    }, {
      onSuccess: (csv) => {
        // تأثير DOM: حوّل نصّ CSV إلى Blob ونزّله (BOM من الخادم يضمن عرض العربيّة بإكسل).
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `operation_report_${orStart.trim()}_${orEnd.trim()}.csv`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      },
    });
  };

  if (!enabled) return null;

  const noField = <div className="text-[11px]" style={{ color: T.faint }}>اختر حقلاً لعرض هذا القسم.</div>;
  const disabledMsg = (d?: boolean) => d
    ? <div className="text-[11px]" style={{ color: T.muted }}>هذه الميزة غير مُفعَّلة على الخادم بعد.</div>
    : null;

  return (
    <section
      className="mb-3 rounded-2xl border p-3"
      style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}
      data-testid="agronomy-consistency"
      aria-label="اتّساق القرار الزراعيّ"
    >
      <div className="flex items-center gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <ShieldCheck className="w-4 h-4 text-emerald-300" aria-hidden="true" /> اتّساق القرار الزراعيّ
          {cropLabel && <span className="text-[11px]" style={{ color: T.faint }}>· {cropLabel}</span>}
        </span>
      </div>

      <div className="flex flex-col gap-2">
        {/* ═══ فحوص الاتّساق (ريّ + نضارة) ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<AlertTriangle className="w-4 h-4 text-amber-300" aria-hidden="true" />} title="فحوص الاتّساق (ريّ + حداثة البيانات)" open={isOpen('consistency')} onToggle={() => toggle('consistency')} />
          {isOpen('consistency') && (
            <div className="flex flex-col gap-2 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              {/* اتّساق توصية الريّ */}
              <div className="flex flex-col gap-1.5">
                <div className="text-[11px] font-bold" style={{ color: T.ink }}>توصية الريّ ضدّ الظروف الحاليّة:</div>
                <div className="flex flex-wrap items-center gap-2">
                  <LabeledInput id="ci-delta" label="تغيير الريّ ٪" value={ciDelta} onChange={setCiDelta} type="number" width="w-16" placeholder="+/-" />
                  <LabeledInput id="ci-rain" label="مطر متوقّع مم" value={ciRain} onChange={setCiRain} type="number" width="w-16" />
                  <LabeledInput id="ci-moist" label="رطوبة/سعة ٪" value={ciMoist} onChange={setCiMoist} type="number" width="w-16" />
                  <LabeledInput id="ci-et0" label="ET₀ مم" value={ciEt0} onChange={setCiEt0} type="number" width="w-14" />
                  <LabeledInput id="ci-conf" label="ثقة التوصية ٪" value={ciConf} onChange={setCiConf} type="number" width="w-16" />
                </div>
                {consistencyParams && Object.values(consistencyParams).every((v) => v == null) ? (
                  <div className="text-[11px]" style={{ color: T.faint }}>أدخِل مدخلاً واحداً على الأقلّ لفحص التناقض (الغائب يُتخطّى).</div>
                ) : consistencyQ.isLoading ? (
                  <div className="text-[11px]" style={{ color: T.faint }}>جارٍ فحص الاتّساق…</div>
                ) : disabledMsg(consistencyQ.data?.disabled) ?? (consistencyQ.data ? (
                  <ConsistencyVerdict resp={consistencyQ.data} />
                ) : null)}
              </div>

              {/* نضارة البيانات */}
              <div className="flex flex-col gap-1.5 pt-1" style={{ borderTop: `1px dashed ${T.line}` }}>
                <div className="text-[11px] font-bold" style={{ color: T.ink }}>حداثة البيانات (عتبات: NDVI≤5ي · تربة≤2ي · طقس≤6س):</div>
                <div className="flex flex-wrap items-center gap-2">
                  <LabeledInput id="f-ndvi" label="عمر NDVI (يوم)" value={fNdvi} onChange={setFNdvi} type="number" width="w-14" />
                  <LabeledInput id="f-soil" label="عمر التربة (يوم)" value={fSoil} onChange={setFSoil} type="number" width="w-14" />
                  <LabeledInput id="f-wx" label="عمر الطقس (ساعة)" value={fWx} onChange={setFWx} type="number" width="w-14" />
                </div>
                {freshnessParams && Object.values(freshnessParams).every((v) => v == null) ? (
                  <div className="text-[11px]" style={{ color: T.faint }}>أدخِل عمراً واحداً على الأقلّ لفحص النضارة.</div>
                ) : freshnessQ.isLoading ? (
                  <div className="text-[11px]" style={{ color: T.faint }}>جارٍ فحص النضارة…</div>
                ) : disabledMsg(freshnessQ.data?.disabled) ?? (freshnessQ.data ? (
                  <ConsistencyVerdict resp={freshnessQ.data} />
                ) : null)}
              </div>
            </div>
          )}
        </div>

        {/* ═══ الدورة الزراعيّة ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<Recycle className="w-4 h-4 text-emerald-300" aria-hidden="true" />} title="تقييم الدورة + مبادئها" open={isOpen('rotation')} onToggle={() => toggle('rotation')} />
          {isOpen('rotation') && (
            <div className="flex flex-col gap-2 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <div className="flex flex-wrap items-center gap-2">
                <LabeledInput id="r-prev" label="المحصول السابق" value={rPrev} onChange={setRPrev} placeholder="قمح / wheat" width="w-24" />
                <LabeledInput id="r-cand" label="المرشّح" value={rCand} onChange={setRCand} placeholder="عدس / lentil" width="w-24" />
              </div>
              {!rPrev.trim() || !rCand.trim() ? (
                <div className="text-[11px]" style={{ color: T.faint }}>أدخِل المحصول السابق والمرشّح لتقييم التعاقب.</div>
              ) : rotationQ.isLoading ? (
                <div className="text-[11px]" style={{ color: T.faint }}>جارٍ تقييم التعاقب…</div>
              ) : disabledMsg(rotationQ.data?.disabled) ?? (
                unsupportedMessage(rotationQ.data) ? (
                  <div className="text-[11px]" style={{ color: T.muted }}>{unsupportedMessage(rotationQ.data)}</div>
                ) : rotationQ.data?.supported ? (
                  <div className="flex flex-col gap-1 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                    <div className="flex flex-wrap items-center gap-2 text-[11px]">
                      <span className="font-bold" style={{ color: T.ink }}>{rotationQ.data.previous_crop ?? '—'} ← {rotationQ.data.candidate_crop ?? '—'}</span>
                      <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: rotationRatingBadge(rotationQ.data.rating).color, border: `1px solid ${T.line}` }}>{rotationQ.data.rating_ar ?? rotationRatingBadge(rotationQ.data.rating).label_ar}</span>
                    </div>
                    {rotReasons.map((r, i) => <div key={i} className="text-[11px]" style={{ color: T.muted }}>{r}</div>)}
                  </div>
                ) : null
              )}

              {/* مبادئ الدورة (تثقيفيّ) — تحميل كسول عند الطلب */}
              <div className="pt-1" style={{ borderTop: `1px dashed ${T.line}` }}>
                <button type="button" onClick={() => setShowPrinciples((v) => !v)} className="text-[11px] px-2 py-0.5 rounded-lg font-semibold" style={{ border: `1px solid ${T.line}`, color: '#86efac', background: SUB_BG }}>
                  {showPrinciples ? 'إخفاء المبادئ' : 'عرض مبادئ الدورة والمحاصيل المصنّفة'}
                </button>
                {showPrinciples && (
                  principlesQ.isLoading ? (
                    <div className="text-[11px] mt-1" style={{ color: T.faint }}>جارٍ قراءة المبادئ…</div>
                  ) : disabledMsg(principlesQ.data?.disabled) ?? (principlesQ.data ? (
                    <div className="flex flex-col gap-1 mt-1">
                      {(principlesQ.data.principles_ar ?? []).map((p, i) => <div key={i} className="text-[11px]" style={{ color: T.muted }}>• {p}</div>)}
                      {principlesQ.data.yemen_context_ar && <div className="text-[10px]" style={{ color: T.faint }}>{principlesQ.data.yemen_context_ar}</div>}
                      {cropTable.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 mt-1">
                          {cropTable.map((c) => (
                            <span key={c.crop} className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.muted }}>
                              {c.name_ar ?? c.crop} · {c.family ?? '—'} · {c.n_effect ?? '—'} · {c.season ?? '—'}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ) : null)
                )}
              </div>
            </div>
          )}
        </div>

        {/* ═══ WOFOST عبر المحاصيل ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<Wheat className="w-4 h-4 text-amber-300" aria-hidden="true" />} title="إرشاد تكيّف WOFOST + أنواع محاصيله" open={isOpen('wofost')} onToggle={() => toggle('wofost')} />
          {isOpen('wofost') && (
            <div className="flex flex-col gap-2 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <div className="flex flex-wrap items-center gap-2">
                <LabeledInput id="w-crop" label="المحصول المستهدف" value={wCrop} onChange={setWCrop} placeholder="حمضيات / citrus" width="w-28" />
              </div>
              {!wCrop.trim() ? (
                <div className="text-[11px]" style={{ color: T.faint }}>أدخِل محصولاً لإرشاد تعديل بارامتراته عن نموذج القمح الأساسي.</div>
              ) : guidanceQ.isLoading ? (
                <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة دليل التكيّف…</div>
              ) : disabledMsg(guidanceQ.data?.disabled) ?? (guidanceQ.data ? (
                <div className="flex flex-col gap-1 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                  <div className="flex flex-wrap items-center gap-2 text-[11px]">
                    <span className="font-bold" style={{ color: T.ink }}>{guidanceQ.data.model_type_ar ?? '—'}</span>
                    {guidanceQ.data.expected_change_pct && <span style={{ color: T.faint }}>تغيير: {guidanceQ.data.expected_change_pct}</span>}
                    {guidanceQ.data.typical_validation_r2 && <span style={{ color: T.faint }}>R²: {guidanceQ.data.typical_validation_r2}</span>}
                    {guidanceQ.data.crop_recognized === false && <span style={{ color: '#fdba74' }}>غير مصنّف صراحةً</span>}
                  </div>
                  {guidanceQ.data.adaptation_summary_ar && <div className="text-[11px]" style={{ color: T.muted }}>{guidanceQ.data.adaptation_summary_ar}</div>}
                  {guidanceQ.data.phenology_ar && <div className="text-[10px]" style={{ color: T.faint }}>الفينولوجيا: {guidanceQ.data.phenology_ar}</div>}
                  {keyParams.map((k, i) => (
                    <div key={`${k.param}-${i}`} className="text-[11px] rounded border p-1" style={{ borderColor: T.line, color: T.muted }}>
                      <span className="font-semibold" style={{ color: T.ink }}>{k.name_ar ?? k.param}</span>
                      {k.range && <span style={{ color: T.faint }}> · المدى {k.range}</span>}
                      {k.default_wheat && <span style={{ color: T.faint }}> · القمح {k.default_wheat}</span>}
                      {k.note_ar && <div style={{ color: T.muted }}>{k.note_ar}</div>}
                      {k.source_ar && <div className="text-[10px]" style={{ color: T.faint }}>المصدر: {k.source_ar}</div>}
                    </div>
                  ))}
                  {(guidanceQ.data.limitations_ar ?? []).map((l, i) => <div key={`l${i}`} className="text-[10px]" style={{ color: '#fdba74' }}>⚠ {l}</div>)}
                  {guidanceQ.data.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{guidanceQ.data.disclaimer_ar}</div>}
                </div>
              ) : null)}

              {/* أنواع نماذج المحاصيل — كسول عند الطلب */}
              <div className="pt-1" style={{ borderTop: `1px dashed ${T.line}` }}>
                <button type="button" onClick={() => setShowTypes((v) => !v)} className="text-[11px] px-2 py-0.5 rounded-lg font-semibold" style={{ border: `1px solid ${T.line}`, color: '#86efac', background: SUB_BG }}>
                  {showTypes ? 'إخفاء الأنواع' : 'عرض أنواع نماذج المحاصيل'}
                </button>
                {showTypes && (
                  cropTypesQ.isLoading ? (
                    <div className="text-[11px] mt-1" style={{ color: T.faint }}>جارٍ قراءة الأنواع…</div>
                  ) : disabledMsg(cropTypesQ.data?.disabled) ?? (modelTypes.length > 0 ? (
                    <div className="flex flex-col gap-1 mt-1">
                      {modelTypes.map((m) => (
                        <span key={m.key} className="text-[11px] px-2 py-0.5 rounded-lg" style={{ border: `1px solid ${T.line}`, color: T.ink }}>
                          <span style={{ color: T.faint }}>{m.name_ar ?? m.key}:</span> تغيير {m.change_pct ?? '—'} · R² {m.typical_r2 ?? '—'}
                        </span>
                      ))}
                      {cropTypesQ.data?.note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{cropTypesQ.data.note_ar}</div>}
                    </div>
                  ) : null)
                )}
              </div>
            </div>
          )}
        </div>

        {/* ═══ توصية ريّ موحّدة ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<Sprout className="w-4 h-4 text-sky-300" aria-hidden="true" />} title="توصية ريّ (صافٍ + ملوحة مشروطة)" open={isOpen('irrigation')} onToggle={() => toggle('irrigation')} />
          {isOpen('irrigation') && (
            <div className="flex flex-col gap-2 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <div className="flex flex-wrap items-center gap-2">
                <LabeledInput id="ir-crop" label="المحصول" value={irCrop} onChange={setIrCrop} placeholder={cropLabel || 'اختياريّ'} width="w-24" />
                <span className="inline-flex items-center gap-1">
                  <label htmlFor="ir-stage" className="text-[11px] font-bold" style={{ color: T.ink }}>المرحلة:</label>
                  <select id="ir-stage" value={irStage} onChange={(e) => setIrStage(e.target.value)} className={inputCls} style={inputStyle}>
                    {STAGE_OPTIONS.map((o) => <option key={o.key} value={o.key}>{o.label_ar}</option>)}
                  </select>
                </span>
                <LabeledInput id="ir-tmin" label="حرارة صغرى °م" value={irTmin} onChange={setIrTmin} type="number" width="w-14" />
                <LabeledInput id="ir-tmax" label="حرارة عظمى °م" value={irTmax} onChange={setIrTmax} type="number" width="w-14" />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <LabeledInput id="ir-rain" label="مطر حديث مم" value={irRain} onChange={setIrRain} type="number" width="w-14" />
                <LabeledInput id="ir-forecast" label="مطر متوقّع مم" value={irForecast} onChange={setIrForecast} type="number" width="w-14" />
                <LabeledInput id="ir-moist" label="رطوبة تربة ٪" value={irMoist} onChange={setIrMoist} type="number" width="w-14" />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[10px]" style={{ color: T.faint }}>ملوحة (اختياريّ — فحص مخبريّ):</span>
                <LabeledInput id="ir-ece" label="ECe" value={irEce} onChange={setIrEce} type="number" width="w-12" />
                <LabeledInput id="ir-tol" label="عتبة المحصول" value={irTol} onChange={setIrTol} type="number" width="w-12" />
                <LabeledInput id="ir-wec" label="ECw ماء" value={irWaterEc} onChange={setIrWaterEc} type="number" width="w-12" />
                <LabeledInput id="ir-drain" label="الصرف" value={irDrain} onChange={setIrDrain} placeholder="fast/medium/slow" width="w-24" />
                <LabeledInput id="ir-eff" label="كفاءة الريّ ٪" value={irEff} onChange={setIrEff} type="number" width="w-14" />
              </div>
              {tMin == null || tMax == null ? (
                <div className="text-[11px]" style={{ color: T.faint }}>أدخِل الحرارتَين الصغرى والعظمى (إجباريّتان لحساب ET₀).</div>
              ) : irrigationQ.isLoading ? (
                <div className="text-[11px]" style={{ color: T.faint }}>جارٍ حساب التوصية…</div>
              ) : disabledMsg(irrigationQ.data?.disabled) ?? (irrigationQ.data ? (
                <div className="flex flex-col gap-1 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                  <div className="flex flex-wrap items-center gap-2 text-[11px]">
                    <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: irrigationPolicyBadge(irrigationQ.data.policy).color, border: `1px solid ${T.line}` }}>{irrigationPolicyBadge(irrigationQ.data.policy).label_ar}</span>
                    {irrigationQ.data.requires_expert_review && <span style={{ color: '#fca5a5' }}>يلزم مراجعة خبير</span>}
                    {irrigationQ.data.urgency && <span style={{ color: T.faint }}>إلحاح: {irrigationQ.data.urgency}</span>}
                  </div>
                  <FactPills facts={irrFacts} />
                  {irrigationQ.data.timing_ar && <div className="text-[11px]" style={{ color: T.muted }}>التوقيت: {irrigationQ.data.timing_ar}</div>}
                  {irrigationQ.data.rationale_ar && <div className="text-[11px]" style={{ color: T.muted }}>{irrigationQ.data.rationale_ar}</div>}
                  {(irrigationQ.data.evidence ?? []).map((e, i) => (
                    <div key={i} className="text-[10px]" style={{ color: T.faint }}>— {e.note_ar ?? e.source} {e.value != null ? `(${fmtNum(e.value, 2)})` : ''}</div>
                  ))}
                </div>
              ) : null)}
            </div>
          )}
        </div>

        {/* ═══ الحالة التشغيليّة للحقل ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<Layers className="w-4 h-4 text-emerald-300" aria-hidden="true" />} title="الحالة التشغيليّة للحقل" open={isOpen('field-state')} onToggle={() => toggle('field-state')} />
          {isOpen('field-state') && (
            <div className="flex flex-col gap-2 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              {!fieldId ? noField : (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="inline-flex items-center gap-1">
                      <label htmlFor="fs-conf" className="text-[11px] font-bold" style={{ color: T.ink }}>مستوى الثقة:</label>
                      <select id="fs-conf" value={fsConf} onChange={(e) => setFsConf(e.target.value)} className={inputCls} style={inputStyle}>
                        {CONFIDENCE_OPTIONS.map((o) => <option key={o.key} value={o.key}>{o.label_ar}</option>)}
                      </select>
                    </span>
                    <LabeledInput id="fs-delta" label="تغيير الريّ ٪" value={fsDelta} onChange={setFsDelta} type="number" width="w-14" />
                    <LabeledInput id="fs-rain" label="مطر متوقّع مم" value={fsRain} onChange={setFsRain} type="number" width="w-14" />
                    <LabeledInput id="fs-moist" label="رطوبة/سعة ٪" value={fsMoist} onChange={setFsMoist} type="number" width="w-14" />
                    <LabeledInput id="fs-et0" label="ET₀ مم" value={fsEt0} onChange={setFsEt0} type="number" width="w-12" />
                    <LabeledInput id="fs-ndvi" label="عمر NDVI ي" value={fsNdvi} onChange={setFsNdvi} type="number" width="w-12" />
                    <LabeledInput id="fs-soil" label="عمر التربة ي" value={fsSoil} onChange={setFsSoil} type="number" width="w-12" />
                    <LabeledInput id="fs-wx" label="عمر الطقس س" value={fsWx} onChange={setFsWx} type="number" width="w-12" />
                  </div>
                  {fieldStateQ.isLoading ? (
                    <div className="text-[11px]" style={{ color: T.faint }}>جارٍ تركيب الحالة التشغيليّة…</div>
                  ) : disabledMsg(fs?.disabled) ?? (fs ? (
                    <div className="flex flex-col gap-1 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                      <div className="flex flex-wrap items-center gap-2 text-[11px]">
                        <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: validityBadge(fs.validity).color, border: `1px solid ${T.line}` }}>{validityBadge(fs.validity).label_ar}</span>
                        <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: executionModeBadge(fs.execution_mode).color, border: `1px solid ${T.line}` }}>{executionModeBadge(fs.execution_mode).label_ar}</span>
                        {fs.confidence_level && <span style={{ color: T.faint }}>ثقة: {fs.confidence_level}</span>}
                      </div>
                      {(fs.reasons_ar ?? []).map((r, i) => <div key={i} className="text-[11px]" style={{ color: T.muted }}>• {r}</div>)}
                      {fsConflicts.map((c, i) => <ConflictRow key={`c${i}`} c={c} />)}
                      {fsFreshness.map((c, i) => <ConflictRow key={`f${i}`} c={c} />)}
                      {fs.note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{fs.note_ar}</div>}
                    </div>
                  ) : null)}
                </>
              )}
            </div>
          )}
        </div>

        {/* ═══ تحسين محفظة الحقول ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<ScatterChart className="w-4 h-4 text-sky-300" aria-hidden="true" />} title="تحسين محفظة الحقول" open={isOpen('portfolio')} onToggle={() => toggle('portfolio')} />
          {isOpen('portfolio') && (
            <div className="flex flex-col gap-2 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <div className="text-[10px]" style={{ color: T.faint }}>الهامش والاحتياج المائيّ لكلّ حقل يُدخِلهما المستخدم (من حالة اقتصاديّة/خطّة ريّ) — لا تُلفَّق.</div>
              <div className="flex flex-wrap items-center gap-2">
                <label className="flex flex-col gap-0.5 text-[10px]" style={{ color: T.faint }}>
                  الحقل
                  <select
                    id="pf-id"
                    value={pfId}
                    onChange={(e) => setPfId(e.target.value)}
                    disabled={fieldOptionsQ.isLoading || fieldOptions.length === 0}
                    className="w-44 px-2 py-1 rounded-lg text-[11px]"
                    style={inputStyle}
                  >
                    <option value="">اختر حقلاً</option>
                    {fieldOptions.map((f) => <option key={f.id} value={f.id}>{f.name}{f.crop && f.crop !== '—' ? ` · ${f.crop}` : ''}</option>)}
                  </select>
                </label>
                <LabeledInput id="pf-margin" label="الهامش المتوقّع" value={pfMargin} onChange={setPfMargin} type="number" width="w-16" />
                <LabeledInput id="pf-demand" label="الاحتياج م³" value={pfDemand} onChange={setPfDemand} type="number" width="w-16" />
                <LabeledInput id="pf-area" label="المساحة هكتار" value={pfArea} onChange={setPfArea} type="number" width="w-14" />
                <button type="button" onClick={addPfField} className="text-[11px] px-2 py-0.5 rounded-lg font-semibold" style={{ border: `1px solid ${T.line}`, color: '#86efac', background: SUB_BG }}>+ أضِف حقلاً</button>
              </div>
              {pfFields.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {pfFields.map((f, i) => (
                    <span key={`${f.field_id}-${i}`} className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.muted }}>
                      {f.field_id}: هامش {fmtNum(f.expected_margin, 1)} · {fmtNum(f.water_demand_m3, 1)} م³
                    </span>
                  ))}
                  <button type="button" onClick={() => setPfFields([])} className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: '#fca5a5' }}>مسح</button>
                </div>
              )}
              <LabeledInput id="pf-total" label="ماء المزرعة المتاح م³" value={pfTotal} onChange={setPfTotal} type="number" width="w-24" />
              {pfFields.length === 0 || pfTotalWater == null ? (
                <div className="text-[11px]" style={{ color: T.faint }}>أضِف حقلاً واحداً على الأقلّ وأدخِل ماء المزرعة المتاح.</div>
              ) : portfolioQ.isLoading ? (
                <div className="text-[11px]" style={{ color: T.faint }}>جارٍ توزيع الماء…</div>
              ) : disabledMsg(portfolioQ.data?.disabled) ?? (portfolioQ.data ? (
                <div className="flex flex-col gap-1 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                  <FactPills facts={pfSummary} />
                  {pfRows.map((r, i) => (
                    <div key={`${r.field_id}-${i}`} className="flex flex-wrap items-center gap-2 text-[11px]" style={{ color: T.muted }}>
                      <span className="font-semibold" style={{ color: T.ink }}>{r.field_id}</span>
                      <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: portfolioStatusBadge(r.status).color, border: `1px solid ${T.line}` }}>{portfolioStatusBadge(r.status).label_ar}</span>
                      <span style={{ color: T.faint }}>مُخصَّص {fmtNum(r.allocated_m3, 1)} م³ ({pctFromFraction(r.fraction)})</span>
                      {r.expected_margin_captured != null && <span style={{ color: T.faint }}>هامش محقّق {fmtNum(r.expected_margin_captured, 1)}</span>}
                    </div>
                  ))}
                  {portfolioQ.data.calibrated === false && <div className="text-[10px]" style={{ color: '#fdba74' }}>غير معايَر (التوزيع الجزئيّ خطّيّ تقريبيّ)</div>}
                  {(portfolioQ.data.warnings_ar ?? []).map((w, i) => <div key={i} className="text-[10px]" style={{ color: '#fdba74' }}>⚠ {w}</div>)}
                </div>
              ) : null)}
            </div>
          )}
        </div>

        {/* ═══ التحقّق من صحّة الهندسة ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<MapPin className="w-4 h-4 text-emerald-300" aria-hidden="true" />} title="التحقّق من صحّة الهندسة" open={isOpen('geometry')} onToggle={() => toggle('geometry')} />
          {isOpen('geometry') && (
            <div className="flex flex-col gap-2 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <textarea
                value={geoText}
                onChange={(e) => setGeoText(e.target.value)}
                placeholder='ألصِق GeoJSON للحدّ (Polygon)… مثال: {"type":"Polygon","coordinates":[[...]]}'
                rows={3}
                className="w-full px-2 py-1 rounded-lg text-[11px] font-mono"
                style={inputStyle}
                dir="ltr"
              />
              <LabeledInput id="geo-crs" label="النظام المرجعيّ المُعلَن" value={geoCrs} onChange={setGeoCrs} placeholder="اختياريّ (مثل EPSG:4326)" width="w-40" />
              {parsedGeo.error ? (
                <div className="text-[11px]" style={{ color: '#fca5a5' }}>{parsedGeo.error}</div>
              ) : !parsedGeo.obj ? (
                <div className="text-[11px]" style={{ color: T.faint }}>ألصِق GeoJSON صالحاً للتحقّق (CRS/تقاطع ذاتي/مساحة/داخل اليمن).</div>
              ) : geometryQ.isLoading ? (
                <div className="text-[11px]" style={{ color: T.faint }}>جارٍ التحقّق من الهندسة…</div>
              ) : disabledMsg(geometryQ.data?.disabled) ?? (geometryQ.data ? (
                <div className="flex flex-col gap-1 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                  <div className="flex flex-wrap items-center gap-2 text-[11px]">
                    <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: geometryQ.data.valid ? '#86efac' : '#fca5a5', border: `1px solid ${T.line}` }}>{geometryQ.data.valid ? 'صالح' : 'غير صالح'}</span>
                    {geometryQ.data.has_warnings && <span style={{ color: '#fdba74' }}>فيه تحذيرات</span>}
                  </div>
                  <FactPills facts={geoFacts} />
                  {geoIssueList.map((iss, i) => {
                    const b = geometryIssueBadge(iss.severity);
                    return (
                      <div key={`${iss.code}-${i}`} className="flex flex-col gap-0.5 text-[11px]">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: b.color, border: `1px solid ${T.line}` }}>{b.label_ar}</span>
                          {iss.code && <span style={{ color: T.faint }}>{iss.code}</span>}
                        </div>
                        {iss.message_ar && <div style={{ color: T.muted }}>{iss.message_ar}</div>}
                        {iss.hint && <div className="text-[10px]" style={{ color: T.faint }}>{iss.hint}</div>}
                      </div>
                    );
                  })}
                </div>
              ) : null)}
            </div>
          )}
        </div>

        {/* ═══ تقرير العمليّات (CSV مدير) ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<FileSpreadsheet className="w-4 h-4 text-amber-300" aria-hidden="true" />} title="تقرير العمليّات (CSV — مدير)" open={isOpen('report')} onToggle={() => toggle('report')} />
          {isOpen('report') && (
            <div className="flex flex-col gap-2 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              {!isManager ? (
                <div className="text-[11px]" style={{ color: T.muted }}>تصدير تقرير العمليّة متاح لدور المالك/المدير (الخادم يتحقّق من المستأجِر والصلاحيّة).</div>
              ) : !fieldId ? noField : (
                <>
                  <div className="text-[10px]" style={{ color: T.faint }}>يُصدَّر صفّ هويّة الحقل المختار ضمن CSV ثنائي اللغة. مقاييس الريّ/التسميد لا تُعبَّأ آليّاً هنا (التقرير الخلفيّ نقيّ يستقبلها من المستدعي) — تظهر بقيَم الخادم الافتراضيّة لا مُختلَقة.</div>
                  <div className="flex flex-wrap items-center gap-2">
                    <LabeledInput id="or-name" label="اسم العمليّة" value={orName} onChange={setOrName} placeholder="مزرعة الوادي" width="w-32" />
                    <LabeledInput id="or-label" label="تسمية الحقل" value={orFieldLabel} onChange={setOrFieldLabel} placeholder={cropLabel || fieldId} width="w-28" />
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <LabeledInput id="or-start" label="من" value={orStart} onChange={setOrStart} type="date" width="w-32" placeholder="" />
                    <LabeledInput id="or-end" label="إلى" value={orEnd} onChange={setOrEnd} type="date" width="w-32" placeholder="" />
                    <button
                      type="button"
                      onClick={onExportReport}
                      disabled={!reportReady || reportMut.isPending}
                      className="px-2 py-0.5 rounded-lg text-[11px] font-semibold disabled:opacity-40"
                      style={{ border: `1px solid ${T.line}`, color: '#86efac', background: 'rgba(15,23,42,.45)' }}
                    >
                      {reportMut.isPending ? '…' : 'صدّر CSV'}
                    </button>
                  </div>
                  {!reportReady && <div className="text-[11px]" style={{ color: T.faint }}>أدخِل اسم العمليّة وفترتها لتفعيل التصدير.</div>}
                  {reportMut.isSuccess && <div className="text-[11px]" role="status" style={{ color: '#86efac' }}>تمّ توليد الملفّ وتنزيله.</div>}
                  {reportMut.isError && <div className="text-[11px]" role="status" style={{ color: '#fca5a5' }}>تعذّر التصدير — قد يكون المستأجِر غير مطابق أو الخدمة غير متاحة.</div>}
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

/** حكم فحص الاتّساق (متّسق/يحتاج مراجعة + عدد القواعد + التناقضات) — النصوص من الخادم. */
function ConsistencyVerdict({ resp }: { resp: import('../../lib/agronomyConsistency').ConsistencyResponse }) {
  const conflicts = conflictRows(resp);
  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-2 text-[11px]">
        <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: resp.consistent ? '#86efac' : '#fca5a5', border: `1px solid ${T.line}` }}>
          {resp.consistent ? 'متّسق' : 'يوجد تناقض'}
        </span>
        {resp.requires_human_review && <span style={{ color: '#fca5a5' }}>يتطلّب مراجعة بشريّة</span>}
        {resp.checked_rules != null && <span style={{ color: T.faint }}>قواعد مفحوصة: {resp.checked_rules}</span>}
      </div>
      {conflicts.map((c, i) => <ConflictRow key={i} c={c} />)}
      {resp.note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{resp.note_ar}</div>}
    </div>
  );
}
