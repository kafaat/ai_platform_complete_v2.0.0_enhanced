// ═══════════════════════════════════════════════════════════════
// SAHOOL — DecisionConfidencePage (ثقة القرار الموحَّدة) — قراءة فقط
// GET /api/v1/fields/{id}/decision-confidence: لحقلٍ مُختار، درجة ثقة موحَّدة مدموجة
// من أربعة مصادر (حسّاس + دليل ميدانيّ + استشعار + طقس)، كلٌّ بوزنه وقيمته وتوفّره،
// مع إعلان أيّ المصادر غائبة. عرض فقط — لا يُعدّل القرار.
//
// الصدق: confidence/level قد تكونان null/«insufficient» حين لا مصدر متاح ⇒ «غير
// كافية» (رماديّ) لا 0%. كلّ مكوّن يُعلِن available — غير المتوفّر رماديّ «يحتاج
// بيانات» باستخدام detail_ar، لا مساهم بصفر. الدرجة المدموجة محسوبة خادميّاً على
// المتوفّر فقط — هنا عرضٌ فقط. level→لون: high=أخضر، medium=كهرمانيّ، low=أحمر،
// insufficient=رماديّ.
//
// العلم مُطفأً (FEATURE_DECISION_CONFIDENCE) ⇒ 404 ⇒ «الميزة غير مُفعَّلة» (لا انهيار).
// 503 ⇒ القاعدة غير متاحة (ErrorState صادقة). لا حقل مُختار ⇒ مطالبة بالاختيار.
// (يطابق أنماط DeviceTwinPage/AgronomicTimelinePage بصريّاً ولونيّاً.)
// ═══════════════════════════════════════════════════════════════
import { Gauge, MapPin, AlertTriangle, ShieldAlert, Lock, Clock, CircleHelp } from 'lucide-react';
import { useDecisionConfidence } from '../hooks/useApi';
import { useSelectedField } from '../hooks/useSelectedField';
import { asApiError } from '../services/api';
import type {
  DecisionConfidenceLevel, DecisionConfidenceComponent, DecisionConfidenceResult,
} from '../services/api';
import { ErrorState, LoadingState, EmptyState } from '../components/StateViews';

// ربط مستوى الثقة (level) بألوان CSS محدّدة — لا فئات إضافيّة.
// insufficient ⇒ رماديّ محايد (يحتاج بيانات — لا حالة إيجابيّة مُختلَقة).
const LEVEL_HEX: Record<DecisionConfidenceLevel, string> = {
  high:         '#16a34a', // أخضر
  medium:       '#d97706', // كهرمانيّ
  low:          '#dc2626', // أحمر
  insufficient: '#9ca3af', // رماديّ (غير كافية — لا حالة إيجابيّة)
};
function levelHex(level: string): string {
  return LEVEL_HEX[level as DecisionConfidenceLevel] ?? LEVEL_HEX.insufficient;
}
// خلفيّة شارة خفيفة مشتقّة (تباين مقروء على سطح داكن).
const LEVEL_BG: Record<DecisionConfidenceLevel, string> = {
  high:         '#0c2a1a',
  medium:       '#2a1a00',
  low:          '#2a0d0d',
  insufficient: '#1e293b',
};
function levelBg(level: string): string {
  return LEVEL_BG[level as DecisionConfidenceLevel] ?? LEVEL_BG.insufficient;
}

// درجة 0..1 كنسبة مئويّة — null ⇒ «—» (لا تلفيق، لا 0).
function pctText(v: number | null): string {
  return v != null ? `${(v * 100).toFixed(0)}%` : '—';
}

// وزن 0..1 كنسبة مئويّة بأرقام عربيّة-إنجليزيّة موحَّدة (مثل «وزن ٣٠٪»).
function weightText(w: number): string {
  return `وزن ${(w * 100).toFixed(0)}٪`;
}

// شارة المستوى الملوّنة (level_ar) — لونها من level الخادم. null/insufficient ⇒ «غير كافية».
function LevelBadge({ data }: { data: DecisionConfidenceResult }) {
  const insufficient = data.confidence == null || data.level === 'insufficient';
  const hex = levelHex(data.level);
  return (
    <span
      className="text-[12px] px-2.5 py-0.5 rounded-full font-semibold whitespace-nowrap inline-flex items-center gap-1"
      style={{ background: levelBg(data.level), color: hex }}
    >
      {insufficient && <CircleHelp className="w-3 h-3" aria-hidden="true" />}
      {insufficient ? 'غير كافية' : data.level_ar}
    </span>
  );
}

