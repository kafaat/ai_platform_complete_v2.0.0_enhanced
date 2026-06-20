// ═══════════════════════════════════════════════════════════════
// SAHOOL — DecisionStudioPage (شرح القرار + إعادة تشغيله)
// قراءة فقط: إدخال decision_id ⇒ تسلسل Signals → Policy → Constraints → Final
// Decision + الثقة + «ماذا حدث فعلاً» (outcomes) + ملخّص الدليل. تستهلك أوّلاً
// GET /api/v1/decision/{id}/explain، وترتدّ عند 404 إلى /lineage (العلم
// FEATURE_DECISION_STUDIO قد يكون مُطفأً) فتشتقّ شرحاً صادقاً من decision_value.
// صدق: لا اختلاق — القرار غير المُدام يُعرَض «غير متاح»، وغياب المعايرة
// (calibrated=false) يُبرَز صراحةً. حالات loading/error/empty صادقة.
// (يطابق أنماط LineagePage/LearningDashboardPage بصريّاً ولونيّاً.)
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import {
  FlaskConical, Search, Radio, Scale, Lock, Target, Activity,
  AlertTriangle, CheckCircle2, XCircle, HelpCircle, History, FileSearch,
} from 'lucide-react';
import { useDecisionExplain } from '../hooks/useApi';
import type {
  DecisionSignal, DecisionExplanation, LineageOutcome,
} from '../services/api';
import { ErrorState, LoadingState, EmptyState } from '../components/StateViews';

