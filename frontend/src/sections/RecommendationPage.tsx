// ════════════════════════════════════════════════════════════
// SAHOOL — صفحة التوصية المتكاملة (مربوطة بالمحرّك الحقيقيّ)
// قسمان:
//   ١) عمود التوصيات الموحَّد لكلّ حقل (GET /api/v1/fields/{id}/recommendations):
//      الريّ + التسميد + الأمراض + الحصاد في مكان واحد، مفروز بالأولويّة. تدهور
//      رشيق: عند تعذّر الطقس يُعرض ما لا يحتاجه (تسميد/حصاد) بصدق — لا رقم وهميّ.
//   ٢) التوصية المتكاملة من المحرّك (POST /recommendations/for-field): «شهادة
//      الجودة» تُبنى خادميّاً ثمّ يُشغَّل المحرّك. عند نقص البيانات حالة محجوبة.
// صدق في كلا القسمين: عند الخطأ/نقص البيانات حالة صادقة — لا سيناريو مفبرَك.
// ════════════════════════════════════════════════════════════
import { useState } from 'react';
import {
  ClipboardList, Sparkles, ChevronDown, ChevronUp,
  Droplets, FlaskConical, Bug, Wheat, LayoutList,
} from 'lucide-react';
import { useFieldRecommendation, useFieldRecommendations } from '../hooks/useApi';
import { useSelectedField } from '../hooks/useSelectedField';
import { ErrorState, LoadingState, EmptyState } from '../components/StateViews';
import SpeakButton from '../components/SpeakButton';
import type { FieldRecommendation, FieldRecommendationsResult } from '../services/api';

const CROPS = ['قمح صلب', 'شعير', 'ذرة صفراء', 'طماطم', 'بطاطس', 'خضروات', 'برسيم', 'سورغم'];

const GRADE_COLOR: Record<string, string> = {
  HIGH: '#16a34a', MEDIUM: '#ca8a04', LOW: '#f97316', BLOCKED: '#dc2626', UNKNOWN: '#6b7280',
};

// لون/تسمية الأولويّة للعمود الموحَّد.
const PRIORITY_META: Record<string, { color: string; label: string; order: number }> = {
  high:   { color: '#dc2626', label: 'عالية',  order: 0 },
  medium: { color: '#ca8a04', label: 'متوسّطة', order: 1 },
  low:    { color: '#16a34a', label: 'منخفضة', order: 2 },
};

// أيقونة + اسم عربيّ لكلّ فئة توصية.
const CATEGORY_META: Record<string, { Icon: typeof Droplets; label: string }> = {
  irrigation: { Icon: Droplets,     label: 'الريّ' },
  fertilizer: { Icon: FlaskConical, label: 'التسميد' },
  disease:    { Icon: Bug,          label: 'الأمراض' },
  yield:      { Icon: Wheat,        label: 'الحصاد' },
};

