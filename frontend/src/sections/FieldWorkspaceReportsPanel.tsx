import { useFieldReport } from '../hooks/useApi';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';
import { TASK_STATUS_AR } from '../components/ds/status';

// تسميات عربيّة لمفاتيح الحالة الخام القادمة من الخادم؛ المفتاح المجهول يُعرَض كما هو
// (لا يُخترَع له معنى) كي لا تختفي حالة جديدة من العدّ.
const ACTIVITY_STATUS_AR: Record<string, string> = {
  ...TASK_STATUS_AR, planned: 'مخطّطة', scheduled: 'مجدولة', done: 'منجزة', skipped: 'متخطّاة',
};
const ALERT_STATUS_AR: Record<string, string> = {
  active: 'نشط', acknowledged: 'تمّ الاطّلاع', resolved: 'عولِج',
};
function activityStatusLabel(status: string): string {
  return ACTIVITY_STATUS_AR[status.toLowerCase()] ?? status;
}
function alertStatusLabel(status?: string | null): string {
  if (!status) return '—';
  return ALERT_STATUS_AR[status.toLowerCase()] ?? status;
}

export type FieldWorkspaceReportsPanelProps = { fieldId: string; seasonId?: string | null };

export default function FieldWorkspaceReportsPanel({ fieldId }: FieldWorkspaceReportsPanelProps) {
  const query = useFieldReport(fieldId || undefined);
  if (!fieldId) return <EmptyState title="اختر حقلاً لعرض تقريره" />;
  if (query.isLoading) return <LoadingState message="جارٍ تحميل ملخص الحقل…" />;
  if (query.isError) return <ErrorState title="تعذّر تحميل تقرير الحقل" onRetry={() => { void query.refetch(); }} />;
  const data = query.data;
  if (!data) return <EmptyState title="لم تُعد الخدمة ملخصاً للحقل" />;
  return (
    <section className="space-y-4 rounded-2xl border border-slate-800 bg-slate-950/70 p-5" dir="rtl" aria-label="تقارير الحقل">
      <h2 className="text-base font-bold text-slate-100">ملخص الحقل الحالي — {data.name}</h2>
      <p className="text-sm text-slate-400">ملخص مباشر من خدمة التقارير؛ ليس ملفاً محفوظاً أو تقريراً تاريخياً للموسم الموجود في الرابط.</p>
      <dl className="grid gap-3 sm:grid-cols-2">
        <div><dt>المحصول</dt><dd>{data.crop ?? '—'}</dd></div>
        <div><dt>المساحة (هكتار)</dt><dd>{Number.isFinite(data.area_ha) ? data.area_ha : '—'}</dd></div>
        <div><dt>نوع التربة</dt><dd>{data.soil_type ?? '—'}</dd></div>
        <div><dt>العمليات المسجلة</dt><dd>{Number.isFinite(data.activities_total) ? data.activities_total : '—'}</dd></div>
      </dl>
      <div><h3>العمليات حسب الحالة</h3><ul>{Object.entries(data.activities_by_status ?? {}).map(([status, count]) => <li key={status}>{activityStatusLabel(status)}: {count}</li>)}</ul></div>
      <div><h3>التنبيهات الأخيرة</h3>{data.recent_alerts?.length ? <ul className="space-y-2">{data.recent_alerts.map(alert => <li key={alert.alert_id}><strong>{alert.title_ar ?? alert.alert_type}</strong><p>{alert.message_ar}</p><small>{alertStatusLabel(alert.status)}</small></li>)}</ul> : <p>لا توجد تنبيهات في آخر استجابة ناجحة.</p>}</div>
      <button type="button" disabled={query.isFetching} onClick={() => { void query.refetch(); }} className="rounded-xl border border-slate-700 px-4 py-2">{query.isFetching ? 'جارٍ التحديث…' : 'تحديث الملخص'}</button>
    </section>
  );
}
