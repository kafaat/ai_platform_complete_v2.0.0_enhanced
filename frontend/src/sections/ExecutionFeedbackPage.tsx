// ═══════════════════════════════════════════════════════════════
// SAHOOL — ExecutionFeedbackPage (رصد حلقة التنفيذ) — GET /api/v1/execution/feedback
// قراءة فقط: لكلّ قرار حديث هل نُفِّذ (من سجلّ التنفيذ) وهل طابقت النتيجة الخطّة —
// إغلاق حلقة القرار→التنفيذ→النتيجة. لا إصدار أوامر ولا إعادة تنفيذ.
//
// الصدق: loop_status من سجلّات مُدامة فقط. execution_unknown «يحتاج بيانات» (رماديّ)
// لا يُعرَض «نُفِّذ» ولا حالة إيجابيّة خضراء. executed_unmeasured كهرمانيّ — نُفِّذ لكن
// لم تُقَس النتيجة بعد (ليس نجاحاً). closure_rate قد تكون null ⇒ «غير محسوبة» لا 0%.
// outcome_success=null حين لا تُقاس ⇒ «—» لا ✗.
//
// العلم مُطفأً (FEATURE_EXECUTION_FEEDBACK) ⇒ 404 ⇒ «الميزة غير مُفعَّلة» (لا انهيار).
// 503 ⇒ القاعدة غير متاحة (ErrorState صادقة). decisions:[] ⇒ «لا قرارات مُدامة بعد».
// ═══════════════════════════════════════════════════════════════
import { Repeat, AlertTriangle, ShieldAlert, Lock, CircleHelp, CheckCircle2, XCircle, Clock } from 'lucide-react';
import { useExecutionFeedback } from '../hooks/useApi';
import { asApiError } from '../services/api';
import type {
  ExecutionFeedbackDecision, ExecutionFeedbackResult, ExecutionLoopStatus,
} from '../services/api';
import { ErrorState, LoadingState } from '../components/StateViews';

// ربط لون الخادم (green|red|amber|gray) بألوان CSS محدّدة في الواجهة.
// لون مجهول ⇒ رماديّ محايد (fail-safe، لا حالة إيجابيّة مُختلَقة).
const COLOR_HEX: Record<string, string> = {
  green: '#16a34a', // مغلقة ونجحت
  red:   '#dc2626', // خارج الخطّة / فشل تنفيذ
  amber: '#d97706', // نُفِّذ بلا قياس
  gray:  '#9ca3af', // مجهولة — يحتاج بيانات
};
function colorHex(color: string): string {
  return COLOR_HEX[color] ?? COLOR_HEX.gray;
}
// خلفيّة شارة خفيفة مشتقّة (تباين مقروء على سطح داكن).
const COLOR_BG: Record<string, string> = {
  green: '#0c2a1a',
  red:   '#2a0d0d',
  amber: '#2a1a00',
  gray:  '#1e293b',
};
function colorBg(color: string): string {
  return COLOR_BG[color] ?? COLOR_BG.gray;
}

// ترتيب حالات الحلقة الثابت من العقد + تسمياتها العربيّة وألوانها (للأسطورة/الرقائق).
const STATUS_ORDER: ExecutionLoopStatus[] = [
  'closed_ok', 'executed_off_plan', 'executed_unmeasured', 'execution_failed', 'execution_unknown',
];
const STATUS_LABEL_AR: Record<ExecutionLoopStatus, string> = {
  closed_ok:           'حلقة مغلقة (نُفِّذ ونجح)',
  executed_off_plan:   'نُفِّذ خارج الخطّة',
  executed_unmeasured: 'نُفِّذ بلا قياس',
  execution_failed:    'فشل التنفيذ',
  execution_unknown:   'يحتاج بيانات (غير مُسجَّل)',
};
const STATUS_COLOR: Record<ExecutionLoopStatus, string> = {
  closed_ok:           'green',
  executed_off_plan:   'red',
  executed_unmeasured: 'amber',
  execution_failed:    'red',
  execution_unknown:   'gray',
};

