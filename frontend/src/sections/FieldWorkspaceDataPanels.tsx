import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, CircleAlert, CircleDotDashed, Database, Gauge, RefreshCw } from 'lucide-react';
import { getFieldDataCompleteness, getFieldReadiness, type CompletenessStatus, type FieldReadinessItem } from '../services/api/fieldOperating';
import { EmptyState, ErrorState, LoadingState } from '../components/StateViews';
import { DegradedState } from '../components/product/DegradedState';

function apiStatus(error: unknown): number | undefined {
  return (error as { response?: { status?: number } } | null | undefined)?.response?.status;
}

function FieldWorkspaceServiceState({
  title,
  error,
  onRetry,
}: {
  title: string;
  error: unknown;
  onRetry: () => void;
}) {
  const status = apiStatus(error);
  if (status === 502 || status === 503 || status === 504) {
    return (
      <DegradedState
        title={`${title} تعمل في وضع متدهور`}
        detail="الخدمة الخلفية غير متاحة حالياً. لا تعرض مساحة العمل قيماً بديلة أو تقديرات مصطنعة."
        availableActions={['اعرض الخريطة والطبقات المتاحة', 'أعد المحاولة بعد عودة الخدمة', 'راجع readiness من مصدرها الخلفي']}
        onRetry={onRetry}
      />
    );
  }

  if (status === 404) {
    return <EmptyState title={`${title} غير مربوطة بعد`} hint="العقد موجود في الواجهة لكن endpoint غير متاح في هذه البيئة." />;
  }

  if (status === 401 || status === 403) {
    return <ErrorState title="لا تملك صلاحية عرض هذه البيانات" detail="راجع الدور أو المستأجر قبل إعادة المحاولة." />;
  }

  return <ErrorState title={`تعذّر تحميل ${title}`} detail="لم يتم استخدام fallback وهمي. أعد المحاولة أو راجع السجلات." onRetry={onRetry} />;
}

const STATUS_LABELS: Record<CompletenessStatus, string> = {
  complete: 'مكتمل',
  partial: 'جزئي',
  missing: 'ناقص',
  unknown: 'غير معروف',
  stale: 'قديم',
};

function statusIcon(status: CompletenessStatus) {
  if (status === 'complete') return <CheckCircle2 className="h-4 w-4 text-emerald-400" aria-hidden="true" />;
  if (status === 'partial' || status === 'stale') return <CircleDotDashed className="h-4 w-4 text-amber-300" aria-hidden="true" />;
  return <CircleAlert className="h-4 w-4 text-slate-500" aria-hidden="true" />;
}

function ReadinessItemRow({ item }: { item: FieldReadinessItem }) {
  return (
    <li className="flex items-start gap-2 rounded-xl border border-slate-800 bg-slate-950/50 p-3">
      <span className="mt-0.5">{statusIcon(item.status)}</span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-slate-100">{item.label_ar ?? item.key}</span>
          <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-400">{STATUS_LABELS[item.status] ?? item.status}</span>
        </div>
        {item.reason_ar && <p className="mt-1 text-xs leading-relaxed text-slate-400">{item.reason_ar}</p>}
      </div>
    </li>
  );
}

export function FieldReadinessPanel({ fieldId }: { fieldId: string }) {
  const query = useQuery({
    queryKey: ['field-workspace', fieldId, 'readiness'],
    queryFn: () => getFieldReadiness(fieldId),
    enabled: Boolean(fieldId),
    staleTime: 60_000,
  });

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5" dir="rtl" aria-label="جاهزية الحقل">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Gauge className="h-5 w-5 text-emerald-300" aria-hidden="true" />
          <h2 className="text-base font-bold text-slate-100">جاهزية الحقل</h2>
        </div>
        {query.data?.calibrated === false && <span className="rounded-full border border-amber-500/40 px-2 py-1 text-xs text-amber-200">غير معايرة</span>}
      </div>

      {query.isLoading && <LoadingState message="جارٍ تحميل جاهزية الحقل…" />}
      {query.isError && <FieldWorkspaceServiceState title="جاهزية الحقل" error={query.error} onRetry={() => query.refetch()} />}
      {query.data && (
        <div className="space-y-4">
          <div>
            <p className="text-3xl font-bold text-slate-100">{Number.isFinite(query.data.score) ? query.data.score : '—'}</p>
            <p className="text-xs text-slate-500">درجة اكتمال تشغيلية وليست حكماً طبياً على المحصول.</p>
          </div>
          {query.data.items?.length > 0 ? (
            <ul className="grid gap-2 md:grid-cols-2">
              {query.data.items.map((item) => <ReadinessItemRow key={`${item.key}-${item.status}`} item={item} />)}
            </ul>
          ) : (
            <EmptyState title="لا توجد عناصر جاهزية" hint="الخادم لم يرجع items قابلة للعرض." />
          )}
          {query.data.note_ar && <p className="text-xs leading-relaxed text-slate-400">{query.data.note_ar}</p>}
        </div>
      )}
    </section>
  );
}

export function FieldDataCompletenessPanel({ fieldId }: { fieldId: string }) {
  const query = useQuery({
    queryKey: ['field-workspace', fieldId, 'data-completeness'],
    queryFn: () => getFieldDataCompleteness(fieldId),
    enabled: Boolean(fieldId),
    staleTime: 60_000,
  });

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5" dir="rtl" aria-label="اكتمال بيانات الحقل">
      <div className="mb-4 flex items-center gap-2">
        <Database className="h-5 w-5 text-emerald-300" aria-hidden="true" />
        <h2 className="text-base font-bold text-slate-100">اكتمال البيانات</h2>
      </div>

      {query.isLoading && <LoadingState message="جارٍ تحميل اكتمال البيانات…" />}
      {query.isError && <FieldWorkspaceServiceState title="اكتمال البيانات" error={query.error} onRetry={() => query.refetch()} />}
      {query.data && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <p className="text-3xl font-bold text-slate-100">{typeof query.data.score === 'number' ? query.data.score : '—'}</p>
            {query.data.level && <span className="mb-1 rounded-full border border-slate-700 px-2 py-1 text-xs text-slate-300">{query.data.level}</span>}
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
              <p className="text-xs font-semibold text-emerald-200">المتوفر</p>
              <p className="mt-2 text-sm text-slate-300">{query.data.present?.length ? query.data.present.join(' · ') : 'لم يحدد الخادم عناصر متوفرة.'}</p>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
              <p className="text-xs font-semibold text-amber-200">الناقص</p>
              <p className="mt-2 text-sm text-slate-300">{query.data.missing?.length ? query.data.missing.join(' · ') : 'لا توجد عناصر ناقصة معلنة.'}</p>
            </div>
          </div>
          {query.data.note_ar && <p className="text-xs leading-relaxed text-slate-400">{query.data.note_ar}</p>}
        </div>
      )}
    </section>
  );
}

export default function FieldWorkspaceDataPanels({ fieldId }: { fieldId: string }) {
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <FieldReadinessPanel fieldId={fieldId} />
      <FieldDataCompletenessPanel fieldId={fieldId} />
    </div>
  );
}
