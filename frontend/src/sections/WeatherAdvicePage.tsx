// ═══════════════════════════════════════════════════════════════
// SAHOOL — WeatherAdvicePage (الطقس والريّ) — واجهة رفيعة (WS-D.2e)
// توصية الريّ تستهلك المسار الكنسيّ الوحيد (مرشَّح → قرار → اعتماد):
//   POST /api/v1/fields/{id}/irrigation-recommendation  (candidate + approval_state)
//   GET  /api/v1/fields/{id}/weather/disease-risk       (منتج طقس مستقلّ — يبقى)
// لا حساب محلّيّ (ET0/Kc/Water-Balance): تُعرَض قيَم الخادم كما تأتي. لا بيانات مُلفَّقة —
// حالة متدهورة (طقس مفقود/استنزاف ناقص) ⇒ حالة صادقة بلا توصية. لا endpoint ريّ قديم.
// خطوات لاحقة (تدريجيّة): إعادة التسمية إلى Field Advisory ثمّ إزالة weather/irrigation-advice.
// ═══════════════════════════════════════════════════════════════
import { useSelectedField } from '../hooks/useSelectedField';
import { CloudRain, Droplets, Bug, Map, Clock, Thermometer, Wind } from 'lucide-react';
import { useDiseaseRisk } from '../hooks/useApi';
import {
  useFieldIrrigationRecommendation,
  isRecommendationReady,
  type IrrigationRecommendationReady,
} from '../hooks/useFieldIrrigationRecommendation';
import type { DiseaseRisk } from '../services/api';
import { asApiError } from '../services/api';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';
import { SegmentedScale, type ScaleBand } from '../components/insights/ScaleLegend';
import { OPERATION_SUITABILITY_BANDS } from '../components/insights/scalePresets';

// ── ألوان/تسميات الإلحاح والخطر ──────────────────────────────────
const URGENCY_STYLE: Record<string, { label: string; bg: string; fg: string }> = {
  none:     { label: 'لا حاجة',  bg: '#16a34a22', fg: '#4ade80' },
  low:      { label: 'منخفض',    bg: '#65a30d22', fg: '#a3e635' },
  moderate: { label: 'متوسّط',   bg: '#f59e0b22', fg: '#fbbf24' },
  high:     { label: 'عاجل',     bg: '#dc262622', fg: '#f87171' },
};
const RISK_STYLE: Record<string, { label: string; bg: string; fg: string }> = {
  low:      { label: 'منخفض',  bg: '#16a34a22', fg: '#4ade80' },
  moderate: { label: 'متوسّط', bg: '#f59e0b22', fg: '#fbbf24' },
  high:     { label: 'مرتفع',  bg: '#dc262622', fg: '#f87171' },
};

// سلالم بصريّة (نطاقات) تطابق مستويات الخدمة النصّيّة — تُبرِز النطاق النشط بصريّاً.
const IRRIGATION_URGENCY_ORDER = ['none', 'low', 'moderate', 'high'];
const IRRIGATION_URGENCY_SCALE: ScaleBand[] = [
  { label: 'لا حاجة', color: '#16a34a', hint: 'رطوبة كافية — لا ريّ قريب.' },
  { label: 'منخفض', color: '#84cc16', hint: 'تابِع — قد يلزم ريّ خلال أيّام.' },
  { label: 'متوسّط', color: '#f59e0b', hint: 'خطّط لريّ قريب لتفادي الإجهاد المائيّ.' },
  { label: 'عاجل', color: '#dc2626', hint: 'إجهاد مائيّ مرتفع — ريّ فوريّ مُوصى به.' },
];
const DISEASE_RISK_ORDER = ['low', 'moderate', 'high'];
const DISEASE_RISK_SCALE: ScaleBand[] = [
  { label: 'منخفض', color: '#16a34a', hint: 'ظروف غير مواتية للمرض — مخاطرة دنيا.' },
  { label: 'متوسّط', color: '#f59e0b', hint: 'ظروف جزئيّة — راقِب الرطوبة والحقل.' },
  { label: 'مرتفع', color: '#dc2626', hint: 'ظروف عدوى مواتية — تدخّل وقائيّ مُوصى به.' },
];