function asText(v: unknown): string {
  if (v == null) return '';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

// ثقة المحرّك الزراعيّ (نصّيّة لا رقميّة — تُورَّث من أدنى سقف مصدر).
const CONF_META: Record<string, { label: string; color: string }> = {
  high:   { label: 'ثقة عالية',       color: '#22c55e' },
  medium: { label: 'ثقة متوسّطة',     color: '#eab308' },
  low:    { label: 'ثقة منخفضة',      color: '#f97316' },
  none:   { label: 'بلا ثقة كافية',   color: '#ef4444' },
};

// شارة الثقة/الجاهزيّة + أسباب الحالة (Provenance UX) — من field_state الذي ترسله
// الخلفيّة أصلاً مع التوصيات. لا تخمين: تظهر فقط حين تتوفّر الحقول.
function FieldStateBanner({ data }: { data: FieldRecommendationsResult }) {
  const fs = data.field_state;
  if (!fs && !data.requires_review) return null;
  const conf = fs?.confidence_level ? CONF_META[fs.confidence_level] : null;
  const reasons = fs?.reasons_ar ?? [];
  return (
    <div className="rounded-lg border border-slate-700 bg-[#16202e] px-3 py-2 space-y-1">
      <div className="flex items-center gap-2 flex-wrap">
        {conf && (
          <span
            className="text-xs px-2 py-0.5 rounded-full font-semibold"
            style={{ background: `${conf.color}22`, color: conf.color }}
          >
            {conf.label}
          </span>
        )}
        {data.requires_review && (
          <span className="text-xs px-2 py-0.5 rounded-full font-semibold text-amber-300 bg-amber-500/15">
            يحتاج مراجعة بشريّة
          </span>
        )}
      </div>
      {reasons.length > 0 && (
        <ul className="text-[11px] text-slate-400 list-disc pr-4 space-y-0.5">
          {reasons.slice(0, 3).map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── القسم ١: عمود التوصيات الموحَّد ───────────────────────────
function UnifiedRecommendations({ fieldId }: { fieldId: string }) {
  const q = useFieldRecommendations(fieldId || undefined);

  if (!fieldId) {
    return (
      <EmptyState
        title="اختر حقلاً"
        hint="اختر حقلاً من القائمة أعلاه لعرض توصياته الموحَّدة (الريّ والتسميد والأمراض والحصاد)."
      />
    );
  }
  if (q.isLoading) return <LoadingState message="جارٍ جمع توصيات الحقل…" />;
  if (q.isError) {
    return (
      <ErrorState
        title="تعذّر جلب توصيات الحقل"
        detail="قد يكون الطقس أو سياق الموسم غير متاح حاليّاً (لا بيانات وهميّة)."
        onRetry={() => q.refetch()}
      />
    );
  }

  const data = q.data;
  const recs = data?.recommendations ?? [];
  if (recs.length === 0) {
    return (
      <EmptyState
        title="لا توصيات متاحة"
        hint="لم نتمكّن من توليد توصيات لهذا الحقل بعد — حدّد موقع الحقل وموسمه النشط."
      />
    );
  }

  const sorted = [...recs].sort(
    (a, b) =>
      (PRIORITY_META[a.priority]?.order ?? 9) - (PRIORITY_META[b.priority]?.order ?? 9),
  );

  return (
    <div className="space-y-3">
      {data && <FieldStateBanner data={data} />}
      {data && !data.weather_available && (
        <p className="text-xs text-amber-300 bg-[#2a2310] rounded-lg px-3 py-2">
          الطقس غير متاح حاليّاً — تُعرض توصيات التسميد/الحصاد فقط (لا ريّ/أمراض). لا بيانات وهميّة.
        </p>
      )}
      {sorted.map((rec, i) => (
        <RecCard key={`${rec.category}-${i}`} rec={rec} />
      ))}
    </div>
  );
}

function RecCard({ rec }: { rec: FieldRecommendation }) {
  const cat = CATEGORY_META[rec.category] ?? { Icon: LayoutList, label: rec.category };
  const pri = PRIORITY_META[rec.priority] ?? { color: '#6b7280', label: rec.priority, order: 9 };
  const { Icon } = cat;
  return (
    <div
      className="rounded-xl border p-4"
      style={{ background: '#1e293b', borderColor: `${pri.color}44` }}
    >
      <div className="flex items-center justify-between mb-2 gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Icon className="w-4 h-4 shrink-0" style={{ color: pri.color }} />
          <span className="text-xs text-slate-400 shrink-0">{cat.label}</span>
          <span className="text-sm font-semibold text-slate-100 truncate">{rec.title_ar}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {rec.safety && (
            <span className="text-xs px-2 py-0.5 rounded-full font-semibold text-red-300 bg-red-500/15">
              سلامة
            </span>
          )}
          <span
            className="text-xs px-2 py-0.5 rounded-full font-semibold"
            style={{ background: `${pri.color}22`, color: pri.color }}
          >
            {pri.label}
          </span>
          <SpeakButton text={[rec.title_ar, rec.detail_ar].filter(Boolean).join('. ')} />
        </div>
      </div>
      <p className="text-sm text-slate-300 leading-relaxed">{rec.detail_ar}</p>
      <p className="text-[11px] text-slate-500 mt-2">{rec.source}</p>
    </div>
  );
}

export default function RecommendationPage() {
  const [crop, setCrop] = useState(CROPS[0]);
  const [farmId, setFarmId] = useState('');
  const [growthStage, setGrowthStage] = useState('');
  const [showBackend, setShowBackend] = useState(false);
  const mut = useFieldRecommendation();

  // قائمة الحقول والاختيار من FieldView المشترك؛ أي اختيار هنا يتبع باقي الشاشات.
  const { options: fields, isLoading: fieldsLoading, isError: fieldsError, fieldId, setFieldId } = useSelectedField();

  const submit = () => {
    if (!fieldId.trim()) return;
    mut.mutate({
      field_id: fieldId.trim(),
      farm_id: farmId.trim() || undefined,
      crop,
      growth_stage: growthStage.trim() || undefined,
    });
  };

  const res = mut.data;
  const rec = (res?.recommendation ?? {}) as Record<string, unknown>;
  const grade = asText(rec.quality_grade || 'UNKNOWN').toUpperCase();
  const gradeColor = GRADE_COLOR[grade] ?? '#6b7280';
  const headline = asText(rec.headline) || (res && !res.delivered ? 'تعذّر إصدار توصية' : '');
  const predicted = rec.predicted_yield_t_ha;

  return (
    <div className="space-y-6 max-w-3xl mx-auto" dir="rtl">
      <div className="flex items-center gap-2">
        <ClipboardList className="w-5 h-5 text-emerald-400" />
        <h2 className="text-xl font-bold text-slate-100">التوصيات المتكاملة</h2>
      </div>

      {/* ── القسم ١: عمود التوصيات الموحَّد لكلّ حقل ── */}
      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <LayoutList className="w-4 h-4 text-emerald-400" />
          <h3 className="text-base font-semibold text-slate-100">العمود الموحَّد للحقل</h3>
        </div>
        <p className="text-sm text-slate-400">
          توصيات الحقل في مكان واحد: الريّ والتسميد والأمراض والحصاد — مفروزة بالأولويّة.
          عند تعذّر الطقس تُعرض التوصيات التي لا تحتاجه بصدق، لا بيانات وهميّة.
        </p>

        {/* اختيار الحقل */}
        <div className="rounded-xl border p-4" style={{ background: '#1e293b', borderColor: '#334155' }}>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">الحقل</span>
            {fieldsLoading ? (
              <span className="text-sm text-slate-400">جارٍ تحميل الحقول…</span>
            ) : fieldsError ? (
              <span className="text-sm text-red-400">تعذّر تحميل قائمة الحقول.</span>
            ) : fields.length === 0 ? (
              <span className="text-sm text-slate-400">لا حقول متاحة — أنشئ حقلاً أوّلاً.</span>
            ) : (
              <select
                value={fieldId}
                onChange={e => setFieldId(e.target.value)}
                className="px-3 py-2 rounded-lg text-sm"
                style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}
              >
                {fields.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}{f.crop && f.crop !== '—' ? ` — ${f.crop}` : ''}
                  </option>
                ))}
              </select>
            )}
          </label>
        </div>

        <UnifiedRecommendations fieldId={fieldId} />
      </section>

      {/* فاصل */}
      <div className="border-t" style={{ borderColor: '#334155' }} />

      {/* ── القسم ٢: التوصية المتكاملة من المحرّك ── */}
      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-emerald-400" />
          <h3 className="text-base font-semibold text-slate-100">التوصية المتكاملة (المحرّك)</h3>
        </div>
        <p className="text-sm text-slate-400">
          يبني الخادم «شهادة الجودة» من ملاحظات حقلك ثمّ يشغّل محرّك التوصية. عند نقص
          البيانات تظهر حالة محجوبة تُبيّن ما يلزم قياسه — لا رقم وهمي.
        </p>

        {/* Form */}
        <div className="rounded-xl border p-4 space-y-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">المحصول</span>
              <select value={crop} onChange={e => setCrop(e.target.value)}
                className="px-3 py-2 rounded-lg text-sm" style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}>
                {CROPS.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">معرّف الحقل</span>
              <input value={fieldId} onChange={e => setFieldId(e.target.value)} placeholder="field_06"
                className="px-3 py-2 rounded-lg text-sm" style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">مرحلة النموّ (اختياريّ)</span>
              <input value={growthStage} onChange={e => setGrowthStage(e.target.value)} placeholder="tillering"
                className="px-3 py-2 rounded-lg text-sm" style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">معرّف المزرعة (اختياريّ — للصلاحيّة المحدودة)</span>
              <input value={farmId} onChange={e => setFarmId(e.target.value)} placeholder="farm_01"
                className="px-3 py-2 rounded-lg text-sm" style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
            </label>
          </div>
          <div className="flex justify-end">
            <button onClick={submit} disabled={mut.isPending || !fieldId.trim()}
              className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-60"
              style={{ background: '#16a34a' }}>
              <Sparkles className="w-4 h-4" />
              {mut.isPending ? 'جارٍ التوليد…' : 'اطلب توصية'}
            </button>
          </div>
        </div>

        {mut.isError && <ErrorState title="تعذّر الاتّصال بمحرّك التوصية" onRetry={submit} />}

        {/* Result — FarmerView */}
        {res && (
          <div className="space-y-4">
            <div className="rounded-xl border p-5" style={{ background: '#1a2b21', borderColor: `${gradeColor}44` }}>
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs px-2 py-0.5 rounded-full font-semibold" style={{ background: `${gradeColor}22`, color: gradeColor }}>
                  جودة: {grade}
                </span>
                <div className="flex items-center gap-3">
                  {asText(rec.status) && (
                    <span className="text-xs text-slate-400">الحالة: {asText(rec.status)}</span>
                  )}
                  {headline && <SpeakButton text={[headline, asText(rec.confidence), asText(rec.next_action_ar)].filter(Boolean).join('. ')} />}
                </div>
              </div>
              <div className="text-xl font-bold text-slate-100 mb-2 leading-relaxed">
                {headline || '—'}
              </div>
              {!res.delivered && res.reason_ar && (
                <p className="text-sm text-amber-300 mb-2">{res.reason_ar}</p>
              )}
              {asText(rec.confidence) && asText(rec.confidence) !== 'blocked' && (
                <div className="text-sm text-slate-300 bg-[#0d1611] rounded-lg px-3 py-2 mb-2">
                  📊 الثقة: {asText(rec.confidence)}
                </div>
              )}
              {/* حقول نصّيّة إرشاديّة إن توفّرت من المحرّك */}
              {['next_action_ar', 'action_ar', 'recommendation_ar', 'note_ar'].map(k =>
                asText(rec[k]) ? (
                  <p key={k} className="text-sm text-slate-300 mt-1">{asText(rec[k])}</p>
                ) : null
              )}
              <div className="mt-3 pt-3 border-t flex flex-wrap gap-4 text-xs text-slate-400" style={{ borderColor: '#2d4a37' }}>
                <span>الإنتاج المتوقّع: {predicted == null ? 'غير معايَر بعد (لا رقم وهمي)' : `${asText(predicted)} ط/هـ`}</span>
                {res.cross_reference_note_ar && <span>{res.cross_reference_note_ar}</span>}
              </div>
            </div>

            {/* BackendDetail toggle */}
            <button onClick={() => setShowBackend(s => !s)}
              className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200">
              {showBackend ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              {showBackend ? 'إخفاء التفاصيل التقنية' : 'عرض التفاصيل التقنية (للمهندس)'}
            </button>
            {showBackend && (
              <div className="rounded-xl border p-4 font-mono text-xs" style={{ background: '#0d1611', borderColor: '#334155' }}>
                <div className="text-emerald-400 mb-2">مخرجات المحرّك (rec_id: {res.rec_id ?? '—'})</div>
                {Object.entries(rec).map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-3 py-0.5 border-b last:border-0" style={{ borderColor: '#1e293b' }}>
                    <span className="text-slate-500">{k}</span>
                    <span className="text-slate-300 text-left break-all">{asText(v) || '—'}</span>
                  </div>
                ))}
                <div className="flex justify-between py-0.5 mt-1">
                  <span className="text-slate-500">model_versions</span>
                  <span className="text-slate-300">{res.model_versions_count ?? 0}</span>
                </div>
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
