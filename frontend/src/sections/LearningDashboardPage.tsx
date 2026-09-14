// ═══════════════════════════════════════════════════════════════
// SAHOOL — LearningDashboardPage (لوحة رصد التعلّم / النَّسَب)
// قراءة فقط: لقطة موحّدة لحلقة التعلّم — كم قراراً أُدِيم؟ كم نتيجة؟ ما نسبة
// النجاح؟ وما حالة جمع العيّنات ومراجعة الدليل لكلّ منطقة؟ تستهلك:
//   GET /api/v1/decision/records (سرد القرارات المُدامة)
//   GET /api/v1/calibration/{region}/evidence/persisted (دليل كلّ منطقة)
//   GET /api/v1/learning/summary (تلخيص — أفضل-جهد؛ null إن لم تتوفّر بعد)
// صدق: لا أرقام مُختلَقة. الدليل المتراكم تقديريّ غير مُعايَر (calibrated=false،
// source=persisted_outcomes)؛ اكتمال العدّ لا يمنح اعتماداً أو معايرة.
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
import type { LearningOutcomeReconciliation } from '../services/api';

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
  field_verified:        'مُتحقَّق ميدانيّاً',
  // U01: العتبة بلغت لكن لا مراجعة مختصّ — لا تُعرَض شارة «مُتحقَّق» قبل الاعتماد.
  field_sample_complete: 'عيّنة مكتملة — بانتظار المراجعة',
  field_preliminary:     'ميدانيّ أوّليّ',
  expert_opinion:        'رأي خبير',
  none:                  'لا دليل',
};
const evidenceStyle = (level: string): { bg: string; color: string } => {
  switch (level) {
    case 'field_verified':        return { bg: '#0c2a1a', color: '#4ade80' };
    case 'field_sample_complete': return { bg: '#2a1a00', color: '#fbbf24' };
    case 'field_preliminary':     return { bg: '#2a1a00', color: '#fbbf24' };
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
    <div role="group" aria-label={label} className="rounded-xl border p-4 space-y-1" style={{ background: '#1e293b', borderColor: '#334155' }}>
      <div className="flex items-center gap-2 text-[11px] text-slate-400">
        {icon}{label}
      </div>
      <div className="text-2xl font-bold text-slate-100">{value}</div>
      {sub && <div className="text-[11px] text-slate-500">{sub}</div>}
    </div>
  );
}

function displayCount(count: number | null | undefined): string {
  return typeof count === 'number' && Number.isSafeInteger(count) && count >= 0 ? String(count) : '—';
}

function OutcomeCounts({ reconciliation }: { reconciliation?: LearningOutcomeReconciliation | null }) {
  const counts = reconciliation?.enabled === false ? undefined : reconciliation;
  const items = [
    { label: 'الحالات بحسب الربط المتاح', value: counts?.independent_case_count },
    { label: 'صفوف النتائج', value: counts?.total },
    { label: 'صفوف أثر القرار', value: counts?.rows_by_source?.outcome_record },
    { label: 'صفوف تعلّم الغلة', value: counts?.rows_by_source?.recommendation_outcomes },
  ];
  return (
    <section aria-labelledby="outcome-counts-title" className="rounded-xl border p-4 space-y-3"
      style={{ background: '#1e293b', borderColor: '#334155' }}>
      <h3 id="outcome-counts-title" className="text-base font-bold text-slate-100">الحالات ومصادر النتائج</h3>
      <dl className="grid grid-cols-2 gap-3">
        {items.map(({ label, value }) => (
          <div key={label}>
            <dt className="text-[11px] text-slate-400">{label}</dt>
            <dd className="text-xl font-bold text-slate-100">{displayCount(value)}</dd>
          </div>
        ))}
      </dl>
      <p className="text-[11px] text-slate-300">
        {counts?.sample_count_basis === 'rows' ? 'أساس عدّ العينات: صفوف النتائج' : 'أساس عدّ العينات: غير متاح'}
      </p>
      <p className="text-[11px] text-slate-400">
        تُجمع الصفوف المرتبطة بالقرار نفسه في حالة واحدة، ويُعدّ كل صف غير مرتبط حالةً.
        هذا العدّ لا يثبت استقلال الحقول أو المزارع ولا فعالية الممارسة.
        قد تشمل صفوف النتائج سجلات لم تكتمل بعد؛ عيّنات الدليل تتطلب قياساً مؤهّلاً.
      </p>
    </section>
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
    <section aria-label={`دليل ${regionAr}`} className="rounded-xl border p-4 space-y-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
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

          {/* عتبة جمع تقديريّة؛ الاسم القديم في API لا يجعلها عتبة اعتماد. */}
          <div className="space-y-1">
            <div className="flex items-center justify-between text-[11px] text-slate-400">
              <span>اكتمال جمع العيّنات</span>
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
                تبقّى {ev.samples_to_verified} عيّنة لبلوغ عتبة الجمع.
              </div>
            )}
          </div>

          {/* U01: جودة الدليل لا عدُّه — حالة المراجعة وأعداد الوحدات المستقلّة (حقول/مواسم/
              مزارع) والعيّنات مجهولة الوحدة. 30 صفّاً من حقلٍ واحد ليست 30 شاهداً. */}
          <div className="rounded-lg border p-2.5 space-y-1" style={{ background: '#0f172a', borderColor: '#334155' }}
            data-testid={`evidence-quality-${region}`}>
            <div className="flex items-center justify-between text-[11px]">
              <span className="text-slate-400">حالة المراجعة</span>
              <span className="font-semibold"
                style={{ color: ev.review_status === 'reviewed' ? '#4ade80' : '#fbbf24' }}>
                {ev.review_status === 'reviewed' ? 'مراجَعة من مختصّ'
                  : ev.review_status === 'unreviewed' ? 'غير مراجَعة' : '—'}
              </span>
            </div>
            <div className="flex items-center justify-between text-[11px]">
              <span className="text-slate-400">معرّفات مميّزة (حقول / مواسم / مزارع / مستأجرون)</span>
              <span className="text-slate-200 font-medium" dir="ltr">
                {ev.independence
                  ? `${ev.independence.fields} / ${ev.independence.seasons} / ${ev.independence.farms} / ${ev.independence.tenants}`
                  : '—'}
              </span>
            </div>
            <p className="text-[10px] text-slate-400">
              هذا العدّ لا يكشف النقص في كلّ معرّف على حدة، ولا يثبت استقلال الشواهد.
            </p>
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
    </section>
  );
}