// صفّ مكوّن واحد (sensor/evidence/satellite/weather): تسمية + شريط قيمة + وزن + تفصيل.
// available:false ⇒ رماديّ «غير متوفّر (needs_data)» (لا 0/مساهم).
function ComponentRow({ c }: { c: DecisionConfidenceComponent }) {
  const pct = c.value != null ? Math.max(0, Math.min(1, c.value)) * 100 : 0;
  // لون الشريط متدرّج بالقيمة (لا حكم قاطع): مرتفع أخضر، متوسّط كهرمانيّ، منخفض أحمر.
  const barHex = c.value == null ? '#475569' : c.value >= 0.8 ? '#16a34a' : c.value >= 0.5 ? '#d97706' : '#dc2626';
  return (
    <div
      className="rounded-xl border p-3 space-y-2"
      style={{
        background: c.available ? '#1e293b' : '#161b22',
        borderColor: c.available ? '#334155' : '#25303f',
      }}
    >
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-semibold" style={{ color: c.available ? '#e2e8f0' : '#94a3b8' }}>
            {c.label_ar}
          </span>
          <span
            className="text-[10px] px-1.5 py-0.5 rounded-full"
            style={{ background: '#0d1117', color: '#94a3b8', border: '1px solid #334155' }}
          >
            {weightText(c.weight)}
          </span>
        </div>
        {c.available ? (
          <span className="text-sm font-bold tabular-nums" style={{ color: barHex }}>
            {pctText(c.value)}
          </span>
        ) : (
          <span className="text-[11px] px-2 py-0.5 rounded-full font-semibold inline-flex items-center gap-1"
            style={{ background: '#1e293b', color: '#9ca3af' }}>
            <CircleHelp className="w-3 h-3" aria-hidden="true" /> غير متوفّر (needs_data)
          </span>
        )}
      </div>

      {/* شريط القيمة — متوفّر: ملوّن بالقيمة؛ غير متوفّر: «—» رماديّ (لا 0 مساهم) */}
      {c.available ? (
        <div className="h-1.5 rounded-full overflow-hidden" style={{ background: '#0d1117' }}>
          <div className="h-full rounded-full" style={{ width: `${pct}%`, background: barHex }} />
        </div>
      ) : (
        <div className="text-[12px] text-slate-500">—</div>
      )}

      {/* تفصيل المصدر (detail_ar) — يُعرَض في الحالتين (صدق: سبب الغياب مُعلَن) */}
      <div className="text-[11px]" style={{ color: c.available ? '#94a3b8' : '#64748b' }}>
        {c.detail_ar}
      </div>
    </div>
  );
}

