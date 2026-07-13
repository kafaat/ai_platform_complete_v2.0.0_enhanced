import { Layers, ShieldCheck, ShieldAlert, GitBranch, CircleCheck } from 'lucide-react';
import { useSoilWorkspace } from '../../hooks/useApi';
import { T, toneColors } from '../ds';

interface Props {
  /** الحقل النشط — تُقرأ حوكمة تربته من soil-service عبر بوّابة /api/soil. */
  fieldId?: string | null;
  enabled?: boolean;
}

// مستوى الأدلّة → تسمية عربيّة + نغمة (أعلى ثقةً ⇐ أخضر).
const EVIDENCE_AR: Record<string, { label: string; tone: 'ok' | 'warn' | 'danger' | 'info' | 'neutral' }> = {
  baseline_only: { label: 'أساس فقط', tone: 'danger' },
  modelled: { label: 'نمذجة', tone: 'warn' },
  analog_guided: { label: 'مُوجَّه بالمناظر', tone: 'warn' },
  field_observed: { label: 'مرصود حقليّاً', tone: 'info' },
  lab_verified: { label: 'مُتحقَّق مختبريّاً', tone: 'ok' },
  operational_verified: { label: 'مُتحقَّق تشغيليّاً', tone: 'ok' },
};

/** بطاقة حوكمة التربة: تعرض حالة الحلقة المغلقة الكنسيّة (soil-service P4) — مستوى
 *  الأدلّة، بوّابة الجودة (نجاح/قابليّة تنفيذ + أسباب)، الاكتمال، الاستخدامات المسموحة/
 *  المحجوبة، وعدّادات سلسلة التنفيذ/التحقّق/النتائج/التعلّم. قراءة فقط — تعرض ولا تحكم،
 *  وتُظهِر «لا لقطة تربة بعد» بصدق عند غياب البيانات (لا تلفيق). */
export default function SoilGovernanceCard({ fieldId, enabled = true }: Props) {
  const { summary, hasProfile, isLoading, isError } = useSoilWorkspace(fieldId ?? null, enabled);

  if (!enabled) return null;

  const evidence = summary ? EVIDENCE_AR[summary.evidenceLevel] ?? { label: summary.evidenceLevel, tone: 'neutral' as const } : null;
  const gateTone = summary?.qualityGate.passed ? 'ok' : 'warn';

  return (
    <section
      className="mb-3 rounded-2xl border p-3"
      style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}
      data-testid="soil-governance"
      aria-label="حوكمة التربة"
    >
      <div className="flex items-center gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <Layers className="w-4 h-4 text-emerald-300" aria-hidden="true" /> حوكمة التربة (الحلقة المغلقة)
        </span>
      </div>

      {isLoading ? (
        <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة لقطة التربة الكنسيّة…</div>
      ) : isError || !hasProfile || !summary ? (
        <div className="text-[11px]" style={{ color: T.muted }}>
          لا لقطة تربة كنسيّة لهذا الحقل بعد — تُبنى عند ورود أدلّة (SoilGrids / مختبر / رصد حقليّ).
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {/* مستوى الأدلّة + الاكتمال */}
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
            {evidence && (() => {
              const tc = toneColors(evidence.tone);
              return (
                <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold" style={{ color: tc.fg, background: tc.bg }}>
                  مستوى الأدلّة: {evidence.label}
                </span>
              );
            })()}
            <span style={{ color: T.faint }}>الاكتمال {summary.completenessPct}٪</span>
            {summary.historyCount > 0 && (
              <span className="inline-flex items-center gap-1" style={{ color: T.faint }}>
                <GitBranch className="w-3 h-3" aria-hidden="true" /> {summary.historyCount} إصدار تعاقُبيّ
              </span>
            )}
          </div>

          {/* بوّابة الجودة */}
          {(() => {
            const tc = toneColors(gateTone);
            const Icon = summary.qualityGate.passed ? ShieldCheck : ShieldAlert;
            return (
              <div className="flex flex-col gap-1 rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }}>
                <span className="inline-flex items-center gap-1.5 text-[11px] font-bold" style={{ color: T.ink }}>
                  <Icon className="w-3.5 h-3.5" style={{ color: tc.fg }} aria-hidden="true" />
                  بوّابة الجودة:
                  <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold" style={{ color: tc.fg, background: tc.bg }}>
                    {summary.qualityGate.passed ? 'ناجحة' : 'غير ناجحة'}
                  </span>
                  <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold" style={{ color: T.faint, border: `1px solid ${T.line}` }}>
                    {summary.qualityGate.executable ? 'قابلة للتنفيذ' : 'غير قابلة للتنفيذ'}
                  </span>
                </span>
                {summary.qualityGate.reasons.length > 0 &&
                  summary.qualityGate.reasons.map((r) => (
                    <div key={r} className="text-[10px]" style={{ color: '#fdba74' }}>⚠ {r}</div>
                  ))}
                {summary.conflicts.length > 0 &&
                  summary.conflicts.map((c) => (
                    <div key={c} className="text-[10px]" style={{ color: '#fdba74' }}>تعارُض: {c}</div>
                  ))}
              </div>
            );
          })()}

          {/* الاستخدامات المسموحة/المحجوبة */}
          {(summary.allowedUse.length > 0 || summary.blockedUse.length > 0) && (
            <div className="flex flex-col gap-1 rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }}>
              {summary.allowedUse.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[11px] font-bold" style={{ color: T.ink }}>مسموح:</span>
                  {summary.allowedUse.map((u) => (
                    <span key={u} className="text-[10px] px-2 py-0.5 rounded-full font-semibold" style={{ color: T.ok, background: T.okBg }}>{u}</span>
                  ))}
                </div>
              )}
              {summary.blockedUse.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[11px] font-bold" style={{ color: T.ink }}>محجوب حتّى ورود الأدلّة:</span>
                  {summary.blockedUse.map((u) => (
                    <span key={u} className="text-[10px] px-2 py-0.5 rounded-full font-semibold" style={{ color: T.danger, background: T.dangerBg }}>{u}</span>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* عدّادات الحلقة المغلقة */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)', color: T.muted }}>
            <span className="inline-flex items-center gap-1 font-bold" style={{ color: T.ink }}>
              <CircleCheck className="w-3.5 h-3.5 text-emerald-300" aria-hidden="true" /> الحلقة المغلقة:
            </span>
            <span>تنفيذ: <b style={{ color: T.ink }}>{summary.closedLoop.executions}</b> ({summary.closedLoop.completedExecutions} مكتمل · {summary.closedLoop.inProgressExecutions} جارٍ)</span>
            <span>تحقّق: <b style={{ color: T.ink }}>{summary.closedLoop.verifications}</b></span>
            <span>نتائج: <b style={{ color: T.ink }}>{summary.closedLoop.outcomes}</b></span>
            <span>تعلّم: <b style={{ color: T.ink }}>{summary.closedLoop.learning}</b> ({summary.closedLoop.learningEligibleForTraining} مؤهَّل)</span>
          </div>

          <div className="text-[10px]" style={{ color: T.faint }}>
            قراءة فقط من الحلقة المغلقة الكنسيّة — القرار والموافقة يجريان في مركز القرار.
          </div>
        </div>
      )}
    </section>
  );
}