export default function LearningDashboardPage() {
  const records = useDecisionRecords();
  const learning = useLearningSummary();

  // الإجماليّات من ملخّص الخادم؛ لا تُستنتج الحالات من عدد الصفوف.
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
  // العقد الحاليّ يضع الإجماليّ تحت `overall` (كانت تُقرأ من الجذر فتظهر «—» على بيانات
  // موجودة — Copilot على #1001)، والمناطقُ المُتحقَّقة تُعدّ من بطاقات المناطق نفسها.
  const outcomeCount = summary?.overall?.outcome_count ?? null;
  const successRate = summary?.overall?.success_rate ?? null;
  const regionsVerified = summary?.regions
    ? summary.regions.filter((r) => r.evidence_level === 'field_verified').length
    : null;

  const isLoading = records.isLoading || learning.isLoading;
  const recordsDegraded = Boolean(records.data?.degraded);
  // الخطأ الحاجب الوحيد هو فشل صلاحيّة/مصادقة أو خطأ غير قابل للتدهور.
  // تعطل read-side لخدمة القرار يُعرض كـdegraded empty state لا كفشل صفحة.
  const isError = records.isError && !recordsDegraded;

  return (
    <div className="space-y-6 max-w-5xl mx-auto" dir="rtl">
      <div className="flex items-center gap-2">
        <BarChart3 className="w-5 h-5 text-emerald-400" />
        <h2 className="text-xl font-bold text-slate-100">لوحة رصد التعلّم والنَّسَب</h2>
      </div>
      <p className="text-sm text-slate-400">
        تعرّف على القرارات والنتائج المسجّلة، واكتمال جمع العيّنات وحالة مراجعتها في كلّ منطقة.
        اكتمال العيّنة يختلف عن الاعتماد الزراعي والمعايرة؛ عدد السجلات وحده لا يثبت فعالية الممارسة.
      </p>

      {isLoading && <LoadingState message="جارٍ جلب لقطة التعلّم…" />}
      {isError && (
        <ErrorState title="تعذّر جلب سجلّ القرارات المُدامة"
          detail="قد تكون المشكلة صلاحيّة عرض أو خطأ غير قابل للتدهور. أما تعطل خدمة القرار فيُعرض كحالة متدهورة صادقة."
          onRetry={() => records.refetch()} />
      )}

      {!isLoading && !isError && recordsDegraded && (
        <div className="rounded-xl border p-4 flex items-start gap-3" style={{ background: '#1a1400', borderColor: '#f59e0b33' }}>
          <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
          <div className="space-y-1 text-[12px]">
            <div className="text-sm font-semibold text-amber-200">
              تعمل اللوحة في وضع متدهور
            </div>
            <div className="text-amber-300/80">
              {records.data?.warning_ar ?? 'تعذّر جلب سجلّ القرارات المُدامة حالياً. لا تُعرض أرقام مُلفّقة، ويمكن متابعة بقية الصفحة عند توفر البيانات.'}
            </div>
            {records.data?.status_code && (
              <div className="text-[11px] text-slate-500">status={records.data.status_code} · source={records.data?.source ?? 'decision-service'}</div>
            )}
          </div>
        </div>
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
              label="سجلات النتائج"
              value={outcomeCount != null ? String(outcomeCount) : '—'}
              sub={outcomeCount != null ? 'تشمل النتائج المكتملة وغير المكتملة' : 'تلخيص التعلّم غير متاح بعد'} />
            <StatCard
              icon={<Activity className="w-3.5 h-3.5 text-emerald-400" />}
              label="مؤشر نجاح الصفوف المحسومة"
              value={successRate != null ? `${(successRate * 100).toFixed(0)}%` : '—'}
              sub={successRate == null ? 'بلا بيانات كافية بعد'
                : summary?.outcome_reconciliation?.enabled === true
                  ? 'يجمع صفوف أثر القرار وتعلّم الغلة المتاحة؛ لا يثبت فعالية ممارسة أو استقلال الحالات'
                  : 'مؤشر وصفي للصفوف؛ لا يثبت فعالية الممارسة أو استقلال الحالات'} />
            <StatCard
              icon={<FlaskConical className="w-3.5 h-3.5 text-emerald-400" />}
              label="مناطق متحقّقة ميدانياً"
              value={displayCount(regionsVerified)}
              sub="بحسب مستوى الدليل الوارد في الملخّص" />
          </section>

          <OutcomeCounts reconciliation={summary?.outcome_reconciliation} />

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

          {/* ═══════════ جمع العيّنات ومراجعة الدليل ═══════════ */}
          <section className="space-y-3">
            <div className="flex items-center gap-2">
              <FlaskConical className="w-4 h-4 text-emerald-400" />
              <h3 className="text-base font-bold text-slate-100">جمع العيّنات ومراجعة الدليل حسب المنطقة</h3>
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
