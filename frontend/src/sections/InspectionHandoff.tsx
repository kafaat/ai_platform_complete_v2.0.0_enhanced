import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '../hooks/useAuth';
import { kongApi } from '../services/api';

type Event = {
  revision: number; action: 'accept' | 'reassign'; assignee: string; previous_assignee: string;
  actor: string; occurred_at: string; reason: string | null;
};
type History = {
  revision: number; accepted: boolean; assigned_to: string; initial_assignee: string;
  assigned_by: string; assigned_at: string; events: Event[]; can_accept: boolean; can_reassign: boolean;
};
type Command = { action: 'accept' | 'reassign'; expected_revision: number; assigned_to?: number; reason?: string };

export function InspectionHandoff({fieldId, taskId, tenant}: {fieldId: string; taskId: string; tenant?: string}) {
  const user = useAuthStore(s => s.user);
  const scope = tenant || user?.tenant_id;
  const cache = useQueryClient();
  const key = ['inspection-handoff', scope, fieldId, taskId, user?.id ?? user?.email, user?.role];
  const fieldPath = '/api/v1/fields/' + encodeURIComponent(fieldId);
  const path = fieldPath + '/tasks/' + encodeURIComponent(taskId) + '/handoff';
  const query = useQuery({queryKey: key, queryFn: async () => (await kongApi.get<History>(path)).data});
  const data = query.data;
  const [person, setPerson] = useState('');
  const [reason, setReason] = useState('');
  const team = useQuery({
    queryKey: ['inspection-assignees', scope, fieldId], enabled: !!data?.can_reassign,
    queryFn: async () => (await kongApi.get<{assignees: {id: number; full_name: string}[]}>(fieldPath + '/inspection-assignees')).data.assignees,
  });
  const change = useMutation({
    mutationFn: async ({action, ...args}: Command) => (await kongApi.post<History>(path + '/' + action, args)).data,
    onSuccess: state => {
      cache.setQueryData(key, state);
      void cache.invalidateQueries({queryKey: ['pin-inspection', scope, fieldId]});
      void cache.invalidateQueries({queryKey: ['tasks', scope]});
      setPerson(''); setReason('');
    },
    onError: () => { void query.refetch(); },
  });
  if (query.isError) return <p role="alert">تعذّر جلب سجل تسليم التفتيش</p>;
  if (!data) return <p>جارٍ جلب سجل التسليم…</p>;
  return <section aria-label="سجل تسليم التفتيش" className="space-y-2">
    <p>المستلم الحالي {data.assigned_to} · {data.accepted ? 'قَبِل التكليف' : 'بانتظار تأكيد الاستلام'}</p>
    <details><summary>سجل التسليم</summary>
      <p>كلّف {data.assigned_by} المفتش {data.initial_assignee} · {new Date(data.assigned_at).toLocaleString('ar')}</p>
      <ol>{data.events.map(event => <li key={event.revision}>
        {event.action === 'accept' ? 'أكّد الاستلام ' + event.actor
          : 'أعاد ' + event.actor + ' الإسناد من ' + event.previous_assignee + ' إلى ' + event.assignee + ' · ' + event.reason}
        {' · '}{new Date(event.occurred_at).toLocaleString('ar')}
      </li>)}</ol>
    </details>
    {data.can_accept && <button type="button" disabled={change.isPending} onClick={() =>
      change.mutate({action:'accept', expected_revision:data.revision})}>تأكيد استلام الزيارة</button>}
    {data.can_reassign && <div className="flex flex-wrap gap-2">
      <label>المستلم البديل <select value={person} onChange={e => setPerson(e.target.value)}>
        <option value="">اختر المستلم</option>
        {team.data?.filter(p => String(p.id) !== data.assigned_to).map(p => <option key={p.id} value={p.id}>{p.full_name}</option>)}
      </select></label>
      <label>سبب إعادة الإسناد <input value={reason} maxLength={500} onChange={e => setReason(e.target.value)} /></label>
      <button type="button" disabled={change.isPending || !person || !reason.trim()} onClick={() =>
        change.mutate({action:'reassign', expected_revision:data.revision, assigned_to:Number(person), reason:reason.trim()})}>إعادة إسناد الزيارة</button>
      {team.isError && <span role="alert">تعذّر جلب المستلمين</span>}
    </div>}
    {change.isError && <p role="alert">تعذّر تأكيد الإجراء. راجع سجل التسليم قبل المحاولة مجدداً.</p>}
  </section>;
}

export default InspectionHandoff;