export default function DecisionConfidencePage() {
  const { options, fieldId, setFieldId, isLoading: fieldsLoading, isError: fieldsError } = useSelectedField();
  const query = useDecisionConfidence(fieldId);
  const data: DecisionConfidenceResult | undefined = query.data;

  // كشف 404 (العلم مُطفأ) عبر شكل خطأ أكسيوس الموحّد — رسالة ودودة لا حالة خطأ.
  const featureOff = query.isError && asApiError(query.error).response?.status === 404;

  const insufficient = !!data && (data.confidence == null || data.level === 'insufficient');
  const confHex = data ? (insufficient ? '#9ca3af' : levelHex(data.level)) : '#9ca3af';

  return (
    <div className="space-y-6 max-w-4xl mx-auto" dir="rtl">
      {/* ── الترويسة ── */}
      <div className="flex items-center gap-2">
        <Gauge className="w-5 h-5 text-emerald-400" aria-hidden="true" />
        <h2 className="text-xl font-bold text-slate-100">ثقة القرار الموحَّدة</h2>
      </div>
      <p className="text-sm text-slate-400">
        درجة ثقة موحَّدة لقرار الحقل، مدموجة بوزنٍ شفّاف من <span className="text-emerald-300">أربعة
        مصادر</span> (الحسّاس + الدليل الميدانيّ + الاستشعار + الطقس) — على المصادر المتوفّرة فقط.
        صدق: المصادر الغائبة مُعلَنة «يحتاج بيانات» (رماديّ) لا تُحتسَب صفراً، والثقة غير الكافية تُعرَض
        «غير كافية». عرض فقط — لا يُعدّل القرار.
      </p>

      {/* ── اختيار الحقل ── */}
      <div className="rounded-xl border p-4" style={{ background: '#1e293b', borderColor: '#334155' }}>
        <label className="flex flex-col gap-1 max-w-xs">
          <span className="text-xs text-slate-400 flex items-center gap-1">
            <MapPin className="w-3.5 h-3.5 text-emerald-400" /> الحقل
          </span>
          {fieldsLoading ? (
            <span className="text-[12px] text-slate-500">جارٍ جلب الحقول…</span>
          ) : fieldsError ? (
            <span className="text-[12px] text-amber-300/80">تعذّر جلب قائمة الحقول.</span>
          ) : (
            <select value={fieldId} onChange={e => setFieldId(e.target.value)}
              className="px-3 py-2 rounded-lg text-sm"
              style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}>
              <option value="">— اختر حقلاً —</option>
              {options.map(o => <option key={o.id} value={o.id}>{o.name || o.id}</option>)}
            </select>
          )}
        </label>
      </div>

      {/* ── لا حقل مُختار ── */}
      {!fieldId && (
        <EmptyState
          icon={<Gauge className="w-8 h-8" />}
          title="اختر حقلاً لعرض ثقة قراره"
          hint="تُدمَج الثقة من الحسّاس والدليل والاستشعار والطقس — على المصادر المتوفّرة لهذا الحقل فقط." />
      )}

      {/* ── الحالات ── */}
      {fieldId && query.isLoading && <LoadingState message="جارٍ جلب ثقة القرار…" />}

      {/* الميزة غير مُفعَّلة (404 — العلم مُطفأ) */}
      {fieldId && featureOff && (
        <div
          className="rounded-xl border p-4 flex items-start gap-3"
          style={{ background: '#1e293b', borderColor: '#334155' }}
          role="status"
        >
          <ShieldAlert className="w-5 h-5 text-slate-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
          <div className="space-y-1">
            <div className="text-sm font-semibold text-slate-200">الميزة غير مُفعَّلة (FEATURE_DECISION_CONFIDENCE)</div>
            <div className="text-[12px] text-slate-400">
              ثقة القرار الموحَّدة خلف علم تشغيل (FEATURE_DECISION_CONFIDENCE) لم يُفعَّل بعد على الخادم. تواصل مع المسؤول لتفعيله.
            </div>
          </div>
        </div>
      )}

      {/* 503/أيّ خطأ آخر — حالة خطأ صادقة */}
      {fieldId && query.isError && !featureOff && (
        <ErrorState
          title="تعذّر جلب ثقة القرار"
          detail="قد تكون قاعدة البيانات غير متاحة (503) أو الحقل ليس لمستأجِرك (404)."
          onRetry={() => query.refetch()}
        />
      )}

      {data && (
        <div className="space-y-6">
          {/* ── مقياس الثقة المدموجة (الرأس) ── */}
          <section
            className="rounded-xl border p-4 flex items-end gap-6 flex-wrap"
            style={{ background: '#10151f', borderColor: '#25303f' }}
          >
            <div>
              <div className="text-4xl font-extrabold leading-none" style={{ color: confHex }}>
                {insufficient ? 'غير كافية' : pctText(data.confidence)}
              </div>
              <div className="mt-2"><LevelBadge data={data} /></div>
            </div>
            <div>
              <div className="text-2xl font-bold text-slate-100 leading-none">
                {data.present_count}/{data.components.length}
              </div>
              <div className="text-[11px] text-slate-400 mt-1">مصادر مُستخدَمة</div>
            </div>
            <div className="text-[11px] text-slate-500 mr-auto self-center inline-flex items-center gap-1">
              <Clock className="w-3 h-3" aria-hidden="true" />
              آخر تحديث: <span className="text-slate-400">{data.generated_at}</span>
            </div>
          </section>

          {/* ── تفصيل المكوّنات (صفّ لكلّ مصدر) ── */}
          <section className="space-y-2">
            <div className="text-[12px] font-semibold text-slate-300">تفصيل المصادر</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {data.components.map((c) => (
                <ComponentRow key={c.source} c={c} />
              ))}
            </div>
            {/* المصادر الغائبة المُعلَنة (missing) — رقائق خافتة */}
            {data.missing.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 pt-1">
                <span className="text-[11px] text-slate-500">غائب:</span>
                {data.missing.map((m) => (
                  <span
                    key={m}
                    className="text-[10px] px-1.5 py-0.5 rounded-full"
                    style={{ background: '#0d1117', color: '#94a3b8', border: '1px dashed #475569' }}
                  >
                    {m}
                  </span>
                ))}
              </div>
            )}
          </section>

          {/* ── بانر الصدق/المصدر (provenance) — كهرمانيّ ── */}
          <div
            className="rounded-xl border p-4 flex items-start gap-3"
            style={{ background: '#1a1400', borderColor: '#f59e0b33' }}
          >
            <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
            <div className="space-y-1">
              <div className="text-sm font-semibold text-amber-200">
                🟡 ثقة القرار تركيبة موزونة شفّافة على المصادر المتوفّرة فقط — الغائبة مُعلَنة لا مُفترَضة
              </div>
              <div className="text-[12px] text-amber-300/80">{data.provenance.note_ar}</div>
            </div>
          </div>

          {/* ── ملاحظة قراءة فقط (لا تعديل) ── */}
          <div className="flex items-center gap-2 text-[12px] text-slate-500">
            <Lock className="w-3.5 h-3.5" aria-hidden="true" />
            عرض فقط — لا يُعدّل القرار.
          </div>
        </div>
      )}
    </div>
  );
}
