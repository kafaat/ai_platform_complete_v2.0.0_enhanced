// ═══════════════════════════════════════════════════════════════
// SAHOOL — LineagePage (يستهلك GET /api/v1/decision/{id}/lineage
// و GET /api/v1/calibration/{region}/evidence/persisted)
// قراءة فقط: يُظهر سلسلة النَّسَب المُدامة (قرار → نتائجه التالية)، والدليل
// الميدانيّ المتراكم لكلّ منطقة وتقدّمه نحو التحقّق. صدق: الدليل المتراكم
// تقديريّ غير مُعايَر (calibrated=false, source=persisted_outcomes) حتى تُجمَع
// عيّنات كافية — تُعرَض warnings_ar صراحةً بلا أرقام قاطعة مُلفَّقة.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import {
  GitBranch, Workflow, Search, CheckCircle2, XCircle, HelpCircle,
  AlertTriangle, FlaskConical,
} from 'lucide-react';
import { useDecisionLineage, usePersistedEvidence } from '../hooks/useApi';
import type { LineageOutcome } from '../services/api';
import { ErrorState, LoadingState } from '../components/StateViews';

// المناطق المدعومة (يطابق نصّ المهمّة).
const REGIONS: { id: string; ar: string }[] = [
  { id: 'jawf',      ar: 'الجوف' },
  { id: 'tihama',    ar: 'تهامة' },
  { id: 'marib',     ar: 'مأرب' },
  { id: 'hadramout', ar: 'حضرموت' },
  { id: 'ibb',       ar: 'إبّ' },
  { id: 'generic',   ar: 'عامّ' },
];

// شارة مستوى الدليل — نفس ألوان CalibrationPage (تناسق بصريّ).
const EVIDENCE_AR: Record<string, string> = {
  field_verified:    'مُتحقَّق ميدانيّاً',
  field_preliminary: 'ميدانيّ أوّليّ',
  expert_opinion:    'رأي خبير',
  none:              'لا دليل',
};
const evidenceStyle = (level: string): { bg: string; color: string } => {
  switch (level) {
    case 'field_verified':    return { bg: '#0c2a1a', color: '#4ade80' };
    case 'field_preliminary': return { bg: '#2a1a00', color: '#fbbf24' };
    case 'expert_opinion':    return { bg: '#0a1f2e', color: '#38bdf8' };
    case 'none':              return { bg: '#2a0d0d', color: '#f87171' };
    default:                  return { bg: '#1e293b', color: '#94a3b8' };
  }
};

// نسّق قيمة مُلخَّصة لعرضها في شبكة المقاييس (أرقام بخانتين، غير ذلك كنصّ).
function fmtValue(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(2);
  if (typeof v === 'boolean') return v ? 'نعم' : 'لا';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

// شبكة مقاييس مُلخّصة (أبرز metrics لكلّ نتيجة).
function MetricsGrid({ metrics }: { metrics: Record<string, unknown> }) {
  const entries = Object.entries(metrics).slice(0, 6);
  if (entries.length === 0) {
    return <div className="text-[11px] text-slate-500">لا مقاييس مُسجَّلة لهذه النتيجة.</div>;
  }
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
      {entries.map(([k, v]) => (
        <div key={k} className="rounded-lg px-2 py-1.5" style={{ background: '#0f1117', border: '1px solid #25303f' }}>
          <div className="text-[10px] text-slate-500 truncate">{k}</div>
          <div className="text-sm font-semibold text-slate-200 truncate">{fmtValue(v)}</div>
        </div>
      ))}
    </div>
  );
}

