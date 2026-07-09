import { useQuery } from '@tanstack/react-query';
import { ListChecks } from 'lucide-react';
import { getFieldPriorityQueue } from '../services/api/fieldOperating';
import { EmptyState, ErrorState, LoadingState } from '../components/StateViews';
import { DegradedState } from '../components/product/DegradedState';

function apiStatus(error: unknown): number | undefined {
  return (error as { response?: { status?: number } } | null | undefined)?.response?.status;
}

function PriorityState({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const status = apiStatus(error);
  if (status === 502 || status === 503 || status === 504) {
    return <DegradedState title="أولوية الحقل تعمل في وضع متدهور" detail="مصدر ترتيب الأولويات غير متاح. لا يتم ترتيب عناصر مصطنعة." onRetry={onRetry} />;
  }
  if (status === 404) return <EmptyState title="أولوية الحقل غير مربوطة بعد" hint="endpoint غير متاح في هذه البيئة." />;
  if (status === 401 || status === 403) return <ErrorState title="لا تملك صلاحية عرض أولوية الحقل" />;
  return <ErrorState title="تعذّر تحميل أولوية الحقل" detail="لم يتم عرض أولويات بديلة غير موثقة." onRetry={onRetry} />;
}

export default function FieldWorkspacePriorityPanel({ fieldId }: { fieldId: string }) {
  const query = useQuery({
    queryKey: ['field-workspace', fieldId, 'priority-queue'],
    queryFn: () => getFieldPriorityQueue(fieldId),
    enabled: Boolean(fieldId),
    staleTime: 60_000,
  });

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5" dir="rtl" aria-label="أولوية الحقل">
      <div className="mb-4 flex items-center gap-2">
        <ListChecks className="h-5 w-5 text-emerald-300" aria-hidden="true" />
        <h2 className="text-base font-bold text-slate-100">أولوية الحقل</h2>
      </div>

      {query.isLoading && <LoadingState message="جارٍ تحميل أولوية الحقل…" />}
      {query.isError && <PriorityState error={query.error} onRetry={() => query.refetch()} />}
      {query.data && (
        <div className="space-y-3">
          {query.data.degraded && <DegradedState title="أولوية الحقل متدهورة" detail={query.data.warning_ar ?? 'الخادم أعاد حالة متدهورة.'} />}
          {query.data.items?.length ? (
            <ol className="space-y-2">
              {query.data.items.map((item) => (
                <li key={item.id} className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-slate-100">{item.title_ar}</p>
                    {item.severity && <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-400">{item.severity}</span>}
                  </div>
                  {item.reasons?.length ? <p className="mt-1 text-xs text-slate-400">{item.reasons.join(' · ')}</p> : null}
                </li>
              ))}
            </ol>
          ) : (
            <EmptyState title="لا توجد أولويات محفوظة" hint="لا يتم إنشاء قائمة أولويات وهمية داخل مساحة العمل." />
          )}
        </div>
      )}
    </section>
  );
}
