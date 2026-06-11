// ═══════════════════════════════════════════════════════════════
// SAHOOL — WeatherAdvicePage (الطقس والريّ)
// توصية ريّ (FAO-56) + مخاطر أمراض لكلّ حقل، بيانات حيّة عبر البوابة:
//   GET /api/v1/fields/{id}/weather/irrigation-advice  (field:view)
//   GET /api/v1/fields/{id}/weather/disease-risk       (field:view)
// تُحسبان من الطقس الحيّ (Open-Meteo) ومحصول الموسم النشط. لا بيانات مُلفَّقة —
// عند الخطأ/الفراغ تُعرض حالة صادقة (StateViews). 503 = الطقس/القاعدة معطّلة.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { CloudRain, Droplets, Bug, Map, Clock, Thermometer, Wind } from 'lucide-react';
import { useFields, useIrrigationAdvice, useDiseaseRisk } from '../hooks/useApi';
import type { IrrigationAdvice, DiseaseRisk } from '../services/api';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';

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

const input = 'px-3 py-2 rounded-lg text-sm w-full';
const inputStyle = { background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' } as const;

// رسالة خطأ صادقة مُشتقّة من رمز الحالة.
function errorDetail(err: unknown): string {
  const status = (err as any)?.response?.status;
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

// ── بطاقة توصية الريّ ─────────────────────────────────────────────
function IrrigationCard({ fieldId }: { fieldId: string }) {
  const { data, isLoading, isError, error, refetch } = useIrrigationAdvice(fieldId);

  return (
    <div className="rounded-xl p-4 border" style={{ background: '#0f1117', borderColor: '#334155' }} dir="rtl">
      <div className="flex items-center gap-2 mb-3">
        <Droplets className="w-4 h-4 text-emerald-400" />
        <span className="text-sm font-semibold text-slate-200">توصية الريّ (FAO-56)</span>
      </div>
      {isLoading ? (
        <LoadingState message="جارٍ حساب توصية الريّ…" />
      ) : isError ? (
        <ErrorState title="تعذّر حساب توصية الريّ" detail={errorDetail(error)} onRetry={() => refetch()} />
      ) : (
        <IrrigationBody a={data as IrrigationAdvice} />
      )}
    </div>
  );
}

function IrrigationBody({ a }: { a: IrrigationAdvice }) {
  const u = URGENCY_STYLE[a.urgency] ?? { label: a.urgency, bg: '#33415544', fg: '#cbd5e1' };
  return (
    <div className="space-y-3">
      <div className="flex items-end justify-between gap-2">
        <div>
          <div className="text-3xl font-bold text-slate-100">{a.recommended_mm}<span className="text-base text-slate-400"> مم</span></div>
          <div className="text-[11px] text-slate-500 mt-0.5">العمق الموصى به</div>
        </div>
        <Badge s={u} />
      </div>
      <div className="flex items-center gap-1.5 text-xs text-slate-300">
        <Clock className="w-3.5 h-3.5 text-slate-500" /> التوقيت: {a.timing_ar}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-400">
        <span>المحصول: {cropLabel(a.crop)}</span>
        <span>المرحلة: {a.stage}</span>
        <span>ET₀: {a.et0} مم</span>
        <span>Kc: {a.kc}</span>
      </div>
      <p className="text-xs text-slate-300 leading-relaxed">{a.rationale_ar}</p>
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
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-400">
        <span className="inline-flex items-center gap-1"><Thermometer className="w-3 h-3 text-slate-500" /> {r.temperature_c}°م</span>
        <span className="inline-flex items-center gap-1"><Wind className="w-3 h-3 text-slate-500" /> رطوبة {r.humidity_pct}٪</span>
        <span className="inline-flex items-center gap-1"><CloudRain className="w-3 h-3 text-slate-500" /> مطر ٣ أيّام {r.rain_mm_3d} مم</span>
      </div>
      {r.diseases_ar.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {r.diseases_ar.map((d) => (
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
  const { data: fieldsData, isLoading, isError, error, refetch } = useFields();
  const [fieldId, setFieldId] = useState<string>('');

  const fields = ((fieldsData as { fields?: any[] } | undefined)?.fields ?? []).map((f) => ({
    id: String(f.field_id ?? f.id),
    name: String(f.name_ar ?? f.name ?? 'حقل'),
  }));

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
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <IrrigationCard fieldId={fieldId} />
          <DiseaseCard fieldId={fieldId} />
        </div>
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
