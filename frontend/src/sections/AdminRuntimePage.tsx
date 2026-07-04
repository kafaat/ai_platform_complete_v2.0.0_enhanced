import { ServerCog, ShieldAlert, MailWarning, ListTree, Timer, CheckCircle2, XCircle, AlertTriangle } from 'lucide-react';
import {
  useAdminReadiness, useAdminEventsDeadLetter, useAdminOutboxDeadLetter,
  useSecurityDenials, useQueueStatus, useAutomationRuns, useSchedulerStatus,
} from '../hooks/useApi';
import { useAuthStore } from '../hooks/useAuth';
import { canManage } from '../lib/permissions';
import { dlqHealth, queueStatusChips, readinessCounters } from '../lib/adminRuntime';
import { T } from '../components/ds';

/** كونسول التشغيل الإداريّ: جاهزيّة الإنتاج + قوائم الموتى (أحداث/outbox) + رفض
 *  الأمان + قائمة offline + الأتمتة — كانت مسارات إدارة خلفيّة بلا أيّ واجهة.
 *  مقصور على owner/manager (canManage) — والخلفيّة تفرض AUDIT_VIEW أصلاً. */
export default function AdminRuntimePage() {
  const { user } = useAuthStore();
  const allowed = canManage(user?.role);

  const readinessQ = useAdminReadiness(allowed);
  const eventsDlqQ = useAdminEventsDeadLetter(allowed);
  const outboxDlqQ = useAdminOutboxDeadLetter(allowed);
  const denialsQ = useSecurityDenials(allowed);
  const queueQ = useQueueStatus(allowed);
  const runsQ = useAutomationRuns(allowed);
  const schedulerQ = useSchedulerStatus(allowed);

  if (!allowed) {
    return (
      <div className="p-4 text-sm" style={{ color: T.muted }}>
        هذه الصفحة مقصورة على المالك/المدير — دورك الحاليّ لا يخوّل عرض تشغيل المنصّة.
      </div>
    );
  }

  const counters = readinessCounters(readinessQ.data);
  const dlq = dlqHealth(eventsDlqQ.data, outboxDlqQ.data);
  const chips = queueStatusChips(queueQ.data);
  const denialsSummary = denialsQ.data?.summary ?? null;
  const runsSummary = runsQ.data?.summary ?? null;
  const scheduler = schedulerQ.data ?? null;

  return (
    <div className="p-4 flex flex-col gap-3" data-testid="admin-runtime">
      <h1 className="inline-flex items-center gap-2 text-lg font-bold" style={{ color: T.ink }}>
        <ServerCog className="w-5 h-5 text-emerald-300" aria-hidden="true" /> تشغيل المنصّة (Runtime)
      </h1>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {/* جاهزيّة الإنتاج */}
        <Panel title="جاهزيّة الإنتاج" icon={readinessQ.data?.ready ? CheckCircle2 : XCircle} tone={readinessQ.data ? (readinessQ.data.ready ? 'good' : 'bad') : undefined}>
          {readinessQ.isLoading ? (
            <Muted>جارٍ التقييم…</Muted>
          ) : readinessQ.isError ? (
            <Muted>تعذّرت قراءة الجاهزيّة (تحقّق من صلاحيّة AUDIT_VIEW).</Muted>
          ) : readinessQ.data ? (
            <>
              <div className="text-sm font-bold" style={{ color: readinessQ.data.ready ? '#86efac' : '#fca5a5' }}>
                {readinessQ.data.ready ? 'جاهزة' : 'غير جاهزة'}
                <span className="text-[11px] font-normal" style={{ color: T.faint }}>
                  {' '}· بيئة {readinessQ.data.is_production ? 'إنتاج' : 'تطوير'}
                </span>
              </div>
              <div className="text-[11px]" style={{ color: T.muted }}>
                فحوص: {counters.ok} سليم · {counters.warn} تحذير · {counters.block} حاجب
              </div>
              {readinessQ.data.blockers.slice(0, 3).map((b) => (
                <div key={b} className="text-[11px]" style={{ color: '#fca5a5' }}>⛔ {b}</div>
              ))}
            </>
          ) : null}
        </Panel>

        {/* قوائم الموتى */}
        <Panel title="قوائم الموتى (DLQ)" icon={MailWarning} tone={dlq === 'attention' ? 'bad' : dlq === 'healthy' ? 'good' : undefined}>
          {eventsDlqQ.isLoading || outboxDlqQ.isLoading ? (
            <Muted>جارٍ القراءة…</Muted>
          ) : (
            <>
              <div className="text-[12px]" style={{ color: T.ink }}>
                أحداث NATS: <b>{eventsDlqQ.data?.total ?? '—'}</b> · outbox: <b>{outboxDlqQ.data?.total ?? '—'}</b>
              </div>
              {dlq === 'attention' && (
                <div className="text-[11px]" style={{ color: '#fdba74' }}>
                  {eventsDlqQ.data?.note_ar ?? outboxDlqQ.data?.note_ar ?? 'يوجد رسائل ميّتة — أصلح السبب ثمّ أعد الجدولة.'}
                </div>
              )}
              {dlq === 'healthy' && <Muted>لا رسائل ميّتة — التدفّق سليم.</Muted>}
            </>
          )}
        </Panel>

        {/* قائمة offline */}
        <Panel title="قائمة Offline" icon={ListTree}>
          {queueQ.isLoading ? (
            <Muted>جارٍ القراءة…</Muted>
          ) : queueQ.data ? (
            <>
              <div className="text-[12px]" style={{ color: T.ink }}>
                في الانتظار: <b>{queueQ.data.total_in_queue}</b>
              </div>
              <div className="flex flex-wrap gap-1.5 mt-1">
                {chips.map((c) => (
                  <span key={c.status} className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.muted }}>
                    {c.status}: {c.count}
                  </span>
                ))}
                {chips.length === 0 && <Muted>لا عناصر معلّقة.</Muted>}
              </div>
            </>
          ) : (
            <Muted>تعذّرت القراءة.</Muted>
          )}
        </Panel>

        {/* رفض الأمان */}
        <Panel title="رفض الأمان (Denials)" icon={ShieldAlert}>
          {denialsQ.isLoading ? (
            <Muted>جارٍ القراءة…</Muted>
          ) : denialsQ.data ? (
            <>
              <div className="text-[12px]" style={{ color: T.ink }}>
                آخر السجلّ: <b>{denialsQ.data.denials.length}</b> رفضاً
              </div>
              {denialsSummary && (
                <pre className="text-[10px] mt-1 overflow-x-auto" style={{ color: T.faint }}>
                  {JSON.stringify(denialsSummary, null, 1)}
                </pre>
              )}
            </>
          ) : (
            <Muted>تعذّرت القراءة.</Muted>
          )}
        </Panel>

        {/* الأتمتة */}
        <Panel title="الأتمتة (Scheduler)" icon={Timer}>
          {runsQ.isLoading || schedulerQ.isLoading ? (
            <Muted>جارٍ القراءة…</Muted>
          ) : (
            <>
              {scheduler && (
                <pre className="text-[10px] overflow-x-auto" style={{ color: T.faint }}>
                  {JSON.stringify(scheduler, null, 1)}
                </pre>
              )}
              {runsQ.data && (
                <div className="text-[12px] mt-1" style={{ color: T.ink }}>
                  تشغيلات مسجَّلة: <b>{runsQ.data.runs.length}</b>
                </div>
              )}
              {runsSummary && (
                <pre className="text-[10px] mt-1 overflow-x-auto" style={{ color: T.faint }}>
                  {JSON.stringify(runsSummary, null, 1)}
                </pre>
              )}
            </>
          )}
        </Panel>
      </div>

      <div className="inline-flex items-center gap-1.5 text-[11px]" style={{ color: T.faint }}>
        <AlertTriangle className="w-3.5 h-3.5" aria-hidden="true" />
        القيم من مسارات الإدارة الحيّة (AUDIT_VIEW) — «—» تعني تعذّر القراءة لا صفراً.
      </div>
    </div>
  );
}

function Panel({ title, icon: Icon, tone, children }: { title: string; icon: typeof ServerCog; tone?: 'good' | 'bad'; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border p-3" style={{ borderColor: tone === 'bad' ? '#7c2d12' : tone === 'good' ? '#14532d' : T.line, background: 'rgba(2,6,23,.35)' }}>
      <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
        <Icon className="w-4 h-4 text-emerald-300" aria-hidden="true" /> {title}
      </div>
      <div className="flex flex-col gap-0.5">{children}</div>
    </section>
  );
}

function Muted({ children }: { children: React.ReactNode }) {
  return <div className="text-[11px]" style={{ color: T.muted }}>{children}</div>;
}