// نسّق قيمة مُلخَّصة لعرضها (أرقام بخانتين، غير ذلك كنصّ) — نفس نهج LineagePage.
function fmtValue(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(2);
  if (typeof v === 'boolean') return v ? 'نعم' : 'لا';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

// لون حالة الإشارة (ok/warn/risk/info/neutral) — تناسق مع شارات بقيّة الشاشات.
function signalStyle(status: string): { bg: string; color: string } {
  switch (status) {
    case 'ok':      return { bg: '#0c2a1a', color: '#4ade80' };
    case 'warn':    return { bg: '#2a1a00', color: '#fbbf24' };
    case 'risk':    return { bg: '#2a0d0d', color: '#f87171' };
    case 'info':    return { bg: '#0a1f2e', color: '#38bdf8' };
    default:        return { bg: '#1e293b', color: '#94a3b8' };
  }
}

// قسم مرحلة (Signals/Policy/Constraints/Final) — رأس بأيقونة + محتوى.
function StageSection({
  icon, title, hint, children,
}: { icon: React.ReactNode; title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <div className="flex items-center gap-2">
        {icon}
        <h3 className="text-base font-bold text-slate-100">{title}</h3>
        {hint && <span className="text-[11px] text-slate-500">— {hint}</span>}
      </div>
      <div className="rounded-xl border p-4" style={{ background: '#1e293b', borderColor: '#334155' }}>
        {children}
      </div>
    </section>
  );
}

// بطاقة إشارة واحدة (مدخَل قرار + حالته اللونيّة).
function SignalCard({ s }: { s: DecisionSignal }) {
  const st = signalStyle(s.status);
  return (
    <div className="rounded-lg px-3 py-2 flex items-center justify-between gap-2"
      style={{ background: '#0f1117', border: '1px solid #25303f' }}>
      <div className="min-w-0">
        <div className="text-[11px] text-slate-400 truncate">{s.label_ar}</div>
        <div className="text-sm font-semibold text-slate-200 truncate">{fmtValue(s.value)}</div>
      </div>
      <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold flex-shrink-0"
        style={{ background: st.bg, color: st.color }}>
        {s.status}
      </span>
    </div>
  );
}

// بطاقة نتيجة («ماذا حدث فعلاً») — نجاح/إخفاق/يحتاج بيانات (نفس منطق LineagePage).
function OutcomeCard({ o }: { o: LineageOutcome }) {
  const success =
    o.success === true
      ? { ar: 'ناجحة', icon: <CheckCircle2 className="w-4 h-4" />, bg: '#0c2a1a', color: '#4ade80' }
      : o.success === false
        ? { ar: 'غير ناجحة', icon: <XCircle className="w-4 h-4" />, bg: '#2a0d0d', color: '#f87171' }
        : { ar: 'يحتاج بيانات', icon: <HelpCircle className="w-4 h-4" />, bg: '#1e293b', color: '#94a3b8' };
  const metrics = Object.entries(o.metrics).slice(0, 6);
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
      {metrics.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {metrics.map(([k, v]) => (
            <div key={k} className="rounded-lg px-2 py-1.5" style={{ background: '#0f1117', border: '1px solid #25303f' }}>
              <div className="text-[10px] text-slate-500 truncate">{k}</div>
              <div className="text-sm font-semibold text-slate-200 truncate">{fmtValue(v)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// جسم الشرح: المراحل الأربع + الثقة + إبراز calibrated=false.
function ExplanationBody({ ex }: { ex: DecisionExplanation }) {
  return (
    <div className="space-y-5">
      {/* الثقة + إبراز عدم المعايرة */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] px-2 py-0.5 rounded-full font-semibold"
          style={{ background: '#0a1f2e', color: '#38bdf8' }}>
          الثقة {ex.confidence != null ? `${(ex.confidence * 100).toFixed(0)}%` : '—'}
        </span>
        {!ex.calibrated && (
          <span className="text-[11px] px-2 py-0.5 rounded-full font-semibold flex items-center gap-1"
            style={{ background: '#2a1a00', color: '#fbbf24' }}>
            <AlertTriangle className="w-3 h-3" /> غير مُعايَر (calibrated=false)
          </span>
        )}
      </div>

      {/* 1) الإشارات */}
      <StageSection icon={<Radio className="w-4 h-4 text-emerald-400" />} title="الإشارات" hint="المدخلات المؤثّرة">
        {ex.signals.length === 0 ? (
          <div className="text-[12px] text-slate-500">لا إشارات مُسجَّلة لهذا القرار.</div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {ex.signals.map((s, i) => <SignalCard key={`${s.key}-${i}`} s={s} />)}
          </div>
        )}
      </StageSection>

      {/* 2) السياسة */}
      <StageSection icon={<Scale className="w-4 h-4 text-emerald-400" />} title="السياسة" hint="المُحلّة/المُطبَّقة وأسبابها">
        {ex.policy ? (
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-[11px] px-2 py-0.5 rounded-full font-semibold"
                style={{ background: '#16a34a18', color: '#4ade80' }}>
                {ex.policy.auto ? 'تلقائيّة (auto)' : 'يدويّة'}
              </span>
              <span className="text-slate-300">
                المُحلّة: <span className="font-semibold text-slate-100">{ex.policy.resolved ?? '—'}</span>
              </span>
              <span className="text-slate-300">
                المُطبَّقة: <span className="font-semibold text-slate-100">{ex.policy.applied ?? '—'}</span>
              </span>
            </div>
            {ex.policy.reasons_ar.length > 0 ? (
              <ul className="space-y-1">
                {ex.policy.reasons_ar.map((r, i) => (
                  <li key={i} className="text-[12px] text-slate-400">• {r}</li>
                ))}
              </ul>
            ) : (
              <div className="text-[12px] text-slate-500">لا أسباب مُسجَّلة.</div>
            )}
          </div>
        ) : (
          <div className="text-[12px] text-slate-500">لا قرار سياسة مُدام لهذا القرار.</div>
        )}
      </StageSection>

      {/* 3) القيود */}
      <StageSection icon={<Lock className="w-4 h-4 text-emerald-400" />} title="القيود" hint="سقوف/حدود مطبَّقة">
        {ex.constraints.length === 0 ? (
          <div className="text-[12px] text-slate-500">لا قيود مُسجَّلة.</div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {ex.constraints.map((c, i) => (
              <div key={(c.key ?? '') + i} className="rounded-lg px-3 py-2"
                style={{ background: '#0f1117', border: '1px solid #25303f' }}>
                <div className="text-[11px] text-slate-400 truncate">{c.label_ar ?? c.key ?? '—'}</div>
                <div className="text-sm font-semibold text-slate-200 truncate">{fmtValue(c.value)}</div>
              </div>
            ))}
          </div>
        )}
      </StageSection>

      {/* 4) القرار النهائيّ */}
      <StageSection icon={<Target className="w-4 h-4 text-emerald-400" />} title="القرار النهائيّ">
        {Object.keys(ex.final).length === 0 ? (
          <div className="text-[12px] text-slate-500">لا تفاصيل قرار نهائيّ مُدامة.</div>
        ) : (
          <div className="space-y-2">
            {Object.entries(ex.final).map(([k, v]) => (
              <div key={k} className="flex items-start gap-2 text-sm">
                <span className="text-[11px] px-2 py-0.5 rounded-full font-semibold flex-shrink-0 mt-0.5"
                  style={{ background: '#16a34a18', color: '#4ade80' }}>{k}</span>
                <span className="text-slate-200">{fmtValue(v)}</span>
              </div>
            ))}
          </div>
        )}
      </StageSection>

      {/* تحذيرات صدق إن وُجدت */}
      {ex.warnings_ar.length > 0 && (
        <div className="rounded-xl border p-3 flex items-start gap-3"
          style={{ background: '#1a1400', borderColor: '#f59e0b33' }}>
          <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
          <div className="space-y-1">
            {ex.warnings_ar.map((w, i) => (
              <div key={i} className="text-[12px] text-amber-200/90">• {w}</div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function DecisionStudioPage() {
  const [input, setInput] = useState('');
  const [decisionId, setDecisionId] = useState('');
  const explain = useDecisionExplain(decisionId);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setDecisionId(input.trim());
  };

  const data = explain.data;

  return (
    <div className="space-y-6 max-w-4xl mx-auto" dir="rtl">
      <div className="flex items-center gap-2">
        <FlaskConical className="w-5 h-5 text-emerald-400" />
        <h2 className="text-xl font-bold text-slate-100">استوديو القرار</h2>
      </div>
      <p className="text-sm text-slate-400">
        شرحٌ صادق لقرارٍ مُتَّخَذ: تسلسل <span className="text-emerald-300">الإشارات ← السياسة ← القيود ← القرار النهائيّ</span> مع الثقة،
        ثمّ <span className="text-emerald-300">«ماذا حدث فعلاً»</span> (النتائج المقيسة). لا اختلاق: القرار غير المُدام يُعرَض «غير متاح»،
        والقيم <span className="text-amber-300">غير المُعايَرة</span> تُبرَز صراحةً.
      </p>

      {/* إدخال معرّف القرار */}
      <form onSubmit={submit}
        className="rounded-xl border p-4 flex flex-col sm:flex-row gap-3 sm:items-end"
        style={{ background: '#1e293b', borderColor: '#334155' }}>
        <label className="flex flex-col gap-1 flex-1">
          <span className="text-xs text-slate-400">معرّف القرار (decision_id)</span>
          <input value={input} onChange={e => setInput(e.target.value)}
            placeholder="dec_..." dir="ltr"
            className="px-3 py-2 rounded-lg text-sm"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
        </label>
        <button type="submit" disabled={!input.trim() || explain.isFetching}
          className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-60"
          style={{ background: '#16a34a' }}>
          <Search className="w-4 h-4" />
          {explain.isFetching ? 'جارٍ الشرح…' : 'اشرح القرار'}
        </button>
      </form>

      {!decisionId && (
        <EmptyState
          icon={<FlaskConical className="w-8 h-8" />}
          title="أدخِل معرّف قرار لشرحه"
          hint="الصق decision_id من سلسلة النَّسَب أو سجلّ القرارات لرؤية الإشارات والسياسة والقيود والنتائج." />
      )}

      {decisionId && explain.isLoading && <LoadingState message="جارٍ جلب شرح القرار…" />}
      {decisionId && explain.isError && (
        <ErrorState title="تعذّر جلب شرح القرار"
          detail="قد تكون القاعدة غير متاحة (503) أو لا صلاحيّة عرض (403)."
          onRetry={() => explain.refetch()} />
      )}

      {data && (
        <div className="space-y-5">
          {/* رأس القرار + مصدر الشرح (شفافيّة) */}
          <div className="rounded-xl border p-4 flex items-center justify-between gap-2"
            style={{ background: '#1e293b', borderColor: '#334155' }}>
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-emerald-400" />
              <span className="text-sm font-semibold text-slate-100">{data.decision_type}</span>
              <span className="text-[11px] text-slate-500" dir="ltr">{data.decision_id}</span>
            </div>
            <span className="text-[10px] px-2 py-0.5 rounded-full font-medium"
              style={{ background: '#0f1117', color: '#94a3b8', border: '1px solid #25303f' }}>
              {data.source === 'explain' ? 'مصدر: /explain' : 'مصدر: مشتقّ من النَّسَب'}
            </span>
          </div>

          {/* القرار غير مُدام ⇒ «غير متاح» صادق (لا اختلاق) */}
          {!data.found || !data.explanation ? (
            <div className="rounded-xl border p-4 flex items-start gap-3"
              style={{ background: '#1a1400', borderColor: '#f59e0b33' }}>
              <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-amber-200">
                شرح القرار غير متاح: القرار غير مُدام (قد يكون حُسِب عبر المسار النقيّ، أو الإدامة مُطفأة).
                لا نختلق شرحاً — هذه الحالة معروضة كما هي.
              </div>
            </div>
          ) : (
            <ExplanationBody ex={data.explanation} />
          )}

          {/* ماذا حدث فعلاً (outcomes / replay) */}
          <StageSection icon={<History className="w-4 h-4 text-emerald-400" />} title="ماذا حدث فعلاً" hint="النتائج المقيسة لاحقاً">
            {data.outcomes.length === 0 ? (
              <div className="text-[12px] text-slate-500">
                لا نتائج مُسجَّلة بعد لهذا القرار — لم يُقَس أثره ميدانيّاً.
              </div>
            ) : (
              <div className="space-y-2">
                {data.outcomes.map(o => <OutcomeCard key={o.outcome_id} o={o} />)}
              </div>
            )}
          </StageSection>

          {/* ملخّص الدليل */}
          {data.evidence && Object.keys(data.evidence).length > 0 && (
            <StageSection icon={<FileSearch className="w-4 h-4 text-emerald-400" />} title="ملخّص الدليل">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {Object.entries(data.evidence).map(([k, v]) => (
                  <div key={k} className="rounded-lg px-3 py-2"
                    style={{ background: '#0f1117', border: '1px solid #25303f' }}>
                    <div className="text-[11px] text-slate-400 truncate">{k}</div>
                    <div className="text-sm font-semibold text-slate-200 truncate">{fmtValue(v)}</div>
                  </div>
                ))}
              </div>
            </StageSection>
          )}
        </div>
      )}
    </div>
  );
}