// closure_rate 0..1 كنسبة مئويّة — null ⇒ «غير محسوبة» (لا 0%، لا تلفيق).
function closureText(rate: number | null): string {
  return rate != null ? `${(rate * 100).toFixed(0)}%` : 'غير محسوبة';
}

// تاريخ ISO قصير (YYYY-MM-DD) — null ⇒ «—» (لا افتراض).
function shortDate(iso: string | null): string {
  if (!iso) return '—';
  const i = iso.indexOf('T');
  return i > 0 ? iso.slice(0, i) : iso;
}

// شارة حالة الحلقة الملوّنة (loop_status_ar) — لونها من color الخادم.
function LoopBadge({ decision }: { decision: ExecutionFeedbackDecision }) {
  const hex = colorHex(decision.color);
  const isUnknown = decision.loop_status === 'execution_unknown';
  return (
    <span
      className="text-[11px] px-2 py-0.5 rounded-full font-semibold whitespace-nowrap inline-flex items-center gap-1"
      style={{ background: colorBg(decision.color), color: hex }}
    >
      {isUnknown && <CircleHelp className="w-3 h-3" aria-hidden="true" />}
      {decision.loop_status_ar}
    </span>
  );
}

// رقاقة عدّ حالة (للأسطورة في الترويسة) — لونها من حالة الحلقة.
function ByStatusChip({ status, count }: { status: ExecutionLoopStatus; count: number }) {
  const color = STATUS_COLOR[status];
  const hex = colorHex(color);
  return (
    <div
      className="flex items-center gap-2 rounded-lg px-3 py-1.5 border"
      style={{ background: '#1e293b', borderColor: '#334155' }}
    >
      <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: hex }} aria-hidden="true" />
      <span className="text-[12px] text-slate-200">{STATUS_LABEL_AR[status]}</span>
      <span
        className="text-[12px] font-bold px-1.5 rounded-full"
        style={{ background: colorBg(color), color: hex }}
      >
        {count}
      </span>
    </div>
  );
}

// خليّة execution_outcome: executed/failed/«غير مُسجَّل» حين null (لا افتراض تنفيذ).
function outcomeText(outcome: 'executed' | 'failed' | null): string {
  if (outcome === 'executed') return 'نُفِّذ';
  if (outcome === 'failed') return 'فشل';
  return 'غير مُسجَّل';
}

// خليّة outcome_success: ✓ / ✗ / «—» (null حين لا تُقاس — لا ✗ مُختلَق).
function SuccessCell({ value }: { value: boolean | null }) {
  if (value === true) {
    return (
      <span className="inline-flex items-center gap-1 text-emerald-400" title="نجحت النتيجة">
        <CheckCircle2 className="w-4 h-4" aria-hidden="true" />
      </span>
    );
  }
  if (value === false) {
    return (
      <span className="inline-flex items-center gap-1 text-red-400" title="لم تنجح النتيجة">
        <XCircle className="w-4 h-4" aria-hidden="true" />
      </span>
    );
  }
  return <span className="text-slate-500" title="لم تُقَس النتيجة">—</span>;
}

// بطاقة إجماليّة صغيرة (مقياس + تسمية).
function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-2xl font-bold text-slate-100 leading-none">{value}</div>
      <div className="text-[11px] text-slate-400 mt-1">{label}</div>
    </div>
  );
}

