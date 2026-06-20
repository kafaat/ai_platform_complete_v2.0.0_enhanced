// ═══════════════════════════════════════════════════════════════
// SAHOOL — LearningDashboardPage (لوحة رصد التعلّم / النَّسَب)
// قراءة فقط: لقطة موحّدة لحلقة التعلّم — كم قراراً أُدِيم؟ كم نتيجة؟ ما نسبة
// النجاح؟ وأين تقف كلّ منطقة يمنيّة نحو «مُتحقَّق ميدانيّاً»؟ تستهلك:
//   GET /api/v1/decision/records (سرد القرارات المُدامة)
//   GET /api/v1/calibration/{region}/evidence/persisted (دليل كلّ منطقة)
//   GET /api/v1/learning/summary (تلخيص — أفضل-جهد؛ null إن لم تتوفّر بعد)
// صدق: لا أرقام مُختلَقة. الدليل المتراكم تقديريّ غير مُعايَر (calibrated=false،
// source=persisted_outcomes) حتى تُجمَع عيّنات كافية — تُبرَز warnings_ar صراحةً.
// غياب البيانات/النقطة ⇒ حالة فارغة صادقة لا تلفيق.
// (يطابق أنماط LineagePage/CalibrationPage بصريّاً ولونيّاً.)
// ═══════════════════════════════════════════════════════════════
import {
  Activity, BarChart3, GitBranch, AlertTriangle, CheckCircle2,
  FlaskConical, MapPin,
} from 'lucide-react';
import {
  useDecisionRecords, usePersistedEvidence, useLearningSummary,
} from '../hooks/useApi';
import { ErrorState, LoadingState, EmptyState } from '../components/StateViews';

// المناطق اليمنيّة المدعومة (يطابق نصّ المهمّة وLineagePage).
const REGIONS: { id: string; ar: string }[] = [
  { id: 'jawf',      ar: 'الجوف' },
  { id: 'tihama',    ar: 'تهامة' },
  { id: 'marib',     ar: 'مأرب' },
  { id: 'hadramout', ar: 'حضرموت' },
  { id: 'ibb',       ar: 'إبّ' },
];

// شارة مستوى الدليل — نفس ألوان CalibrationPage/LineagePage (تناسق بصريّ).
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

// بطاقة إجماليّة واحدة (مقياس + تسمية + أيقونة).
function StatCard({
  icon, label, value, sub,
}: { icon: React.ReactNode; label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border p-4 space-y-1" style={{ background: '#1e293b', borderColor: '#334155' }}>
      <div className="flex items-center gap-2 text-[11px] text-slate-400">
        {icon}{label}
      </div>
      <div className="text-2xl font-bold text-slate-100">{value}</div>
      {sub && <div className="text-[11px] text-slate-500">{sub}</div>}
    </div>
  );
}

