import { Map, Leaf, AlertTriangle, ArrowUpLeft, RefreshCw, ClipboardList, Droplets } from 'lucide-react';
import { useDashboardData, useAlerts } from '../hooks/useApi';
import { useSelectedField } from '../hooks/useSelectedField';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';
import { KPICard } from '../components/KPICard';
import { canAccess } from '../lib/permissions';
import { isPageEnabled } from '../lib/featureFlags';
import { isRuntimePageEnabled, useFeatureRegistry } from '../hooks/useFeatureRegistry';
import { useAuthStore } from '../hooks/useAuth';
import ConnectionStatus from '../components/ConnectionStatus';
import { measuredNdvi, summarizeNdvi, dataFailureMessage } from '../lib/operationsSummary';
import type { PageId } from '../App';

export default function DashboardPage({ setPage }: { setPage: (p: PageId) => void }) {
  const { data, dash, allNdvi, refetch } = useDashboardData();
  const alertsQuery = useAlerts();
  const { setFieldId } = useSelectedField({ autoSelect: false });
  const { user } = useAuthStore();
  const registry = useFeatureRegistry();
  const allowed = (page: PageId) => canAccess(user?.role, page) && isPageEnabled(page) && isRuntimePageEnabled(page, registry);
  const fields = data.fields_summary;
  const ndvi = summarizeNdvi(fields);
  const alerts = Array.isArray(alertsQuery.data) ? alertsQuery.data : [];
  const alertsKnown = alertsQuery.isSuccess && !alertsQuery.isError;
  const refresh = () => { refetch(); void alertsQuery.refetch(); };

  return <div className="ops-dashboard" dir="rtl">
    <div className="ops-page-heading">
      <div><p className="ops-eyebrow">سهول · مركز العمليات</p><h2>مزرعتك، بوضوح.</h2>
        <p className="ops-muted">تابع الحقول، راجع ما يحتاج انتباهك، وخطّط للعمل التالي.</p></div>
      <button className="ops-button" onClick={refresh} disabled={dash.isFetching}>
        <RefreshCw size={16} aria-hidden="true" />{dash.isFetching ? 'جارٍ التحديث…' : 'تحديث البيانات'}
      </button>
    </div>
    <div className="ops-toolbar"><span>نطاق العرض: جميع حقول المزرعة</span><ConnectionStatus /></div>
    {/* A failed background refresh keeps the last good summary on screen (TanStack keeps data
        on error) and says so; only a failure with nothing to show replaces the page. */}
    {dash.isError && dash.data === undefined ? <ErrorState title="تعذّر تحميل ملخص المزرعة" detail={dataFailureMessage(dash.error)} onRetry={refresh} />
      : dash.data === undefined ? <LoadingState message="جارٍ تحميل ملخص المزرعة…" /> : <>
      {dash.isError && <p className="ops-notice" role="status">تعذّر التحديث الأخير ({dataFailureMessage(dash.error)}). المعروض آخر ملخص ناجح.</p>}
      <section className="ops-metrics" aria-label="ملخص المزرعة">
        <div className="ops-metric"><Map size={20} /><span>الحقول المسجّلة</span><strong>{fields.length}</strong><small>ضمن نطاق المزرعة</small></div>
        <div className="ops-metric"><Leaf size={20} /><span>متوسط NDVI المتاح</span><strong>{ndvi.mean === null ? '—' : ndvi.mean.toFixed(2)}</strong><small>{ndvi.count} من {fields.length} حقل له قراءة</small></div>
        <div className="ops-metric"><AlertTriangle size={20} /><span>التنبيهات المتاحة</span><strong>{alertsKnown ? alerts.length : '—'}</strong><small>{alertsKnown ? 'راجع القائمة لتحديد الأولوية' : 'لم تتأكد بيانات التنبيهات'}</small></div>
      </section>
      {allNdvi.isError && <p className="ops-notice" role="status">تعذّر تحديث المؤشرات النباتية. القراءات المتاحة أدناه لا تعني نجاح التحديث.</p>}
      <div className="ops-workspace">
        <section className="ops-panel">
          <div className="ops-panel-heading"><div><p className="ops-eyebrow">المزرعة</p><h3>الحقول والمؤشرات</h3></div>
            <button className="ops-button ops-button-primary" onClick={() => setPage('fields')}>إدارة الحقول <ArrowUpLeft size={16} /></button></div>
          {fields.length === 0 ? <EmptyState title="لا توجد حقول مسجّلة" hint="أضف حقلك من إدارة الحقول لبدء المتابعة." /> :
          <div className="ops-table-scroll"><table className="ops-table"><caption className="ops-sr-only">قراءات NDVI المتاحة للحقول؛ الشرطة تعني عدم توفر قراءة</caption>
            <thead><tr><th scope="col">الحقل</th><th scope="col">NDVI</th><th scope="col">الإجراء</th></tr></thead>
            <tbody>{fields.map(f => { const value = measuredNdvi(f.ndvi); return <tr key={f.field_id}>
              <th scope="row">{f.field_name || f.field_id}</th>
              <td><span className="ops-value" dir="ltr">{value === null ? '—' : value.toFixed(2)}</span><small className="ops-reading-note">{value !== null ? 'قراءة متاحة' : allNdvi.isLoading ? 'جارٍ التحميل…' : allNdvi.isError ? 'غير معروف' : 'غير مقيس'}</small></td>
              <td><button className="ops-button ops-button-quiet" aria-label={`عرض مؤشرات ${f.field_name || f.field_id}`} onClick={() => {
                setFieldId(String(f.field_id), { source: 'user', name: f.field_name ?? null }); setPage('satellite');
              }}>عرض المؤشرات <ArrowUpLeft size={16} /></button></td>
            </tr>; })}</tbody></table></div>}
        </section>
        <section className="ops-panel">
          <div className="ops-panel-heading"><div><p className="ops-eyebrow">المتابعة</p><h3>ما يحتاج انتباهك</h3></div></div>
          {alertsQuery.isError ? <ErrorState title="تعذّر تحميل التنبيهات" detail={dataFailureMessage(alertsQuery.error)} onRetry={() => { void alertsQuery.refetch(); }} />
            : !alertsKnown ? <LoadingState message="جارٍ تحميل التنبيهات…" />
            : alerts.length === 0 ? <EmptyState title="لا توجد تنبيهات في القائمة" hint="هذه نتيجة آخر طلب ناجح، وليست تقييمًا مستقلًا لسلامة الحقول." />
            : <ul className="ops-alerts">{alerts.slice(0, 4).map(a => <li key={a.alert_id}>
              <button onClick={() => setPage('alerts')} className="ops-alert-button"><AlertTriangle size={18} aria-hidden="true" />
                <span><strong>{a.title_ar || 'تنبيه حقل'}</strong><span>{a.message_ar}</span></span><ArrowUpLeft size={16} aria-hidden="true" />
              </button></li>)}</ul>}
          <button className="ops-button ops-panel-footer" onClick={() => setPage('alerts')}>فتح مركز التنبيهات <ArrowUpLeft size={16} /></button>
        </section>
      </div>
      <p className="ops-muted ops-data-note">مصدر الملخص: بيانات المنصة. القراءة المفقودة لا تُعرض صفرًا، ولا تمثل هذه الشاشة اعتمادًا لتنفيذ الري.</p>
      {data.kpis.length > 0 && <details className="ops-panel"><summary className="ops-panel-heading">المؤشرات التفصيلية</summary><div className="grid grid-cols-2 lg:grid-cols-4 gap-3 p-4">{data.kpis.map(k => <KPICard key={k.id} kpi={{ ...k }} />)}</div></details>}
    </>}
    <section className="ops-shortcuts" aria-label="إجراءات العمل">
      {allowed('map-center') && <button onClick={() => setPage('map-center')}><Map /><span><strong>افتح مركز الخرائط</strong><small>الحدود والبيانات والمؤشرات</small></span><ArrowUpLeft /></button>}
      {allowed('tasks') && <button onClick={() => setPage('tasks')}><ClipboardList /><span><strong>خطّط ليومك</strong><small>المهام الميدانية والمتابعة</small></span><ArrowUpLeft /></button>}
      {allowed('irrigation-ops') && <button onClick={() => setPage('irrigation-ops')}><Droplets /><span><strong>راجع الري</strong><small>الجداول والحالة التشغيلية</small></span><ArrowUpLeft /></button>}
    </section>
  </div>;
}