// بطاقة نتيجة واحدة (outcome) — success كشارة ✓/✗/«يحتاج بيانات».
function OutcomeCard({ o }: { o: LineageOutcome }) {
  const success =
    o.success === true
      ? { ar: 'ناجحة', icon: <CheckCircle2 className="w-4 h-4" />, bg: '#0c2a1a', color: '#4ade80' }
      : o.success === false
        ? { ar: 'غير ناجحة', icon: <XCircle className="w-4 h-4" />, bg: '#2a0d0d', color: '#f87171' }
        : { ar: 'يحتاج بيانات', icon: <HelpCircle className="w-4 h-4" />, bg: '#1e293b', color: '#94a3b8' };
  return (
    <div className="rounded-xl border p-3 space-y-2" style={{ background: '#1e293b', borderColor: '#334155' }}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <span className="text-slate-300 font-medium">{o.stage || '—'}</span>
          {o.created_at && <span className="text-slate-600">· {o.created_at}</span>}
        </div>
        <span className="text-[11px] px-2 py-0.5 rounded-full font-semibold flex items-center gap-1"
          style={{ background: success.bg, color: success.color }}>
          {success.icon}{success.ar}
        </span>
      </div>
      <MetricsGrid metrics={o.metrics} />
    </div>
  );
}

