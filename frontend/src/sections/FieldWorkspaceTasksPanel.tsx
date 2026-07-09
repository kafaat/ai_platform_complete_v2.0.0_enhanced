import { useQuery } from '@tanstack/react-query';
import { ClipboardList } from 'lucide-react';
import { getFieldTasks, type FieldTaskSummary } from '../services/api/fieldTasks';
import { EmptyState, ErrorState, LoadingState } from '../components/StateViews';
import { DegradedState } from '../components/product/DegradedState';

function apiStatus(error: unknown): number | undefined {
  return (error as { response?: { status?: number } } | null | undefined)?.response?.status;
}

function TaskState({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const status = apiStatus(error);
  if (status === 502 || status === 503 || status === 504) {
    return <DegradedState title="مهام الحقل تعمل في وضع متدهور" detail="خدمة المهام أو قاعدة البيانات غير متاحة. لا يتم إنشاء مهام بديلة." onRetry={onRetry} />;
  }
  if (status === 404) return <EmptyState title="مهام الحقل غير مربوطة بعد" hint="endpoint /api/v1/tasks غير متاح في هذه البيئة." />;
  if (status === 401 || status === 403) return <ErrorState title="لا تملك صلاحية عرض مهام الحقل" />;
  return <ErrorState title="تعذّر تحميل مهام الحقل" detail="لم يتم عرض مهام افتراضية غير موثقة." onRetry={onRetry} />;
}

function taskKey(task: FieldTaskSummary, index: number) {
  return String(task.task_id ?? task.id ?? `${task.field_id ?? 'field'}-${index}`);
}

function taskTitle(task: FieldTaskSummary) {
  return String(task.title_ar ?? task.title ?? 'مهمة بدون عنوان محفوظ');
}

export default function FieldWorkspaceTasksPanel({ fieldId }: { fieldId: string }) {
  const query = useQuery({
    queryKey: ['field-workspace', fieldId, 'tasks'],
    queryFn: () => getFieldTasks(fieldId),
    enabled: Boolean(fieldId),
    staleTime: 60_000,
  });

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5" dir="rtl" aria-label="مهام الحقل">
      <div className="mb-4 flex items-center gap-2">
        <ClipboardList className="h-5 w-5 text-emerald-300" aria-hidden="true" />
        <h2 className="text-base font-bold text-slate-100">مهام الحقل</h2>
      </div>

      {query.isLoading && <LoadingState message="جارٍ تحميل مهام الحقل…" />}
      {query.isError && <TaskState error={query.error} onRetry={() => query.refetch()} />}
      {query.data && (
        <div className="space-y-3">
          {query.data.degraded && <DegradedState title="مهام الحقل متدهورة" detail={query.data.warning_ar ?? 'الخادم أعاد حالة متدهورة.'} />}
          {query.data.tasks?.length ? (
            <ol className="space-y-2">
              {query.data.tasks.map((task, index) => (
                <li key={taskKey(task, index)} className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-slate-100">{taskTitle(task)}</p>
                    {task.status && <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-400">{String(task.status)}</span>}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-2 text-xs text-slate-500">
                    {task.priority !== undefined && <span>priority: {String(task.priority)}</span>}
                    {(task.recommended_date || task.due_at) && <span>date: {String(task.recommended_date ?? task.due_at)}</span>}
                  </div>
                  {task.description_ar && <p className="mt-1 text-xs text-slate-400">{String(task.description_ar)}</p>}
                </li>
              ))}
            </ol>
          ) : (
            <EmptyState title="لا توجد مهام محفوظة" hint="لا يتم إنشاء مهام وهمية داخل مساحة العمل." />
          )}
        </div>
      )}
    </section>
  );
}
