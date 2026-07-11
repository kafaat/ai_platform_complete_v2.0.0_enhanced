import { useState } from 'react';
import { ShieldCheck, Bot, GitBranch, Check, X, ClipboardCheck } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import {
  usePendingAgentApprovals, useDecideAgentApproval, useDispatchDecisions,
  useDecisionReviewQueue, useReviewDecisionCandidate,
} from '../hooks/useApi';
import { useAuthStore } from '../hooks/useAuth';
import { canManage } from '../lib/permissions';
import {
  approvalKey, candidateEvidenceSummary, newReviewIdempotencyKey, paramsSummary,
  pendingDispatchDecisions, riskColor,
} from '../lib/approvalsConsole';
import { dispatchStateColor, dispatchStateLabel } from '../lib/decisionRuntime';
import { T } from '../components/ds';

/** كونسول الموافقات الموحَّد (آخر طبقة partial في سجلّ التغطية): طلبات أدوات وكيل
 *  AI المعلّقة (v58: لا mutating بلا موافقة بشريّة) + قرارات التوزيع المنتظِرة موافقة.
 *  صدق: الموافِق المسجَّل هويّة البوّابة الموثوقة (SEC-3.1) لا الـbody؛ الاعتماد هنا
 *  لا ينفّذ الأداة — التنفيذ على خدمة النطاق المالكة بعد التخويل. owner/manager فقط. */