// صفّ قرار واحد. صفوف execution_unknown/executed_unmeasured مميّزة بصريّاً (حدّ
// جانبيّ ملوّن + ملاحظة note_ar) لإبراز الفجوة الصادقة (رماديّ/كهرمانيّ) لا نجاحاً.
function DecisionRow({ decision }: { decision: ExecutionFeedbackDecision }) {
  const hex = colorHex(decision.color);
  // الملاحظة الصادقة: exec_note_ar من سجلّ التنفيذ أو note_ar (تفسير الحالة المجهولة/غير المقيسة).
  const note = decision.exec_note_ar || decision.note_ar;
  return (
    <tr className="border-t text-slate-200 align-top" style={{ borderColor: '#25303f' }}>
      <td className="px-3 py-2" style={{ borderRight: `3px solid ${hex}` }}>
        <div className="font-medium">{decision.decision_type}</div>
        <div className="text-[11px] text-slate-400">{decision.decision_id}</div>
        {note && <div className="text-[11px] text-slate-500 mt-1 max-w-xs">{note}</div>}
      </td>
      <td className="px-3 py-2 text-slate-300">{decision.field_id ?? '—'}</td>
      <td className="px-3 py-2 text-slate-300 whitespace-nowrap">{shortDate(decision.created_at)}</td>
      <td className="px-3 py-2"><LoopBadge decision={decision} /></td>
      <td className="px-3 py-2 text-slate-300">{outcomeText(decision.execution_outcome)}</td>
      <td className="px-3 py-2 text-slate-300 whitespace-nowrap">
        <span className="inline-flex items-center gap-1">
          <Clock className="w-3 h-3 text-slate-500" aria-hidden="true" />
          {shortDate(decision.executed_at)}
        </span>
      </td>
      <td className="px-3 py-2"><SuccessCell value={decision.outcome_success} /></td>
    </tr>
  );
}

