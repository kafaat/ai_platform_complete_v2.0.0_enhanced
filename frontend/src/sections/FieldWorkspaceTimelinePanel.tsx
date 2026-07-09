import { useQuery } from '@tanstack/react-query';
import { Clock3, RefreshCw } from 'lucide-react';
import { getFieldUnifiedTimeline } from '../services/api/fieldTimeline';
import { EmptyState, ErrorState, LoadingState } from '../components/StateViews';
import { DegradedState } from '../components/product/DegradedState';

function apiStatus(error: unknown): number | undefined {
  return (error as { response?: { status?: number } } | null | undefined)?.response?.status;
}

function TimelineState({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const status = apiStatus(error);
  if (status === 502 || status === 503 || status === 504) {
    return (
      <DegradedState
        title="خط الحقل الزمني يعمل في وضع متدهور"
        detail="مصدر timeline غير متاح حالياً. لا يتم تصنيع أحداث بديلة داخل الواجهة."
        availableActions={['اعرض خريطة الحقل', 'راجع الصور أو العمليات المتاحة', 'أعد المحاولة بعد عودة الخدمة']}
        onRetry={onRetry}
      />
    );
  }
  if (status === 404) return <EmptyState title="خط الحقل الزمني غير مربوط بعد" hint="endpoint غير متاح في هذه البيئة." />;
  if (status === 401 || status === 403) return <ErrorState title="لا تملك صلاحية عرض خط الحقل الزمني" />;
  return <ErrorState title="تعذّر تحميل خط الحقل الزمني" detail="لم تُعرض أحداث بديلة مصطنعة." onRetry={onRetry} />;
}

export default function FieldWorkspaceTimelinePanel({ fieldId, seasonId }: { fieldId: string; seasonId?: string | null }) {
  const query = useQuery({
    queryKey: ['field-workspace', fieldId, seasonId ?? 'no-season', 'unified-timeline'],
    queryFn: () => getFieldUnifiedTimeline(fieldId, { limit: 8, newest_first: true, season_id: seasonId ?? undefined }),
    enabled: Boolean(fieldId),
    staleTime: 60_000,
  });

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5" dir="rtl" aria-label="خط الحقل الزمني">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Clock3 className="h-5 w-5 text-emerald-300" aria-hidden="true" />
          <h2 className="text-base font-bold text-slate-100">خط الحقل الزمني</h2>
        </div>
        <span className="text-xs text-slate-500">field_id + season_id</span>
      </div>

      {query.isLoading && <LoadingState message="جارٍ تحميل خط الحقل الزمني…" />}
      {query.isError && <TimelineState error={query.error} onRetry={() => query.refetch()} />}
      {query.data && (
        <div className="space-y-3">
          {!seasonId && <p className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-100">لا يوجد season_id في الرابط؛ تُعرض أحداث الحقل العامة فقط عند توفرها.</p>}
          {query.data.events?.length ? (
            <ol className="space-y-2">
              {query.data.events.map((event, index) => (
                <li key={event.event_id ?? `${event.event_type ?? 'event'}-${event.occurred_at ?? index}`} className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-slate-100">{event.title_ar ?? event.event_type ?? event.category ?? 'حدث غير مسمى'}</p>
                    {event.occurred_at && <time className="text-xs text-slate-500">{event.occurred_at}</time>}
                  </div>
                  {event.description_ar && <p className="mt-1 text-xs leading-relaxed text-slate-400">{event.description_ar}</p>}
                </li>
              ))}
            </ol>
          ) : (
            <EmptyState title="لا توجد أحداث محفوظة" hint="لا يتم إنشاء أحداث وهمية لملء الخط الزمني." />
          )}
          {query.data.note_ar && <p className="text-xs text-slate-400">{query.data.note_ar}</p>}
        </div>
      )}
    </section>
  );
}