export default function ApprovalsConsolePage() {
  const { user } = useAuthStore();
  const allowed = canManage(user?.role);
  const qc = useQueryClient();

  const approvalsQ = usePendingAgentApprovals(allowed);
  const decisionsQ = useDispatchDecisions(allowed);
  const decideM = useDecideAgentApproval();
  const reviewQueueQ = useDecisionReviewQueue(allowed);
  const reviewM = useReviewDecisionCandidate();
  const [rowStates, setRowStates] = useState<Record<string, string>>({});
  const [reviewReasons, setReviewReasons] = useState<Record<string, string>>({});

  if (!allowed) {
    return (
      <div className="p-4 text-sm" style={{ color: T.muted }}>
        هذه الصفحة مقصورة على المالك/المدير — دورك الحاليّ لا يخوّل البتّ في الموافقات.
      </div>
    );
  }

  const pending = approvalsQ.data?.pending ?? [];
  const pendingDispatch = pendingDispatchDecisions(decisionsQ.data?.decisions);

  const decide = (approval: (typeof pending)[number], decision: 'approve' | 'deny') => {
    const key = approvalKey(approval);
    setRowStates((s) => ({ ...s, [key]: 'sending' }));
    decideM.mutate(
      { approval, decision, reason: decision === 'deny' ? 'denied_by_manager' : undefined },
      {
        onSuccess: () => {
          setRowStates((s) => ({ ...s, [key]: decision === 'approve' ? 'approved' : 'denied' }));
          qc.invalidateQueries({ queryKey: ['pending-agent-approvals'] });
        },
        onError: () => setRowStates((s) => ({ ...s, [key]: 'failed' })),
      },
    );
  };


  const reviewCandidate = (
    decisionId: string,
    candidateLineageId: string,
    action: 'approve' | 'reject',
  ) => {
    const reason = (reviewReasons[decisionId] ?? '').trim();
    if (action === 'reject' && !reason) {
      setRowStates((state) => ({ ...state, [decisionId]: 'reason_required' }));
      return;
    }
    setRowStates((state) => ({ ...state, [decisionId]: 'sending' }));
    reviewM.mutate(
      {
        decisionId,
        action,
        reason,
        candidateLineageId,
        idempotencyKey: newReviewIdempotencyKey(decisionId),
      },
      {
        onSuccess: (result) => {
          setRowStates((state) => ({ ...state, [decisionId]: result.state }));
          qc.invalidateQueries({ queryKey: ['decision-review-queue'] });
        },
        onError: () => setRowStates((state) => ({ ...state, [decisionId]: 'failed' })),
      },
    );
  };

  return (
    <div className="p-4 flex flex-col gap-3" data-testid="approvals-console">
      <h1 className="inline-flex items-center gap-2 text-lg font-bold" style={{ color: T.ink }}>
        <ShieldCheck className="w-5 h-5 text-emerald-300" aria-hidden="true" /> كونسول الموافقات
      </h1>


      {/* WX-10.8 — authoritative decision candidates */}
      <section className="rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}>
        <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
          <ClipboardCheck className="w-4 h-4 text-violet-300" aria-hidden="true" /> مرشّحات القرار بانتظار المراجعة
          <span className="text-[11px] font-normal" style={{ color: T.faint }}>· {reviewQueueQ.data?.count ?? '—'}</span>
        </div>
        {reviewQueueQ.isLoading ? (
          <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة الطابور الآمر…</div>
        ) : reviewQueueQ.isError ? (
          <div className="text-[11px]" role="alert" style={{ color: '#fdba74' }}>
            طابور المراجعة غير متاح. في وضع mirror يفشل المسار مغلقاً ولا يعرض قائمة فارغة مضللة.
          </div>
        ) : (reviewQueueQ.data?.items ?? []).length === 0 ? (
          <div className="text-[11px]" style={{ color: T.muted }}>لا توجد مرشّحات قرار معلّقة.</div>
        ) : (
          <div className="flex flex-col gap-2">
            {(reviewQueueQ.data?.items ?? []).map((candidate) => {
              const state = rowStates[candidate.decision_id];
              const reason = reviewReasons[candidate.decision_id] ?? '';
              return (
                <article key={candidate.decision_id} className="rounded-xl border p-3 text-[11px]" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }}>
                  <div className="flex flex-wrap items-center gap-2">
                    <strong style={{ color: T.ink }}>{candidate.decision_type ?? 'قرار زراعي'}</strong>
                    {candidate.field_id && <span style={{ color: T.muted }}>حقل: {candidate.field_id}</span>}
                    {candidate.confidence != null && <span style={{ color: T.faint }}>الثقة: {Math.round(candidate.confidence * 100)}%</span>}
                    {candidate.created_at && <time style={{ color: T.faint }}>{new Date(candidate.created_at).toLocaleString('ar')}</time>}
                  </div>
                  <p className="mt-1" style={{ color: T.muted }}>{candidateEvidenceSummary(candidate.decision_value)}</p>
                  <div className="mt-1 break-all" style={{ color: T.faint }}>lineage: {candidate.candidate_lineage_id}</div>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <input
                      value={reason}
                      onChange={(event) => setReviewReasons((items) => ({ ...items, [candidate.decision_id]: event.target.value }))}
                      placeholder="سبب المراجعة (إلزامي عند الرفض)"
                      aria-label={`سبب مراجعة ${candidate.decision_id}`}
                      className="min-w-[240px] flex-1 rounded-lg border px-2 py-1 bg-transparent"
                      style={{ borderColor: T.line, color: T.ink }}
                      disabled={state === 'sending'}
                    />
                    <button type="button" onClick={() => reviewCandidate(candidate.decision_id, candidate.candidate_lineage_id, 'approve')} disabled={state === 'sending'} className="inline-flex items-center gap-1 px-2 py-1 rounded-lg font-semibold disabled:opacity-50" style={{ border: '1px solid #14532d', color: '#86efac' }}>
                      <Check className="w-3 h-3" aria-hidden="true" /> اعتماد
                    </button>
                    <button type="button" onClick={() => reviewCandidate(candidate.decision_id, candidate.candidate_lineage_id, 'reject')} disabled={state === 'sending'} className="inline-flex items-center gap-1 px-2 py-1 rounded-lg font-semibold disabled:opacity-50" style={{ border: '1px solid #7c2d12', color: '#fca5a5' }}>
                      <X className="w-3 h-3" aria-hidden="true" /> رفض
                    </button>
                    {state === 'reason_required' && <span role="alert" style={{ color: '#fca5a5' }}>سبب الرفض إلزامي.</span>}
                    {state === 'failed' && <span role="alert" style={{ color: '#fdba74' }}>تعذّر حفظ المراجعة؛ أعد تحميل الطابور قبل المحاولة.</span>}
                    {(state === 'approved' || state === 'rejected') && <span role="status" style={{ color: state === 'approved' ? '#86efac' : '#fca5a5' }}>{state === 'approved' ? 'اعتُمد' : 'رُفض'}</span>}
                  </div>
                </article>
              );
            })}
          </div>
        )}
        <div className="mt-2 text-[10px]" style={{ color: T.faint }}>
          الانتقال وحفظ سجل المراجعة مملوكان لـdecision-service؛ هذه الشاشة لا تنشئ مهمة ولا dispatch ولا أمر معدّة.
        </div>
      </section>

      {/* طلبات أدوات وكيل AI */}
      <section className="rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}>
        <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
          <Bot className="w-4 h-4 text-emerald-300" aria-hidden="true" /> طلبات وكيل الذكاء المعلّقة
          <span className="text-[11px] font-normal" style={{ color: T.faint }}>· {approvalsQ.data?.count ?? '—'}</span>
        </div>
        {approvalsQ.isLoading ? (
          <div className="text-[11px]" style={{ color: T.faint }}>جارٍ القراءة…</div>
        ) : approvalsQ.data?.disabled ? (
          <div className="text-[11px]" style={{ color: T.muted }}>خدمة الوكيل غير متاحة في هذه البيئة.</div>
        ) : pending.length === 0 ? (
          <div className="text-[11px]" style={{ color: T.muted }}>لا طلبات معلّقة — كلّ أدوات الوكيل الحسّاسة بُتَّ فيها.</div>
        ) : (
          <div className="flex flex-col gap-2">
            {pending.map((a) => {
              const key = approvalKey(a);
              const state = rowStates[key];
              return (
                <div key={key} className="flex flex-wrap items-center gap-2 rounded-xl border p-2 text-[11px]" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }}>
                  <span className="px-2 py-0.5 rounded-full font-semibold" style={{ border: `1px solid ${T.line}`, color: riskColor(a.risk) }}>
                    {a.risk ?? '—'}
                  </span>
                  <span className="font-bold" style={{ color: T.ink }}>{a.tool ?? '—'}</span>
                  {a.capability && <span style={{ color: T.faint }}>({a.capability})</span>}
                  <span style={{ color: T.muted }}>وسائط: {paramsSummary(a.params)}</span>
                  <span className="mr-auto" />
                  {state === 'approved' || state === 'denied' ? (
                    <span role="status" style={{ color: state === 'approved' ? '#86efac' : '#fca5a5' }}>
                      {state === 'approved' ? 'اعتُمد' : 'رُفض'} — التنفيذ على خدمة النطاق بعد التخويل
                    </span>
                  ) : state === 'failed' ? (
                    <span role="status" style={{ color: '#fdba74' }}>تعذّر الحفظ — أعد المحاولة</span>
                  ) : (
                    <>
                      <button
                        type="button"
                        onClick={() => decide(a, 'approve')}
                        disabled={state === 'sending'}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg font-semibold disabled:opacity-50"
                        style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' }}
                      >
                        <Check className="w-3 h-3" aria-hidden="true" /> اعتمِد
                      </button>
                      <button
                        type="button"
                        onClick={() => decide(a, 'deny')}
                        disabled={state === 'sending'}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg font-semibold disabled:opacity-50"
                        style={{ border: '1px solid #7c2d12', color: '#fca5a5', background: 'rgba(15,23,42,.45)' }}
                      >
                        <X className="w-3 h-3" aria-hidden="true" /> ارفض
                      </button>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        )}
        <div className="mt-2 text-[10px]" style={{ color: T.faint }}>
          الموافِق المسجَّل = هويّتك الموثّقة عبر البوّابة (SEC-3.1) — لا يُسجَّل من حقل الطلب.
        </div>
      </section>

      {/* قرارات التوزيع بانتظار موافقة */}
      <section className="rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}>
        <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
          <GitBranch className="w-4 h-4 text-sky-300" aria-hidden="true" /> قرارات التوزيع المنتظِرة موافقة
          <span className="text-[11px] font-normal" style={{ color: T.faint }}>· {pendingDispatch.length}</span>
        </div>
        {decisionsQ.data?.disabled ? (
          <div className="text-[11px]" style={{ color: T.muted }}>موزِّع القرار غير مُفعَّل (SAHOOL_DECISION_DISPATCH).</div>
        ) : pendingDispatch.length === 0 ? (
          <div className="text-[11px]" style={{ color: T.muted }}>لا قرارات منتظِرة — كلّ القرارات المحروسة إمّا جاهزة أو محجوبة.</div>
        ) : (
          <div className="flex flex-col gap-1.5">
            {pendingDispatch.slice(0, 10).map((d) => (
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
        <div className="mt-2 text-[10px]" style={{ color: T.faint }}>
          جمع موافقات التوزيع يمرّ عبر مسار evaluate/execute المحروس — هذه القائمة رقابيّة (من يقرأها يعرف ما ينتظر البتّ).
        </div>
      </section>
    </div>
  );
}
