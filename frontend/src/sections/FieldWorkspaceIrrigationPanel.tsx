import { useQuery } from '@tanstack/react-query';
import { Droplets, Timer } from 'lucide-react';
import { getFieldIrrigationAdvice, getFieldIrrigationSchedules } from '../services/api/fieldIrrigation';
import { EmptyState, ErrorState, LoadingState } from '../components/StateViews';
import { DegradedState } from '../components/product/DegradedState';

function apiStatus(error: unknown): number | undefined {
  return (error as { response?: { status?: number } } | null | undefined)?.response?.status;
}

function IrrigationState({ title, error, onRetry }: { title: string; error: unknown; onRetry: () => void }) {
  const status = apiStatus(error);
  if (status === 502 || status === 503 || status === 504) return <DegradedState title={`${title} يعمل في وضع متدهور`} detail="خدمة الري أو الطقس غير متاحة. لا يتم حساب بدائل من الواجهة." onRetry={onRetry} />;
  if (status === 404) return <EmptyState title={`${title} غير مربوط بعد`} hint="endpoint الري غير متاح في هذه البيئة." />;
  if (status === 401 || status === 403) return <ErrorState title="لا تملك صلاحية عرض بيانات الري" />;
  return <ErrorState title={`تعذّر تحميل ${title}`} detail="لا تعرض الواجهة خطة ري مصطنعة." onRetry={onRetry} />;
}

export default function FieldWorkspaceIrrigationPanel({ fieldId, seasonId }: { fieldId: string; seasonId?: string | null }) {
  const adviceQ = useQuery({
    queryKey: ['field-workspace', fieldId, seasonId, 'irrigation-advice'],
    queryFn: () => getFieldIrrigationAdvice(fieldId),
    enabled: Boolean(fieldId && seasonId),
    staleTime: 60_000,
  });
  const schedulesQ = useQuery({
    queryKey: ['field-workspace', fieldId, 'irrigation-schedules'],
    queryFn: () => getFieldIrrigationSchedules(fieldId),
    enabled: Boolean(fieldId),
    staleTime: 60_000,
  });

  if (!seasonId) {
    return <EmptyState title="لا يوجد موسم نشط للري" hint="تبويب الري لا يحسب توصيات خارج سياق crop stage/season_id." />;
  }

  return (
    <section className="grid gap-4 xl:grid-cols-2" dir="rtl" aria-label="ري الحقل">
      <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5">
        <div className="mb-4 flex items-center gap-2"><Droplets className="h-5 w-5 text-emerald-300" /><h2 className="text-base font-bold text-slate-100">نصيحة الري</h2></div>
        {adviceQ.isLoading && <LoadingState message="جارٍ تحميل نصيحة الري…" />}
        {adviceQ.isError && <IrrigationState title="نصيحة الري" error={adviceQ.error} onRetry={() => adviceQ.refetch()} />}
        {adviceQ.data && <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
          <div className="flex flex-wrap items-end gap-3"><p className="text-3xl font-bold text-slate-100">{typeof adviceQ.data.recommended_mm === 'number' ? adviceQ.data.recommended_mm : '—'}</p><span className="mb-1 text-xs text-slate-500">mm</span>{adviceQ.data.urgency && <span className="mb-1 rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-400">{adviceQ.data.urgency}</span>}</div>
          <p className="mt-2 text-sm text-slate-300">{adviceQ.data.timing_ar ?? 'لا يوجد توقيت محفوظ من الخادم.'}</p>
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">{typeof adviceQ.data.et0 === 'number' && <span>ET0: {adviceQ.data.et0}</span>}{typeof adviceQ.data.kc === 'number' && <span>Kc: {adviceQ.data.kc}</span>}{adviceQ.data.stage && <span>stage: {adviceQ.data.stage}</span>}</div>
          {adviceQ.data.rationale_ar && <p className="mt-2 text-xs leading-relaxed text-slate-400">{adviceQ.data.rationale_ar}</p>}
        </div>}
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5">
        <div className="mb-4 flex items-center gap-2"><Timer className="h-5 w-5 text-emerald-300" /><h2 className="text-base font-bold text-slate-100">جداول الري المحفوظة</h2></div>
        {schedulesQ.isLoading && <LoadingState message="جارٍ تحميل جداول الري…" />}
        {schedulesQ.isError && <IrrigationState title="جداول الري" error={schedulesQ.error} onRetry={() => schedulesQ.refetch()} />}
        {schedulesQ.data && (schedulesQ.data.length ? <ol className="space-y-2">{schedulesQ.data.map(s => <li key={s.schedule_id} className="rounded-xl border border-slate-800 bg-slate-950/50 p-3"><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-semibold text-slate-100">{s.name}</p><span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-400">{s.enabled ? 'enabled' : 'disabled'}</span></div><p className="mt-1 text-xs text-slate-500">{s.start_time} · {s.duration_min} دقيقة{typeof s.water_target_mm === 'number' ? ` · ${s.water_target_mm}mm` : ''}</p></li>)}</ol> : <EmptyState title="لا توجد جداول ري محفوظة" hint="لا يتم توليد جدول ري من الواجهة." />)}
      </div>
    </section>
  );
}
