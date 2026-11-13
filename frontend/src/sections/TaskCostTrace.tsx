import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { kongApi } from '../services/api/client';

type Trace = {
  task: { farm_id?: string };
  changes: { changed_at: string; changed_by: string | null; previous_usd: number | null;
    actual_usd: number | null; status: string }[];
  entries: { entry_id: string; entry_type: string; amount: string; currency: string; occurred_on: string;
    receipt_document_id?: string; reverses_entry_id?: string }[];
  expenses_by_currency: Record<string, string>;
};

function Receipt({ id, tenant, subject }: { id: string; tenant: string; subject: string }) {
  const [open, setOpen] = useState(false);
  const doc = useQuery({
    queryKey: ['task-receipt', tenant, subject, id], enabled: open, retry: false,
    queryFn: async () => (await kongApi.get<{ title: string; version: number; content_type: string | null }>(
      '/api/v1/documents/' + encodeURIComponent(id))).data,
  });
  return <span> · <button type="button" className="underline" onClick={() => setOpen(!open)} aria-expanded={open}>إيصال {id}</button>
    {open && (doc.isSuccess ? <span> · {doc.data.title} · إصدار {doc.data.version} · {doc.data.content_type}</span>
      : <span>{doc.isError ? ' تعذّر فتح بيانات المستند' : ' جارٍ التحميل…'}</span>)}</span>;
}

type Props = {
  taskId: string; fieldId: string; tenant: string; subject: string; amount?: number | null; canRecord: boolean;
};

export function TaskCostTrace({ taskId, fieldId, tenant, subject, amount, canRecord }: Props) {
  const [open, setOpen] = useState(false);
  const trace = useQuery({
    queryKey: ['task-cost-trace', tenant, taskId, subject], enabled: open, retry: false,
    queryFn: async () => (await kongApi.get<Trace>('/api/v1/tasks/' + encodeURIComponent(taskId) + '/cost-trace')).data,
  });
  const params = new URLSearchParams({ task_id: taskId, field_id: fieldId });
  if (trace.data?.task.farm_id) params.set('farm_id', trace.data.task.farm_id);
  if (amount != null && amount > 0) params.set('cost_usd', String(amount));
  return <section className="my-2 space-y-2 text-sm">
    <button type="button" className="underline" aria-expanded={open} onClick={() => setOpen(!open)}>تتبع التكلفة والقيود</button>
    {open && <>
      {trace.isLoading && <p>جارٍ تحميل السجل…</p>}
      {trace.isError && <p role="alert">تعذرت قراءة السجل. تحقق من صلاحية عرض التحليلات.</p>}
      {trace.isSuccess && <>
        {canRecord && <a href={'/ops/farm-book?' + params.toString()} className="underline">تسجيل مصروف أو ربط قيد سابق</a>}
        {trace.data.changes.length === 0 && <p>لا تغييرات مسجلة منذ تفعيل التتبع.</p>}
        {trace.data.changes.map((change, i) => <p key={i}>{change.changed_at} · {change.changed_by ?? 'غير مسجل'} ·
          {' من '}{change.previous_usd ?? '—'} إلى {change.actual_usd ?? '—'} USD · {change.status}</p>)}
        {trace.data.entries.length === 0 && <p>لا قيود مرتبطة.</p>}
        {trace.data.entries.map(e => <p key={e.entry_id}>{e.occurred_on} · {e.reverses_entry_id ? 'عكس' :
          e.entry_type === 'payment' ? 'سداد' : e.entry_type === 'income' ? 'إيراد' : 'مصروف'} · {e.amount} {e.currency} · {e.entry_id}
          {e.receipt_document_id && <Receipt id={e.receipt_document_id} tenant={tenant} subject={subject} />}</p>)}
        {Object.entries(trace.data.expenses_by_currency).map(([cur, total]) => <p key={cur}>صافي المصروف المقيد: {total} {cur}</p>)}
      </>}
    </>}
  </section>;
}
