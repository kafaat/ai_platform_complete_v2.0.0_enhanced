import { useState } from 'react';
import { Droplets, GraduationCap, History, Microscope } from 'lucide-react';
import {
  useDecisionExplainInsight, useDecisionImpact, useDecisionLearning, useDecisionRecordsInsight,
} from '../../hooks/useApi';
import {
  dash, decisionTypeLabel, explanationSteps, outcomeSuccessColor, outcomeSuccessLabel,
  percentLabel, suggestionKindColor, suggestionKindLabel,
} from '../../lib/decisionInsight';
import { T } from '../ds';

/** لوحة رؤى القرار: سجلّ القرارات المُدامة + سلسلة الشرح (لماذا؟) + اقتراحات التعلُّم
 *  المُسنَدة بالأثر + الأثر المُحقَّق (هل نفع؟). قراءة فقط — لا كتابة من هذه اللوحة.
 *  صدق: أحكام الخادم تمرّ كما هي (calibrated=false يُعرَض، advisory_only يُعلَن)؛
 *  404 ⇒ حالة «غير مفعّلة» صادقة لا خطأ مُفزِع؛ الغائب «—» لا صفر مُختلق. */
export default function DecisionInsightPanel() {
  const recordsQ = useDecisionRecordsInsight();
  const learningQ = useDecisionLearning();
  const impactQ = useDecisionImpact();

  // الشرح يتبع قراراً محدّداً: يُختار من السجلّ أو يُدخَل معرّفه يدويّاً.
  const [selectedId, setSelectedId] = useState('');
  const explainQ = useDecisionExplainInsight(selectedId.trim() || null);
  const steps = explanationSteps(explainQ.data?.explanation);

  return (
    <div className="grid gap-3 md:grid-cols-2" data-testid="decision-insight">
      {/* سجلّ القرارات المُدامة */}
      <section className="rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}>
        <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
          <History className="w-4 h-4 text-emerald-300" aria-hidden="true" /> سجلّ القرارات المُدامة
          <span className="text-[11px] font-normal" style={{ color: T.faint }}>· {recordsQ.data?.count ?? '—'}</span>
        </div>
        {recordsQ.isLoading ? (
          <div className="text-[11px]" style={{ color: T.faint }}>جارٍ القراءة…</div>
        ) : recordsQ.data?.disabled ? (
          <div className="text-[11px]" style={{ color: T.muted }}>مسار سجلّ القرارات غير متاح في هذه البيئة.</div>
        ) : (recordsQ.data?.decisions ?? []).length === 0 ? (
          <div className="text-[11px]" style={{ color: T.muted }}>لا قرارات مُدامة بعد — تُدام القرارات القابلة للتنفيذ إلزاميّاً.</div>
        ) : (
          <div className="flex flex-col gap-1.5">
            {(recordsQ.data?.decisions ?? []).slice(0, 6).map((d) => (
              <button
                key={d.decision_id}
                type="button"
                onClick={() => setSelectedId(d.decision_id)}
                className="text-right text-[11px] flex flex-wrap items-center gap-1.5 rounded-lg px-1 py-0.5"
                style={{
                  color: T.muted,
                  border: `1px solid ${selectedId === d.decision_id ? '#14532d' : 'transparent'}`,
                }}
                title="اعرض شرح هذا القرار"
              >
                <span style={{ color: T.ink }}>{decisionTypeLabel(d.decision_type)}</span>
                <span style={{ color: T.faint }}>ثقة {percentLabel(d.confidence)}</span>
                <span style={{ color: T.faint }}>{(d.created_at ?? '').slice(0, 16) || '—'}</span>
                {d.field_id && <span style={{ color: T.faint }}>حقل {d.field_id.slice(0, 8)}…</span>}
              </button>
            ))}
          </div>
        )}
      </section>

      {/* شرح القرار — لماذا هذا القرار؟ (FEATURE_DECISION_STUDIO) */}
      <section className="rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}>
        <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
          <Microscope className="w-4 h-4 text-sky-300" aria-hidden="true" /> شرح القرار (لماذا؟)
        </div>
        <input
          value={selectedId}
          onChange={(e) => setSelectedId(e.target.value)}
          placeholder="معرّف القرار — أو اختر من السجلّ"
          className="w-56 px-2 py-1 mb-2 rounded-lg text-[11px]"
          style={{ border: `1px solid ${T.line}`, background: 'rgba(2,6,23,.5)', color: T.ink }}
        />
        {!selectedId.trim() ? (
          <div className="text-[11px]" style={{ color: T.muted }}>اختر قراراً من السجلّ (أو أدخِل معرّفه) لعرض سلسلة شرحه.</div>
        ) : explainQ.isLoading ? (
          <div className="text-[11px]" style={{ color: T.faint }}>جارٍ القراءة…</div>
        ) : explainQ.isError ? (
          <div className="text-[11px]" role="status" style={{ color: '#fdba74' }}>تعذّر الشرح — {explainQ.error?.message}</div>
        ) : explainQ.data?.disabled ? (
          <div className="text-[11px]" style={{ color: T.muted }}>
            الشرح غير متاح — الميزة غير مُفعَّلة (اضبط <span className="font-mono">FEATURE_DECISION_STUDIO</span>) أو القرار غير مُدام.
          </div>
        ) : explainQ.data ? (
          <div className="flex flex-col gap-1 text-[11px]" style={{ color: T.muted }}>
            <div style={{ color: T.ink }}>
              {decisionTypeLabel(explainQ.data.decision_type)}
              <span style={{ color: T.faint }}> · {dash(explainQ.data.region)} · {(explainQ.data.created_at ?? '').slice(0, 16) || '—'}</span>
            </div>
            {steps.length === 0 ? (
              <div style={{ color: T.muted }}>القرار مُدام بلا كتل شرح حاضرة — الغياب يُكشَف لا يُختلق.</div>
            ) : (
              steps.map((s) => (
                <div key={s.key}>
                  <span className="font-semibold" style={{ color: T.ink }}>{s.label_ar}:</span> {s.detail_ar}
                </div>
              ))
            )}
            {(explainQ.data.outcomes ?? []).length > 0 && (
              <div className="mt-1">
                <span className="font-semibold" style={{ color: T.ink }}>النتائج المُدامة ({explainQ.data.outcome_count}):</span>
                {(explainQ.data.outcomes ?? []).slice(0, 3).map((o) => (
                  <span key={o.outcome_id} className="mr-1 px-1.5 rounded" style={{ border: `1px solid ${T.line}`, color: outcomeSuccessColor(o.success) }}>
                    {outcomeSuccessLabel(o.success)}
                  </span>
                ))}
              </div>
            )}
            <div style={{ color: T.faint }}>⚠ سلسلة مشتقّة من قرار غير معايَر (calibrated=false) — تُعلَن لا تُخفى.</div>
          </div>
        ) : null}
      </section>

      {/* اقتراحات التعلُّم — استشاريّة (SAHOOL_DECISION_DISPATCH) */}
      <section className="rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}>
        <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
          <GraduationCap className="w-4 h-4 text-violet-300" aria-hidden="true" /> اقتراحات التعلُّم
          <span className="text-[11px] font-normal px-1.5 rounded" style={{ border: `1px solid ${T.line}`, color: T.faint }}>
            استشاريّة — لا تُطبَّق آليّاً
          </span>
        </div>
        {learningQ.isLoading ? (
          <div className="text-[11px]" style={{ color: T.faint }}>جارٍ القراءة…</div>
        ) : learningQ.data?.disabled ? (
          <div className="text-[11px]" style={{ color: T.muted }}>
            ميزة موزِّع القرار غير مُفعَّلة — اضبط <span className="font-mono">SAHOOL_DECISION_DISPATCH</span> لاشتقاق الاقتراحات.
          </div>
        ) : (learningQ.data?.suggestions ?? []).length === 0 ? (
          <div className="text-[11px]" style={{ color: T.muted }}>
            لا اقتراحات بعد — العيّنة غير كافية
            {learningQ.data?.based_on ? ` (الحدّ الأدنى ${learningQ.data.based_on.min_sample} قرارات نهائيّة لكلّ إجراء)` : ''}.
          </div>
        ) : (
          <div className="flex flex-col gap-1.5">
            {(learningQ.data?.suggestions ?? []).slice(0, 6).map((s) => (
              <div key={`${s.kind}-${s.action_type}`} className="text-[11px] flex flex-wrap items-center gap-1.5" style={{ color: T.muted }}>
                <span className="px-2 py-0.5 rounded-full font-semibold" style={{ border: `1px solid ${T.line}`, color: suggestionKindColor(s.kind) }}>
                  {suggestionKindLabel(s.kind)}
                </span>
                <span>{s.message_ar}</span>
                <span style={{ color: T.faint }}>عيّنة {s.evidence.sample} · ثقة {percentLabel(s.confidence)}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* الأثر المُحقَّق — هل نفع؟ (SAHOOL_DECISION_DISPATCH) */}
      <section className="rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}>
        <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
          <Droplets className="w-4 h-4 text-amber-300" aria-hidden="true" /> الأثر المُحقَّق
          <span className="text-[11px] font-normal" style={{ color: T.faint }}>· قياس ما حدث، لا تنبّؤ</span>
        </div>
        {impactQ.isLoading ? (
          <div className="text-[11px]" style={{ color: T.faint }}>جارٍ القراءة…</div>
        ) : impactQ.data?.disabled ? (
          <div className="text-[11px]" style={{ color: T.muted }}>
            ميزة موزِّع القرار غير مُفعَّلة — اضبط <span className="font-mono">SAHOOL_DECISION_DISPATCH</span> لقياس الأثر.
          </div>
        ) : (impactQ.data?.total_decisions ?? 0) === 0 ? (
          <div className="text-[11px]" style={{ color: T.muted }}>لا سجلّات تنفيذ بعد — الأثر يُقاس من execution_ledger لا يُقدَّر.</div>
        ) : impactQ.data ? (
          <div className="flex flex-col gap-1 text-[11px]" style={{ color: T.muted }}>
            <div style={{ color: T.ink }}>
              {impactQ.data.total_decisions} قراراً · نُفِّذ <b>{impactQ.data.executed}</b> · فشل <b>{impactQ.data.failed}</b>
              <span style={{ color: T.faint }}> · نجاح {percentLabel(impactQ.data.success_rate)}</span>
            </div>
            <div>
              ماء موفَّر <span style={{ color: '#7dd3fc' }}>{impactQ.data.water_saved_mm}مم</span>
              <span style={{ color: T.faint }}> (من {impactQ.data.water_records} سجلّاً اكتملت كمّيّاته — الناقص لا يُحتسَب)</span>
            </div>
            {Object.entries(impactQ.data.by_action ?? {}).slice(0, 4).map(([action, a]) => (
              <div key={action} style={{ color: T.faint }}>
                <span style={{ color: T.ink }}>{action}</span> · نُفِّذ {a.executed} · فشل {a.failed} · وفّر {a.water_saved_mm}مم
              </div>
            ))}
          </div>
        ) : null}
      </section>
    </div>
  );
}