const input = 'px-3 py-2 rounded-lg text-sm w-full';
const inputStyle = { background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' } as const;

// رسالة خطأ صادقة مُشتقّة من رمز الحالة.
function errorDetail(err: unknown): string {
  const status = asApiError(err).response?.status;
  if (status === 503) return 'خدمة الطقس غير متاحة حاليّاً (مصدر الطقس أو القاعدة معطّل).';
  if (status === 422) return 'الحقل بلا إحداثيّات — حدّد موقعه أوّلاً لجلب الطقس.';
  if (status === 404) return 'الحقل غير موجود ضمن هذا المستأجِر.';
  if (status === 403) return 'لا تملك صلاحية هذه العملية (field:view).';
  if (status === 401) return 'انتهت الجلسة. يُرجى تسجيل الدخول من جديد.';
  return 'تعذّر الاتصال بخدمة الطقس.';
}

function Badge({ s }: { s: { label: string; bg: string; fg: string } }) {
  return (
    <span className="px-2 py-0.5 rounded-full text-[11px] font-medium" style={{ background: s.bg, color: s.fg }}>
      {s.label}
    </span>
  );
}

const cropLabel = (c: string | null) => (c && c !== '—' ? c : 'غير محدّد');

// حالة الاعتماد (WS-D.2d) — «اروِ» ليس قراراً نهائيّاً قبل approved.
const APPROVAL_STYLE: Record<string, { label: string; bg: string; fg: string }> = {
  not_submitted: { label: 'مرشَّح — غير مُقدَّم', bg: '#33415544', fg: '#cbd5e1' },
  pending_approval: { label: 'بانتظار الاعتماد', bg: '#f59e0b22', fg: '#fbbf24' },
  submit_unavailable: { label: 'تعذّر التقديم', bg: '#dc262622', fg: '#f87171' },
  approved: { label: 'مُعتمَد', bg: '#16a34a22', fg: '#4ade80' },
  rejected: { label: 'مرفوض', bg: '#dc262622', fg: '#f87171' },
};

// ── بطاقة توصية الريّ (WS-D.2e: واجهة رفيعة على المسار الكنسيّ irrigation-recommendation) ──
// لا تحسب شيئاً محلّيّاً؛ تستهلك المرشَّح الواعي بالاستنزاف (candidate → decision) بجلب
// طقس تلقائيّ من الخادم (WS-D.2c). مصدر الحقيقة واحد — لا endpoint ريّ قديم.
function IrrigationCard({ fieldId }: { fieldId: string }) {
  const { data, loading, error, refetch } = useFieldIrrigationRecommendation(fieldId, null);

  return (
    <div className="rounded-xl p-4 border" style={{ background: '#0f1117', borderColor: '#334155' }} dir="rtl">
      <div className="flex items-center gap-2 mb-3">
        <Droplets className="w-4 h-4 text-emerald-400" />
        <span className="text-sm font-semibold text-slate-200">توصية الريّ (FAO-56)</span>
      </div>
      {loading ? (
        <LoadingState message="جارٍ حساب توصية الريّ…" />
      ) : error ? (
        <ErrorState title="تعذّر حساب توصية الريّ" detail={errorDetail(error)} onRetry={() => refetch()} />
      ) : isRecommendationReady(data) ? (
        <IrrigationBody a={data} />
      ) : (
        // صدق: حالة متدهورة (استنزاف ناقص/غير متّسق/طقس مفقود) ⇒ لا توصية مُلفَّقة.
        <EmptyState
          icon={<Droplets className="w-8 h-8" />}
          title={
            data?.status === 'dependency_unavailable'
              ? 'الطقس غير متاح — لا توصية'
              : data?.status === 'insufficient_data'
                ? 'بيانات الاستنزاف ناقصة'
                : data?.status === 'inconsistent_state'
                  ? 'حالة رطوبة غير متّسقة'
                  : 'لا توصية متاحة'
          }
          hint={(data?.limitations ?? []).join(' · ') || 'تحتاج بيانات حقل أحدث لإصدار توصية.'}
        />
      )}
    </div>
  );
}

function IrrigationBody({ a }: { a: IrrigationRecommendationReady }) {
  const rec = a.recommendation;
  const u = URGENCY_STYLE[rec.urgency] ?? { label: rec.urgency, bg: '#33415544', fg: '#cbd5e1' };
  const approval = APPROVAL_STYLE[a.approval_state ?? 'not_submitted'] ?? APPROVAL_STYLE.not_submitted;
  return (
    <div className="space-y-3">
      <div className="flex items-end justify-between gap-2">
        <div>
          <div className="text-3xl font-bold text-slate-100">
            {rec.net_irrigation_mm}
            <span className="text-base text-slate-400"> مم</span>
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">العمق الصافي الموصى به (مرشَّح)</div>
        </div>
        <Badge s={u} />
      </div>
      <SegmentedScale
        title="إلحاح الريّ"
        bands={IRRIGATION_URGENCY_SCALE}
        activeIndex={Math.max(0, IRRIGATION_URGENCY_ORDER.indexOf(rec.urgency))}
      />
      {/* WS-D.2d: حالة الاعتماد — «اروِ» ليس قراراً نهائيّاً قبل approved. */}
      <div className="flex items-center justify-between gap-2 text-xs">
        <span className="text-slate-400">حالة القرار</span>
        <Badge s={approval} />
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-400">
        <span>المحصول: {cropLabel(a.inputs.crop)}</span>
        <span>المرحلة: {a.inputs.stage}</span>
        {a.et0?.et0_mm != null && <span>ET₀: {a.et0.et0_mm} مم</span>}
        {a.weather?.source && <span>الطقس: {a.weather.source === 'weather-engine-forecast' ? 'تلقائيّ' : a.weather.source}</span>}
      </div>
      <p className="text-xs text-slate-500 leading-relaxed">
        {rec.trigger_reason} — مرشَّح لخدمة القرار (لا تنفيذ قبل الاعتماد).
      </p>
    </div>
  );
}

// ── بطاقة مخاطر الأمراض ───────────────────────────────────────────
function DiseaseCard({ fieldId }: { fieldId: string }) {
  const { data, isLoading, isError, error, refetch } = useDiseaseRisk(fieldId);

  return (
    <div className="rounded-xl p-4 border" style={{ background: '#0f1117', borderColor: '#334155' }} dir="rtl">
      <div className="flex items-center gap-2 mb-3">
        <Bug className="w-4 h-4 text-emerald-400" />
        <span className="text-sm font-semibold text-slate-200">مخاطر الأمراض</span>
      </div>
      {isLoading ? (
        <LoadingState message="جارٍ تقييم مخاطر الأمراض…" />
      ) : isError ? (
        <ErrorState title="تعذّر تقييم مخاطر الأمراض" detail={errorDetail(error)} onRetry={() => refetch()} />
      ) : (
        <DiseaseBody r={data as DiseaseRisk} />
      )}
    </div>
  );
}

function DiseaseBody({ r }: { r: DiseaseRisk }) {
  const s = RISK_STYLE[r.risk_level] ?? { label: r.risk_level, bg: '#33415544', fg: '#cbd5e1' };
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm text-slate-300">مستوى الخطر</span>
        <Badge s={s} />
      </div>
      <SegmentedScale
        title="مخاطر الأمراض"
        bands={DISEASE_RISK_SCALE}
        activeIndex={Math.max(0, DISEASE_RISK_ORDER.indexOf(r.risk_level))}
      />
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-400">
        <span className="inline-flex items-center gap-1"><Thermometer className="w-3 h-3 text-slate-500" /> {r.temperature_c}°م</span>
        <span className="inline-flex items-center gap-1"><Wind className="w-3 h-3 text-slate-500" /> رطوبة {r.humidity_pct}٪</span>
        <span className="inline-flex items-center gap-1"><CloudRain className="w-3 h-3 text-slate-500" /> مطر ٣ أيّام {r.rain_mm_3d} مم</span>
      </div>
      {(r.diseases_ar ?? []).length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {(r.diseases_ar ?? []).map((d) => (
            <span key={d} className="px-2 py-0.5 rounded-lg text-[11px]" style={{ background: '#1e293b', color: '#cbd5e1', border: '1px solid #334155' }}>
              {d}
            </span>
          ))}
        </div>
      )}
      <p className="text-xs text-slate-300 leading-relaxed">{r.advice_ar}</p>
    </div>
  );
}