export default function LineagePage() {
  // ── سلسلة القرار ──
  const [decisionInput, setDecisionInput] = useState('');
  const [decisionId, setDecisionId] = useState('');
  const lineage = useDecisionLineage(decisionId);

  const submitDecision = (e: React.FormEvent) => {
    e.preventDefault();
    setDecisionId(decisionInput.trim());
  };

  // ── دليل منطقة متراكم ──
  const [region, setRegion] = useState('');
  const evidence = usePersistedEvidence(region);

  const dec = lineage.data?.decision ?? null;
  const ev = evidence.data;
  const evStyle = ev ? evidenceStyle(ev.evidence_level) : null;
  // تقدّم العيّنات نحو التحقّق (sample_count / field_verified_min_samples).
  const progressPct = ev && ev.field_verified_min_samples > 0
    ? Math.min(100, Math.round((ev.sample_count / ev.field_verified_min_samples) * 100))
    : 0;

  return (
    <div className="space-y-6 max-w-4xl mx-auto" dir="rtl">
      <div className="flex items-center gap-2">
        <GitBranch className="w-5 h-5 text-emerald-400" />
        <h2 className="text-xl font-bold text-slate-100">سلسلة النَّسَب والدليل المتراكم</h2>
      </div>
      <p className="text-sm text-slate-400">
        أثرٌ صادق للقرارات المُدامة ونتائجها التالية، وتراكم الدليل الميدانيّ لكلّ منطقة نحو التحقّق.
        لا أرقام قاطعة مُلفَّقة: الدليل المتراكم <span className="text-amber-300">تقديريّ غير مُعايَر</span> حتى تُجمَع عيّنات كافية.
      </p>

      {/* ═══════════ القسم الأوّل: سلسلة قرار ═══════════ */}
      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <Workflow className="w-4 h-4 text-emerald-400" />
          <h3 className="text-base font-bold text-slate-100">سلسلة قرار</h3>
        </div>

        <form onSubmit={submitDecision}
          className="rounded-xl border p-4 flex flex-col sm:flex-row gap-3 sm:items-end"
          style={{ background: '#1e293b', borderColor: '#334155' }}>
          <label className="flex flex-col gap-1 flex-1">
            <span className="text-xs text-slate-400">معرّف القرار (decision_id)</span>
            <input value={decisionInput} onChange={e => setDecisionInput(e.target.value)}
              placeholder="dec_..." dir="ltr"
              className="px-3 py-2 rounded-lg text-sm"
              style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
          </label>
          <button type="submit" disabled={!decisionInput.trim() || lineage.isFetching}
            className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-60"
            style={{ background: '#16a34a' }}>
            <Search className="w-4 h-4" />
            {lineage.isFetching ? 'جارٍ الجلب…' : 'جلب السلسلة'}
          </button>
        </form>

        {decisionId && lineage.isLoading && <LoadingState message="جارٍ جلب سلسلة القرار…" />}
        {decisionId && lineage.isError && (
          <ErrorState title="تعذّر جلب سلسلة القرار"
            detail="قد يكون المعرّف غير موجود أو القرار غير مُدام."
            onRetry={() => lineage.refetch()} />
        )}

        {lineage.data && (
          <div className="space-y-4">
            {/* بطاقة القرار */}
            {dec ? (
              <div className="rounded-xl border p-4 space-y-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <GitBranch className="w-4 h-4 text-emerald-400" />
                    <span className="text-sm font-semibold text-slate-100">{dec.decision_type}</span>
                  </div>
                  {dec.confidence != null && (
                    <span className="text-[11px] px-2 py-0.5 rounded-full font-semibold"
                      style={{ background: '#0a1f2e', color: '#38bdf8' }}>
                      الثقة {(dec.confidence * 100).toFixed(0)}%
                    </span>
                  )}
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm">
                  <div className="rounded-lg px-2 py-1.5" style={{ background: '#0f1117' }}>
                    <div className="text-[10px] text-slate-500">الحقل</div>
                    <div className="text-slate-200 font-medium truncate">{dec.field_id || '—'}</div>
                  </div>
                  <div className="rounded-lg px-2 py-1.5" style={{ background: '#0f1117' }}>
                    <div className="text-[10px] text-slate-500">المنطقة</div>
                    <div className="text-slate-200 font-medium truncate">{dec.region || '—'}</div>
                  </div>
                  <div className="rounded-lg px-2 py-1.5" style={{ background: '#0f1117' }}>
                    <div className="text-[10px] text-slate-500">المرحلة</div>
                    <div className="text-slate-200 font-medium truncate">{dec.stage || '—'}</div>
                  </div>
                  <div className="rounded-lg px-2 py-1.5" style={{ background: '#0f1117' }}>
                    <div className="text-[10px] text-slate-500">الوقت</div>
                    <div className="text-slate-200 font-medium truncate">{dec.created_at || '—'}</div>
                  </div>
                </div>
                <MetricsGrid metrics={dec.decision_value} />
              </div>
            ) : (
              <div className="rounded-xl border p-4 flex items-start gap-3" style={{ background: '#1a1400', borderColor: '#f59e0b33' }}>
                <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
                <div className="text-sm text-amber-200">
                  القرار غير مُدام (قد يكون حُسِب عبر المسار النقيّ).
                </div>
              </div>
            )}

            {/* شريط المراحل present (decision → outcome…) */}
            {lineage.data.stages_present.length > 0 && (
              <div className="rounded-xl border p-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
                <div className="text-[11px] text-slate-400 mb-2">سلسلة المراحل ({lineage.data.outcome_count} نتيجة)</div>
                <div className="flex flex-wrap items-center gap-1.5">
                  {lineage.data.stages_present.map((s, i) => (
                    <span key={`${s}-${i}`} className="flex items-center gap-1.5">
                      {i > 0 && <span className="text-slate-600 text-xs">←</span>}
                      <span className="text-[11px] px-2 py-0.5 rounded-full font-medium"
                        style={{ background: '#16a34a18', color: '#4ade80' }}>{s}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* النتائج */}
            <div className="space-y-2">
              <div className="text-sm font-semibold text-slate-200">النتائج المتراكمة</div>
              {lineage.data.outcomes.length === 0 ? (
                <div className="rounded-xl border p-3 text-sm text-slate-400" style={{ background: '#1e293b', borderColor: '#334155' }}>
                  لا نتائج مُسجَّلة بعد لهذا القرار.
                </div>
              ) : (
                <div className="space-y-2">
                  {lineage.data.outcomes.map(o => <OutcomeCard key={o.outcome_id} o={o} />)}
                </div>
              )}
            </div>
          </div>
        )}
      </section>

      {/* ═══════════ القسم الثاني: دليل منطقة متراكم ═══════════ */}
      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <FlaskConical className="w-4 h-4 text-emerald-400" />
          <h3 className="text-base font-bold text-slate-100">دليل منطقة متراكم</h3>
        </div>

        <div className="rounded-xl border p-4" style={{ background: '#1e293b', borderColor: '#334155' }}>
          <label className="flex flex-col gap-1 max-w-xs">
            <span className="text-xs text-slate-400">المنطقة</span>
            <select value={region} onChange={e => setRegion(e.target.value)}
              className="px-3 py-2 rounded-lg text-sm"
              style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}>
              <option value="">— اختر منطقة —</option>
              {REGIONS.map(r => <option key={r.id} value={r.id}>{r.ar}</option>)}
            </select>
          </label>
        </div>

        {region && evidence.isLoading && <LoadingState message="جارٍ جلب الدليل المتراكم…" />}
        {region && evidence.isError && (
          <ErrorState title="تعذّر جلب الدليل المتراكم" onRetry={() => evidence.refetch()} />
        )}

        {ev && evStyle && (
          <div className="space-y-4">
            {/* تقدّم نحو التحقّق + شارة + معدّل النجاح */}
            <div className="rounded-xl border p-4 space-y-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] px-2 py-0.5 rounded-full font-semibold"
                  style={{ background: evStyle.bg, color: evStyle.color }}>
                  {EVIDENCE_AR[ev.evidence_level] ?? ev.evidence_level}
                </span>
                <span className="text-sm text-slate-300">
                  معدّل النجاح: <span className="font-bold text-slate-100">
                    {ev.success_rate != null ? `${(ev.success_rate * 100).toFixed(0)}%` : '—'}
                  </span>
                </span>
              </div>

              {/* شريط تقدّم العيّنات نحو التحقّق */}
              <div className="space-y-1">
                <div className="flex items-center justify-between text-[11px] text-slate-400">
                  <span>التقدّم نحو التحقّق الميدانيّ</span>
                  <span className="text-slate-300 font-medium">
                    {ev.sample_count} / {ev.field_verified_min_samples} عيّنة
                  </span>
                </div>
                <div className="h-2.5 rounded-full overflow-hidden" style={{ background: '#0f1117' }}>
                  <div className="h-full rounded-full transition-all"
                    style={{ width: `${progressPct}%`, background: evStyle.color }} />
                </div>
                {ev.samples_to_verified > 0 && (
                  <div className="text-[10px] text-slate-500">
                    تبقّى {ev.samples_to_verified} عيّنة للوصول إلى «مُتحقَّق ميدانيّاً».
                  </div>
                )}
              </div>

              {/* توزيع أعلام النجاح */}
              {Object.keys(ev.success_flag_counts).length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(ev.success_flag_counts).map(([flag, count]) => (
                    <span key={flag} className="text-[11px] px-2 py-0.5 rounded-full"
                      style={{ background: '#0f1117', color: '#cbd5e1', border: '1px solid #25303f' }}>
                      {flag}: <span className="font-semibold">{count}</span>
                    </span>
                  ))}
                </div>
              )}

              <div className="text-[10px] text-slate-500">
                صفوف مُدامة: {ev.persisted_rows}
                {ev.last_evaluated_at && <> · آخر تقييم: {ev.last_evaluated_at}</>}
              </div>
            </div>

            {/* بانر الصدق: تقديريّ غير مُعايَر + المصدر + warnings_ar */}
            <div className="rounded-xl border p-4 flex items-start gap-3" style={{ background: '#1a1400', borderColor: '#f59e0b33' }}>
              <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
              <div className="space-y-1">
                <div className="text-sm font-semibold text-amber-200">
                  🟡 دليل تقديريّ غير مُعايَر (calibrated = false)
                </div>
                <div className="text-[11px] text-amber-300/80">
                  المصدر: <code className="text-amber-200">{ev.source}</code> — مُشتقّ من النتائج المُدامة، يحتاج معايرة ميدانيّة قبل اعتماده قاطعاً.
                </div>
                {ev.warnings_ar.map((w, i) => (
                  <div key={i} className="text-[11px] text-slate-400">• {w}</div>
                ))}
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
