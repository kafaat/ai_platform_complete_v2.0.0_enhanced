import { useMemo, useState } from 'react';
import { GitBranch, ListOrdered, ScrollText, Shield, FlaskConical, Lock, Ruler } from 'lucide-react';
import {
  useDispatchQueue, useDispatchDecisions, useDecisionLedger, useDecisionPolicies, useEvaluateDispatch, useMeasureOutcome,
} from '../hooks/useApi';
import {
  buildOutcomeInput, dispatchStateColor, dispatchStateLabel, outcomeStatusColor, summarizeDecisions,
} from '../lib/decisionRuntime';
import { T } from '../components/ds';

const ACTIONS = ['irrigation', 'fertigation', 'spray', 'harvest', 'other'];
const RISKS = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];

/** كونسول تشغيل القرار: طابور التوزيع + القرارات المحروسة + سجلّ التنفيذ + السياسات
 *  + معاينة dry-run. صدق: الحالات والخروق والأسباب من الخادم؛ الميزة خلف علم
 *  (404 ⇒ «غير مفعّلة»)؛ ولا زرّ تنفيذ هنا — التنفيذ الفعليّ يمرّ بمسار الموافقات
 *  والمشغِّل (mutating يتطلّب موافقة). */
export default function DecisionRuntimePage() {
  const queueQ = useDispatchQueue();
  const decisionsQ = useDispatchDecisions();
  const ledgerQ = useDecisionLedger();
  const policiesQ = useDecisionPolicies();
  const evalM = useEvaluateDispatch();

  const disabled = !!(queueQ.data?.disabled && decisionsQ.data?.disabled);
  const overview = useMemo(() => summarizeDecisions(decisionsQ.data?.decisions), [decisionsQ.data]);

  const [action, setAction] = useState('irrigation');
  const [risk, setRisk] = useState('MEDIUM');
  const [recId, setRecId] = useState('');
  const [hasGoverning, setHasGoverning] = useState(true);

  // قياس النتيجة: مُخطَّط مقابل مرصود — يغلق حلقة قرار ⇒ أثر.
  const outcomeM = useMeasureOutcome();
  const [ocDecisionId, setOcDecisionId] = useState('');
  const [ocRecIrr, setOcRecIrr] = useState('');
  const [ocActIrr, setOcActIrr] = useState('');
  const [ocExpYield, setOcExpYield] = useState('');
  const [ocActYield, setOcActYield] = useState('');

  const runEvaluate = () => {
    if (!recId.trim()) return;
    evalM.mutate({
      recommendation_id: recId.trim(),
      action_type: action,
      risk_level: risk,
      has_governing_data: hasGoverning,
    });
  };

  return (
    <div className="p-4 flex flex-col gap-3" data-testid="decision-runtime">
      <h1 className="inline-flex items-center gap-2 text-lg font-bold" style={{ color: T.ink }}>
        <GitBranch className="w-5 h-5 text-emerald-300" aria-hidden="true" /> تشغيل القرار (Dispatch)
      </h1>

      {disabled ? (
        <div className="text-sm rounded-2xl border p-3" style={{ borderColor: T.line, color: T.muted }}>
          ميزة موزِّع القرار غير مُفعَّلة في هذه البيئة — اضبط <span className="font-mono">SAHOOL_DECISION_DISPATCH</span> لعرض الطابور والقرارات المحروسة.
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {/* القرارات المحروسة */}
          <section className="rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}>
            <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
              <Shield className="w-4 h-4 text-emerald-300" aria-hidden="true" /> القرارات المحروسة
              <span className="text-[11px] font-normal" style={{ color: T.faint }}>
                · {overview.total} ({overview.ready} جاهز · {overview.pendingApproval} بانتظار · {overview.blocked} محجوب)
              </span>
            </div>
            {decisionsQ.isLoading ? (
              <div className="text-[11px]" style={{ color: T.faint }}>جارٍ القراءة…</div>
            ) : (decisionsQ.data?.decisions ?? []).length === 0 ? (
              <div className="text-[11px]" style={{ color: T.muted }}>لا قرارات توزيع مُسجَّلة بعد.</div>
            ) : (
              <div className="flex flex-col gap-1.5">
                {(decisionsQ.data?.decisions ?? []).slice(0, 6).map((d) => (
                  <div key={d.decision_id} className="text-[11px] flex flex-wrap items-center gap-1.5" style={{ color: T.muted }}>
                    <span className="px-2 py-0.5 rounded-full font-semibold" style={{ border: `1px solid ${T.line}`, color: dispatchStateColor(d.state) }}>
                      {dispatchStateLabel(d.state)}
                    </span>
                    <span style={{ color: T.ink }}>{d.action_type}</span>
                    <span style={{ color: T.faint }}>خطر {d.risk_level} · موافقات {d.approvals_collected}/{d.required_approvals}</span>
                    {d.reason_ar && <span>— {d.reason_ar}</span>}
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* طابور المُشغِّل */}
          <section className="rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}>
            <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
              <ListOrdered className="w-4 h-4 text-sky-300" aria-hidden="true" /> طابور المُشغِّل
              <span className="text-[11px] font-normal" style={{ color: T.faint }}>· {queueQ.data?.count ?? '—'} منتظِراً</span>
            </div>
            {queueQ.isLoading ? (
              <div className="text-[11px]" style={{ color: T.faint }}>جارٍ القراءة…</div>
            ) : (queueQ.data?.queued ?? []).length === 0 ? (
              <div className="text-[11px]" style={{ color: T.muted }}>لا أوامر منتظِرة — الطابور فارغ.</div>
            ) : (
              <div className="flex flex-col gap-1">
                {(queueQ.data?.queued ?? []).slice(0, 6).map((d) => (
                  <div key={d.decision_id} className="text-[11px]" style={{ color: T.muted }}>
                    {(d.created_at ?? '').slice(0, 16)} · <span style={{ color: T.ink }}>{d.action_type}</span>
                    {d.field_id ? ` · حقل ${d.field_id.slice(0, 8)}…` : ''}
                  </div>
                ))}
              </div>
            )}
            <div className="mt-2 inline-flex items-center gap-1 text-[10px]" style={{ color: T.faint }}>
              <Lock className="w-3 h-3" aria-hidden="true" /> التنفيذ عبر المشغِّل ومسار الموافقات — لا تنفيذ من هذه الشاشة.
            </div>
          </section>

          {/* سجلّ التنفيذ */}
          <section className="rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}>
            <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
              <ScrollText className="w-4 h-4 text-amber-300" aria-hidden="true" /> سجلّ التنفيذ
              <span className="text-[11px] font-normal" style={{ color: T.faint }}>· {ledgerQ.data?.count ?? '—'}</span>
            </div>
            {(ledgerQ.data?.ledger ?? []).length === 0 ? (
              <div className="text-[11px]" style={{ color: T.muted }}>لا نتائج تنفيذ مُسجَّلة بعد.</div>
            ) : (
              <div className="flex flex-col gap-1">
                {(ledgerQ.data?.ledger ?? []).slice(0, 6).map((e) => (
                  <div key={e.ledger_id} className="text-[11px]" style={{ color: T.muted }}>
                    {(e.recorded_at ?? '').slice(0, 16)} · <span style={{ color: T.ink }}>{e.action_type ?? '—'}</span>
                    {e.outcome ? ` ⇒ ${e.outcome}` : ''}{e.note_ar ? ` — ${e.note_ar}` : ''}
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* السياسات */}
          <section className="rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}>
            <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
              <Shield className="w-4 h-4 text-violet-300" aria-hidden="true" /> سياسات القرار
              <span className="text-[11px] font-normal" style={{ color: T.faint }}>· {policiesQ.data?.count ?? '—'}</span>
            </div>
            {(policiesQ.data?.policies ?? []).length === 0 ? (
              <div className="text-[11px]" style={{ color: T.muted }}>لا سياسات مُعرَّفة — القرارات تخضع للحواجز الافتراضيّة فقط.</div>
            ) : (
              <div className="flex flex-col gap-1">
                {(policiesQ.data?.policies ?? []).slice(0, 6).map((p) => (
                  <div key={p.policy_id} className="text-[11px] flex items-center gap-1.5" style={{ color: T.muted }}>
                    <span className="px-1.5 rounded" style={{ border: `1px solid ${T.line}`, color: p.enabled ? '#86efac' : T.faint }}>
                      {p.enabled ? 'فعّالة' : 'معطّلة'}
                    </span>
                    <span style={{ color: T.ink }}>{p.name}</span>
                    <span style={{ color: T.faint }}>أولويّة {p.priority}</span>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}

      {/* معاينة dry-run — لا تنفيذ */}
      {!disabled && (
        <section className="rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}>
          <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
            <FlaskConical className="w-4 h-4 text-emerald-300" aria-hidden="true" /> معاينة قرار (dry-run)
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[11px]" style={{ color: T.muted }}>
            <input
              value={recId}
              onChange={(e) => setRecId(e.target.value)}
              placeholder="معرّف التوصية"
              className="w-40 px-2 py-1 rounded-lg"
              style={{ border: `1px solid ${T.line}`, background: 'rgba(2,6,23,.5)', color: T.ink }}
            />
            <select value={action} onChange={(e) => setAction(e.target.value)} className="px-2 py-1 rounded-lg" style={{ border: `1px solid ${T.line}`, background: 'rgba(2,6,23,.5)', color: T.ink }}>
              {ACTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
            <select value={risk} onChange={(e) => setRisk(e.target.value)} className="px-2 py-1 rounded-lg" style={{ border: `1px solid ${T.line}`, background: 'rgba(2,6,23,.5)', color: T.ink }}>
              {RISKS.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
            <label className="inline-flex items-center gap-1">
              <input type="checkbox" checked={hasGoverning} onChange={(e) => setHasGoverning(e.target.checked)} />
              بيانات حاكمة متوفّرة
            </label>
            <button
              type="button"
              onClick={runEvaluate}
              disabled={!recId.trim() || evalM.isPending}
              className="px-2.5 py-1 rounded-lg font-semibold disabled:opacity-50"
              style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' }}
            >
              {evalM.isPending ? 'جارٍ المعاينة…' : 'عاين (بلا تنفيذ)'}
            </button>
          </div>
          {evalM.isError && (
            <div className="mt-2 text-[11px]" role="status" style={{ color: '#fdba74' }}>تعذّرت المعاينة — {evalM.error?.message}</div>
          )}
          {evalM.data && (
            <div className="mt-2 flex flex-col gap-1 text-[11px]" style={{ color: T.muted }}>
              <div>
                <span className="px-2 py-0.5 rounded-full font-semibold" style={{ border: `1px solid ${T.line}`, color: dispatchStateColor(String(evalM.data.state ?? '')) }}>
                  {dispatchStateLabel(String(evalM.data.state ?? ''))}
                </span>
                {evalM.data.dry_run && <span className="mr-1" style={{ color: T.faint }}> · معاينة فقط — لم يُنفَّذ شيء</span>}
              </div>
              {evalM.data.reason_ar && <div>السبب: {evalM.data.reason_ar}</div>}
              {Array.isArray(evalM.data.halt_breaches) && evalM.data.halt_breaches.length > 0 && (
                <div style={{ color: '#fca5a5' }}>خروق حاجبة: {evalM.data.halt_breaches.length}</div>
              )}
              {typeof evalM.data.required_approvals === 'number' && (
                <div style={{ color: T.faint }}>موافقات مطلوبة: {evalM.data.required_approvals}</div>
              )}
            </div>
          )}
        </section>
      )}

      {/* قياس نتيجة قرار — يغلق الحلقة: هل نجح القرار فعلاً؟ (المتوفّر طرفاه فقط يُقيَّم) */}
      <section className="rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}>
        <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
          <Ruler className="w-4 h-4 text-sky-300" aria-hidden="true" /> قياس نتيجة قرار (مُخطَّط ⇄ مرصود)
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[11px]" style={{ color: T.muted }}>
          <input value={ocDecisionId} onChange={(e) => setOcDecisionId(e.target.value)} placeholder="معرّف القرار (اختياريّ)" className="w-40 px-2 py-1 rounded-lg" style={{ border: `1px solid ${T.line}`, background: 'rgba(2,6,23,.5)', color: T.ink }} />
          <input type="number" value={ocRecIrr} onChange={(e) => setOcRecIrr(e.target.value)} placeholder="ريّ موصى (مم)" className="w-28 px-2 py-1 rounded-lg" style={{ border: `1px solid ${T.line}`, background: 'rgba(2,6,23,.5)', color: T.ink }} />
          <input type="number" value={ocActIrr} onChange={(e) => setOcActIrr(e.target.value)} placeholder="ريّ فعليّ (مم)" className="w-28 px-2 py-1 rounded-lg" style={{ border: `1px solid ${T.line}`, background: 'rgba(2,6,23,.5)', color: T.ink }} />
          <input type="number" value={ocExpYield} onChange={(e) => setOcExpYield(e.target.value)} placeholder="غلّة متوقَّعة (طن/هـ)" className="w-32 px-2 py-1 rounded-lg" style={{ border: `1px solid ${T.line}`, background: 'rgba(2,6,23,.5)', color: T.ink }} />
          <input type="number" value={ocActYield} onChange={(e) => setOcActYield(e.target.value)} placeholder="غلّة فعليّة (طن/هـ)" className="w-32 px-2 py-1 rounded-lg" style={{ border: `1px solid ${T.line}`, background: 'rgba(2,6,23,.5)', color: T.ink }} />
          <button
            type="button"
            onClick={() => outcomeM.mutate(buildOutcomeInput({ decisionId: ocDecisionId, recommendedIrrigationMm: ocRecIrr, actualIrrigationMm: ocActIrr, expectedYieldTHa: ocExpYield, actualYieldTHa: ocActYield }))}
            disabled={outcomeM.isPending}
            className="px-2.5 py-1 rounded-lg font-semibold disabled:opacity-50"
            style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' }}
          >
            {outcomeM.isPending ? 'جارٍ القياس…' : 'قِس النتيجة'}
          </button>
        </div>
        {outcomeM.isError && (
          <div className="mt-2 text-[11px]" role="status" style={{ color: '#fdba74' }}>تعذّر القياس — {outcomeM.error?.message}</div>
        )}
        {outcomeM.data && (
          <div className="mt-2 flex flex-col gap-1 text-[11px]" style={{ color: T.muted }}>
            <div style={{ color: T.ink }}>
              قُيِّم <b>{outcomeM.data.n_evaluated}</b> مقياساً · نجح <b>{outcomeM.data.n_success}</b>
              <span style={{ color: T.faint }}> · اكتمال البيانات {Math.round((outcomeM.data.data_completeness ?? 0) * 100)}٪</span>
            </div>
            {outcomeM.data.metrics.map((m) => (
              <div key={`${m.key}-${m.label_ar}`} style={{ color: outcomeStatusColor(m.status) }}>
                {m.label_ar}
                {m.delta != null ? ` (Δ ${m.delta})` : ''}
                {m.ratio != null ? ` (نسبة ${m.ratio})` : ''}
              </div>
            ))}
            {outcomeM.data.warnings_ar.map((w) => (
              <div key={w} style={{ color: T.faint }}>⚠ {w}</div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