// ── الصفحة ──────────────────────────────────────────────────────
export default function WeatherAdvicePage() {
  // «الحقل النشط» المشترك (useSelectedField) — يتبع المستخدم عبر الشاشات؛ يُهيّأ
  // بأوّل حقل بدل بدء فارغ، فينتقل المزارع من الأقمار إلى الطقس بحقله محفوظاً.
  const { options: fields, isLoading, isError, error, refetch, fieldId, setFieldId } = useSelectedField();

  return (
    <div className="space-y-5 max-w-5xl mx-auto" dir="rtl">
      <div>
        <h2 className="text-xl font-bold text-slate-100">الطقس والريّ</h2>
        <p className="text-sm text-slate-400">توصية ريّ ومخاطر أمراض محسوبة من الطقس الحيّ لكلّ حقل</p>
      </div>

      {/* اختيار الحقل */}
      <div className="rounded-xl p-4 border" style={{ background: '#0f1117', borderColor: '#334155' }}>
        <div className="flex items-center gap-2 mb-3">
          <Map className="w-4 h-4 text-emerald-400" />
          <span className="text-sm font-semibold text-slate-200">اختر الحقل</span>
        </div>
        {isLoading ? (
          <LoadingState message="جارٍ تحميل الحقول…" />
        ) : isError ? (
          <ErrorState title="تعذّر تحميل الحقول" detail={errorDetail(error)} onRetry={() => refetch()} />
        ) : fields.length === 0 ? (
          <EmptyState
            icon={<Map className="w-8 h-8" />}
            title="لا توجد حقول بعد"
            hint="أضِف حقلاً أوّلاً من شاشة «إدارة الحقول» لعرض توصيات الطقس."
          />
        ) : (
          <select className={input} style={inputStyle} value={fieldId} onChange={(e) => setFieldId(e.target.value)}>
            <option value="">— اختر حقلاً —</option>
            {fields.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        )}
      </div>

      {/* البطاقات عند اختيار حقل */}
      {fieldId ? (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <IrrigationCard fieldId={fieldId} />
            <DiseaseCard fieldId={fieldId} />
          </div>
          {/* مرجع: سلّم ملاءمة الطقس للعمليّات الحقليّة (0..1) — يطابق طبقات الطقس على الخريطة */}
          <div className="rounded-xl p-4 border" style={{ background: '#0f1117', borderColor: '#334155' }}>
            <div className="flex items-center gap-2 mb-3">
              <CloudRain className="w-4 h-4 text-emerald-400" />
              <span className="text-sm font-semibold text-slate-200">ملاءمة الطقس للعمليّات الحقليّة</span>
            </div>
            <SegmentedScale bands={OPERATION_SUITABILITY_BANDS} title="مقياس الملاءمة (٠ → ١)" />
            <p className="text-[11px] text-slate-500 mt-2 leading-relaxed">
              يُستعمَل هذا المقياس في طبقات الطقس على الخريطة (الرشّ، السير على التربة…): كلّما اقتربت
              القيمة من ١ كانت النافذة أنسب للتنفيذ الآمن والفعّال.
            </p>
          </div>
        </>
      ) : (
        fields.length > 0 && (
          <EmptyState
            icon={<CloudRain className="w-8 h-8" />}
            title="اختر حقلاً لعرض توصياته"
            hint="ستظهر توصية الريّ ومخاطر الأمراض المحسوبة من الطقس الحالي."
          />
        )
      )}
    </div>
  );
}