// بطاقة تقدّم منطقة — تستهلك usePersistedEvidence لكلّ منطقة على حدة (قائمة ثابتة
// الترتيب ⇒ آمن لقواعد الـHooks). تُبرز calibrated=false + warnings_ar صراحةً.
function RegionEvidenceCard({ region, regionAr }: { region: string; regionAr: string }) {
  const { data: ev, isLoading, isError } = usePersistedEvidence(region);

  const evStyle = ev ? evidenceStyle(ev.evidence_level) : null;
  const progressPct = ev && ev.field_verified_min_samples > 0
    ? Math.min(100, Math.round((ev.sample_count / ev.field_verified_min_samples) * 100))
    : 0;

  return (
    <div className="rounded-xl border p-4 space-y-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <MapPin className="w-4 h-4 text-emerald-400" />
          <span className="text-sm font-bold text-slate-100">{regionAr}</span>
        </div>
        {ev && evStyle && (
          <span className="text-[11px] px-2 py-0.5 rounded-full font-semibold"
            style={{ background: evStyle.bg, color: evStyle.color }}>
            {EVIDENCE_AR[ev.evidence_level] ?? ev.evidence_level}
          </span>
        )}
      </div>

      {isLoading && (
        <div className="text-[11px] text-slate-500">جارٍ جلب الدليل المتراكم…</div>
      )}
      {isError && (
        <div className="text-[11px] text-amber-300/80 flex items-center gap-1.5">
          <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
          تعذّر جلب الدليل لهذه المنطقة (حالة صادقة، لا أرقام مُلفَّقة).
        </div>
      )}

      {ev && evStyle && (
        <>
          {/* معدّل النجاح */}
          <div className="text-sm text-slate-300">
            معدّل النجاح: <span className="font-bold text-slate-100">
              {ev.success_rate != null ? `${(ev.success_rate * 100).toFixed(0)}%` : '—'}
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

          {/* إبراز صريح: غير مُعايَر (calibrated=false) + warnings_ar */}
          {!ev.calibrated && (
            <div className="rounded-lg border p-2.5 space-y-1" style={{ background: '#1a1400', borderColor: '#f59e0b33' }}>
              <div className="text-[11px] font-semibold text-amber-200 flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                🟡 تقديريّ غير مُعايَر (calibrated = false)
              </div>
              {ev.warnings_ar.map((w, i) => (
                <div key={i} className="text-[10px] text-slate-400">• {w}</div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function LearningDashboardPage() {
  const records = useDecisionRecords();
  const learning = useLearningSummary();

  // إجماليّات الدليل المُجمَّعة من بطاقات المناطق (تُملأ عبر onEvidence).
  // نستخدم كائناً عاديّاً عبر ref-like state بسيط: نُجمّع من learning.summary إن
  // توفّرت (مصدر موحّد)، وإلّا نعتمد على قرارات السرد + بطاقات المناطق.
  const summary = learning.data ?? null;

  // عدد القرارات المُدامة — من سرد القرارات (مصدر مُثبَّت في هذا الفرع).
  const decisionCount = records.data?.count ?? null;

  // اشتقاق توزيع القرارات حسب المنطقة (صادق: من السرد الفعليّ، لا تلفيق).
  const byRegion: Record<string, number> = {};
  for (const d of records.data?.decisions ?? []) {
    const r = (d.region || 'غير محدّد').trim() || 'غير محدّد';
    byRegion[r] = (byRegion[r] ?? 0) + 1;
  }

  // النتائج/نسبة النجاح/المناطق المُتحقَّقة — من learning/summary إن توفّرت فقط
  // (لا نُلفّق هذه الأرقام من سرد القرارات وحده، فهو لا يحمل النتائج). null ⇒ «—».
  const outcomeCount = summary?.outcome_count ?? null;
  const successRate = summary?.success_rate ?? null;
  const regionsVerified = summary?.regions_verified ?? null;

  const isLoading = records.isLoading || learning.isLoading;
  // الخطأ الحاجب الوحيد هو فشل سرد القرارات (المصدر المُثبَّت)؛ learning أفضل-جهد (null).
  const isError = records.isError;

  return (
    <div className="space-y-6 max-w-5xl mx-auto" dir="rtl">
      <div className="flex items-center gap-2">
        <BarChart3 className="w-5 h-5 text-emerald-400" />
        <h2 className="text-xl font-bold text-slate-100">لوحة رصد التعلّم والنَّسَب</h2>
      </div>
      <p className="text-sm text-slate-400">
        لقطة موحّدة لحلقة التعلّم: كم قراراً أُدِيم وأين، وتقدّم كلّ منطقة يمنيّة نحو
        <span className="text-emerald-300"> التحقّق الميدانيّ</span>. صدق: الدليل المتراكم
        <span className="text-amber-300"> تقديريّ غير مُعايَر</span> (calibrated=false) حتى تُجمَع عيّنات كافية —
        لا أرقام قاطعة مُلفَّقة، والفراغ يُعرَض حالةً صادقة.
      </p>

      {isLoading && <LoadingState message="جارٍ جلب لقطة التعلّم…" />}
      {isError && (
        <ErrorState title="تعذّر جلب سجلّ القرارات المُدامة"
          detail="قد تكون قاعدة البيانات غير متاحة (503) أو لا صلاحيّة عرض."
          onRetry={() => records.refetch()} />
      )}

      {!isLoading && !isError && (
        <div className="space-y-6">
          {/* ═══════════ بطاقات إجماليّة ═══════════ */}
          <section className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard
              icon={<GitBranch className="w-3.5 h-3.5 text-emerald-400" />}
              label="قرارات مُدامة"
              value={decisionCount != null ? String(decisionCount) : '—'}
              sub="إجماليّ سجلّ القرارات (decision_record)" />
            <StatCard
              icon={<CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />}
              label="نتائج مقيسة"
              value={outcomeCount != null ? String(outcomeCount) : '—'}
              sub={outcomeCount != null ? 'من تلخيص حلقة التعلّم' : 'تلخيص التعلّم غير متاح بعد'} />
            <StatCard
              icon={<Activity className="w-3.5 h-3.5 text-emerald-400" />}
              label="نسبة النجاح"
              value={successRate != null ? `${(successRate * 100).toFixed(0)}%` : '—'}
              sub={successRate != null ? 'تقديريّ غير مُعايَر' : 'بلا بيانات كافية بعد'} />
            <StatCard
              icon={<FlaskConical className="w-3.5 h-3.5 text-emerald-400" />}
              label="مناطق نحو التحقّق"
              value={regionsVerified != null ? `${regionsVerified} / ${REGIONS.length}` : `0 / ${REGIONS.length}`}
              sub="مُتحقَّق ميدانيّاً (field_verified)" />
          </section>

          {/* بانر الصدق العامّ */}
          <div className="rounded-xl border p-4 flex items-start gap-3" style={{ background: '#1a1400', borderColor: '#f59e0b33' }}>
            <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
            <div className="space-y-1 text-[12px]">
              <div className="text-sm font-semibold text-amber-200">
                🟡 حلقة التعلّم قيد التراكم — قيم تقديريّة غير مُعايَرة
              </div>
              <div className="text-amber-300/80">
                الدليل لكلّ منطقة مُشتقّ من النتائج المُدامة (source=persisted_outcomes)، ويحتاج
                معايرة ميدانيّة قبل اعتماده قاطعاً. النتائج/نسبة النجاح تظهر فقط حين يوفّرها
                تلخيص التعلّم؛ وإلّا تُعرَض «—» بصدق (لا تلفيق).
              </div>
              {(summary?.warnings_ar ?? []).map((w, i) => (
                <div key={i} className="text-[11px] text-slate-400">• {w}</div>
              ))}
            </div>
          </div>

          {/* توزيع القرارات حسب المنطقة (من السرد الفعليّ) */}
          {Object.keys(byRegion).length > 0 && (
            <section className="rounded-xl border p-4" style={{ background: '#1e293b', borderColor: '#334155' }}>
              <div className="text-[11px] text-slate-400 mb-2">توزيع القرارات المُدامة حسب المنطقة</div>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(byRegion).map(([region, n]) => (
                  <span key={region} className="text-[11px] px-2 py-0.5 rounded-full"
                    style={{ background: '#0f1117', color: '#cbd5e1', border: '1px solid #25303f' }}>
                    {region}: <span className="font-semibold">{n}</span>
                  </span>
                ))}
              </div>
            </section>
          )}

          {/* حالة فارغة صادقة: لا قرارات مُدامة بعد (علم الإدامة قد يكون مُطفأً) */}
          {decisionCount === 0 && (
            <EmptyState
              icon={<GitBranch className="w-8 h-8" />}
              title="لا قرارات مُدامة بعد"
              hint="إدامة القرارات قد تكون مُطفأة (SAHOOL_AUTO_PERSIST_DECISIONS)، أو لم تُتّخذ قرارات بعد. لا أرقام مُختلَقة — تُعرَض الحالة كما هي." />
          )}

          {/* ═══════════ تقدّم المناطق نحو التحقّق ═══════════ */}
          <section className="space-y-3">
            <div className="flex items-center gap-2">
              <FlaskConical className="w-4 h-4 text-emerald-400" />
              <h3 className="text-base font-bold text-slate-100">تقدّم المناطق نحو التحقّق الميدانيّ</h3>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {REGIONS.map(r => (
                <RegionEvidenceCard key={r.id} region={r.id} regionAr={r.ar} />
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