export default function ExecutionFeedbackPage() {
  const query = useExecutionFeedback();
  const data: ExecutionFeedbackResult | undefined = query.data;

  // كشف 404 (العلم مُطفأ) عبر شكل خطأ أكسيوس الموحّد — رسالة ودودة لا حالة خطأ.
  const featureOff = query.isError && asApiError(query.error).response?.status === 404;

  return (
    <div className="space-y-6 max-w-6xl mx-auto" dir="rtl">
      {/* ── الترويسة ── */}
      <div className="flex items-center gap-2">
        <Repeat className="w-5 h-5 text-emerald-400" aria-hidden="true" />
        <h2 className="text-xl font-bold text-slate-100">رصد حلقة التنفيذ</h2>
      </div>
      <p className="text-sm text-slate-400">
        لكلّ قرار حديث: هل <span className="text-emerald-300">نُفِّذ</span> فعلاً (من سجلّ التنفيذ) وهل
        <span className="text-emerald-300"> طابقت النتيجة الخطّة</span> — إغلاق حلقة القرار→التنفيذ→النتيجة.
        صدق: غير المُسجَّل <span className="text-slate-300">«يحتاج بيانات»</span> لا يُفترَض مُنفَّذاً، والمنفَّذ بلا قياس
        <span className="text-amber-300"> ليس نجاحاً</span>.
      </p>

      {/* ── الحالات ── */}
      {query.isLoading && <LoadingState message="جارٍ جلب رصد حلقة التنفيذ…" />}

      {/* الميزة غير مُفعَّلة (404 — العلم مُطفأ) */}
      {featureOff && (
        <div
          className="rounded-xl border p-4 flex items-start gap-3"
          style={{ background: '#1e293b', borderColor: '#334155' }}
          role="status"
        >
          <ShieldAlert className="w-5 h-5 text-slate-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
          <div className="space-y-1">
            <div className="text-sm font-semibold text-slate-200">الميزة غير مُفعَّلة (FEATURE_EXECUTION_FEEDBACK)</div>
            <div className="text-[12px] text-slate-400">
              رصد حلقة التنفيذ خلف علم تشغيل (FEATURE_EXECUTION_FEEDBACK) لم يُفعَّل بعد على الخادم. تواصل مع المسؤول لتفعيله.
            </div>
          </div>
        </div>
      )}

      {/* 503/أيّ خطأ آخر — حالة خطأ صادقة */}
      {query.isError && !featureOff && (
        <ErrorState
          title="تعذّر جلب رصد حلقة التنفيذ"
          detail="قد تكون قاعدة البيانات غير متاحة (503) أو حدث انقطاع."
          onRetry={() => query.refetch()}
        />
      )}

      {/* decisions:[] — لا قرارات مُدامة بعد */}
      {data && data.decisions.length === 0 && (
        <div
          className="rounded-xl border p-4 text-sm text-slate-400"
          style={{ background: '#1e293b', borderColor: '#334155' }}
          role="status"
        >
          لا قرارات مُدامة بعد — لا تتوفّر بيانات لرصد حلقة التنفيذ.
        </div>
      )}

      {data && data.decisions.length > 0 && (
        <div className="space-y-6">
          {/* ── ترويسة التلخيص: نسبة إغلاق الحلقة + الإجماليّات + رقائق الحالات ── */}
          <section
            className="rounded-xl border p-4 space-y-3"
            style={{ background: '#10151f', borderColor: '#25303f' }}
          >
            <div className="flex items-end gap-6 flex-wrap">
              <div>
                <div
                  className="text-4xl font-extrabold leading-none"
                  style={{ color: data.closure_rate != null ? '#34d399' : '#9ca3af' }}
                >
                  {closureText(data.closure_rate)}
                </div>
                <div className="text-[11px] text-slate-400 mt-1">نسبة إغلاق الحلقة</div>
              </div>
              <MiniStat label="إجماليّ القرارات" value={String(data.decision_count)} />
              <MiniStat label="نُفِّذ" value={String(data.totals.executed)} />
              <MiniStat label="فشل التنفيذ" value={String(data.totals.failed)} />
              <MiniStat label="نتائج مقيسة" value={String(data.totals.measured)} />
              <MiniStat label="حلقات مغلقة" value={String(data.totals.closed_ok)} />
              <div className="text-[11px] text-slate-500 mr-auto self-center">
                آخر تحديث: <span className="text-slate-400">{data.generated_at}</span>
              </div>
            </div>

            {/* رقائق عدّ حالات الحلقة (by_status) ملوّنة */}
            <div className="flex flex-wrap gap-2">
              {STATUS_ORDER.map((st) => (
                <ByStatusChip key={st} status={st} count={data.by_status?.[st] ?? 0} />
              ))}
            </div>
          </section>

          {/* ── بانر الصدق/المصدر (provenance) — كهرمانيّ ── */}
          <div
            className="rounded-xl border p-4 flex items-start gap-3"
            style={{ background: '#1a1400', borderColor: '#f59e0b33' }}
          >
            <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
            <div className="space-y-1">
              <div className="text-sm font-semibold text-amber-200">
                🟡 حالات الحلقة من سجلّات مُدامة فقط — غير المُسجَّل لا يُفترَض مُنفَّذاً، والمنفَّذ بلا قياس ليس نجاحاً
              </div>
              <div className="text-[12px] text-amber-300/80">{data.provenance.note_ar}</div>
            </div>
          </div>

          {/* ── ملاحظة قراءة فقط (لا أوامر) ── */}
          <div className="flex items-center gap-2 text-[12px] text-slate-500">
            <Lock className="w-3.5 h-3.5" aria-hidden="true" />
            رصد قراءة فقط — لا إصدار أوامر ولا إعادة تنفيذ من هذه الصفحة.
          </div>

          {/* ── جدول القرارات ── */}
          <section className="space-y-2">
            <div className="text-sm font-semibold text-slate-200">
              القرارات الحديثة ({data.decision_count})
            </div>
            <div className="overflow-x-auto rounded-xl border" style={{ borderColor: '#334155' }}>
              <table className="w-full text-sm" style={{ background: '#1e293b' }}>
                <thead>
                  <tr className="text-[11px] text-slate-400 text-right">
                    <th className="px-3 py-2 font-medium">القرار</th>
                    <th className="px-3 py-2 font-medium">الحقل</th>
                    <th className="px-3 py-2 font-medium">تاريخ القرار</th>
                    <th className="px-3 py-2 font-medium">حالة الحلقة</th>
                    <th className="px-3 py-2 font-medium">التنفيذ</th>
                    <th className="px-3 py-2 font-medium">وقت التنفيذ</th>
                    <th className="px-3 py-2 font-medium">نجاح النتيجة</th>
                  </tr>
                </thead>
                <tbody>
                  {data.decisions.map((d) => (
                    <DecisionRow key={d.decision_id} decision={d} />
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
