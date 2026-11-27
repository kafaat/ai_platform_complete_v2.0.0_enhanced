import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '../hooks/useAuth';
import { getAuthScope } from '../lib/authStorage';
import { normalizeRole } from '../lib/permissions';
import {
  getInspectionExecutions, inspectionErrorStatus, inspectionInboxHidden, inspectionReason,
  receiveInspectionExecution, verifyInspectionExecution,
  type InspectionExecution, type InspectionExecutionState,
} from '../services/api/inspectionExecutions';

export const inspectionExecutionKey = (tenantId: string, userId: string, role: string, fieldId: string) =>
  ['inspection-executions', tenantId, userId, role, fieldId] as const;

type Scope = { fieldId: string; tenantId: string; userId: string; role: string; authScope: string };
type Command = { kind: 'receive' | 'verify'; item: InspectionExecution };
const stateLabel: Record<InspectionExecutionState, string> = {
  queued: 'جاهزة للإرسال إلى المستلم', delivering: 'التسليم بحاجة إلى استكمال',
  accepted: 'حُفظت المهمة للمستلم', verified_success: 'سُجّل تأكيد النتيجة المعتمدة',
  blocked: 'تحتاج المهمة إلى مراجعة قبل التسليم',
};

function verificationHint(item: InspectionExecution) {
  const reason = inspectionReason(item.verification_reason);
  if (item.state === 'verified_success' && reason) return 'هذا سجل تأكيد سابق؛ الدليل الحالي يحتاج إلى مراجعة جديدة.';
  if (reason === 'only_current_approver_may_verify') return 'تأكيد النتيجة متاح للمراجع الذي اعتمد النسخة الحالية.';
  if (reason === 'inspection_not_completed') return 'بانتظار استلام الزيارة، ورفع النتيجة، واعتمادها، وإكمال المهمة.';
  if (reason === 'current_independent_inspection_approval_required') return 'يلزم اعتماد النسخة الحالية من مراجع مختلف عن المفتش.';
  if (item.state === 'accepted' && !item.can_verify) return 'لا تتوافر بعد شروط تأكيد نتيجة التفتيش الحالية.';
  return null;
}

function ScopedInbox(scope: Scope) {
  const { fieldId, tenantId, userId, role, authScope } = scope;
  const cache = useQueryClient();
  const key = inspectionExecutionKey(tenantId, userId, role, fieldId);
  const mounted = useRef(true);
  const pending = useRef(false);
  const commands = useRef(new Set<AbortController>());
  const [notice, setNotice] = useState<string | null>(null);
  useEffect(() => {
    mounted.current = true;
    const controllers = commands.current;
    return () => {
      mounted.current = false;
      controllers.forEach(controller => controller.abort());
      controllers.clear();
    };
  }, []);
  const current = () => {
    const state = useAuthStore.getState();
    return mounted.current && getAuthScope() === authScope && state.tenantId === tenantId &&
      String(state.user?.id ?? state.user?.email ?? '') === userId && normalizeRole(state.user?.role) === role;
  };
  const query = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => getInspectionExecutions(fieldId, { authScope, signal }),
    staleTime: 0, retry: false,
  });
  const refresh = () => {
    if (!current()) return;
    void cache.invalidateQueries({ queryKey: key, exact: true });
    void cache.invalidateQueries({ queryKey: ['tasks', tenantId] });
    void cache.invalidateQueries({ queryKey: ['pin-inspection', tenantId, fieldId] });
    void cache.invalidateQueries({
      predicate: entry => {
        const q = entry.queryKey;
        if (q[0] === 'field-workspace') return q[1] === fieldId && q[2] === 'tasks' && q[3] === tenantId &&
          q[4] === useAuthStore.getState().user?.email && normalizeRole(String(q[5] ?? '')) === role;
        return q[0] === 'inspection-handoff' && q[1] === tenantId && q[2] === fieldId &&
          String(q[4] ?? '') === userId && normalizeRole(String(q[5] ?? '')) === role;
      },
    });
  };
  const change = useMutation({
    mutationFn: async ({ kind, item }: Command) => {
      if (!current()) throw new Error('session changed');
      const controller = new AbortController();
      commands.current.add(controller);
      try {
        const context = { authScope, signal: controller.signal };
        if (kind === 'receive' && item.can_receive) {
          return await receiveInspectionExecution(fieldId, item.execution_request_id, context);
        }
        if (kind === 'verify' && item.can_verify && item.task_id) {
          return await verifyInspectionExecution(fieldId, item.task_id, item.execution_request_id, context);
        }
        throw new Error('action unavailable');
      } finally { commands.current.delete(controller); }
    },
    onSuccess: (_, command) => {
      if (!current()) return;
      setNotice(command.kind === 'receive'
        ? 'حُفظت مهمة التفتيش وأصبح بإمكان المستلم تأكيد استلامها من صفحة المهام.'
        : 'سُجّل تأكيد النتيجة وربطها بالتفتيش المعتمد.');
    },
    onSettled: () => { pending.current = false; refresh(); },
    retry: false,
  });
  const act = (command: Command) => {
    if (pending.current || query.isFetching || query.isError || !current()) return;
    pending.current = true;
    setNotice(null);
    change.mutate(command);
  };

  // A cached former success does not expose actions after access or configuration changes.
  if (inspectionInboxHidden(query.error) || inspectionInboxHidden(change.error)) return null;
  const data = query.isError ? undefined : query.data;
  const busy = change.isPending || query.isFetching;
  const mutationConflict = inspectionErrorStatus(change.error) === 409;
  return <section className="mt-5 space-y-3 rounded-xl border border-slate-700 p-4" aria-label="تسليم مهام التفتيش" dir="rtl">
    <div className="flex items-center justify-between gap-3">
      <h3 className="font-semibold text-slate-100">تسليم مهام التفتيش</h3>
      <button type="button" disabled={busy} onClick={() => { setNotice(null); change.reset(); void query.refetch(); }}
        className="rounded-lg border border-slate-700 px-3 py-1 text-sm text-slate-200 disabled:opacity-50">تحديث مهام التفتيش</button>
    </div>
    <p className="text-sm text-slate-400">استلام الزيارة ورفع نتائجها ومراجعتها متاح من <a className="text-emerald-300 underline" href="/ops/tasks">صفحة المهام الميدانية</a>.</p>
    {query.isPending && <p role="status">جارٍ تحميل مهام التفتيش…</p>}
    {query.isError && <p role="alert">تعذّر تحميل مهام التفتيش. أعد المحاولة للتحقق من الحالة الحالية.</p>}
    {change.isError && <p role="alert">{mutationConflict
      ? 'تغيّرت حالة المهمة أو الدليل. راجع الحالة الحالية قبل إعادة المحاولة.'
      : 'تعذّر تأكيد العملية. حدّث الحالة قبل إعادة المحاولة؛ قد يكون الخادم قد حفظها.'}</p>}
    {notice && <p role="status" className="text-emerald-300">{notice}</p>}
    {data && data.items.length === 0 && <p className="text-sm text-slate-400">لا توجد طلبات تفتيش متاحة لهذا الحقل الآن.</p>}
    {data && data.truncated && <p role="status" className="text-sm text-amber-200">القائمة محدودة؛ قد توجد طلبات أخرى غير ظاهرة.</p>}
    {!!data?.items.length && <ol className="space-y-3">
      {data.items.map(item => <li key={item.execution_request_id} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
        <p className="font-medium text-slate-200">{stateLabel[item.state]}</p>
        {item.assigned_to && <p className="mt-1 text-sm text-slate-300">{item.assignee_name?.trim()
          ? <>المستلم: <bdi>{item.assignee_name}</bdi></> : 'المستلم المحدد في الخطة'}</p>}
        {item.due_at && <p className="text-xs text-slate-400">موعد الزيارة: <time dateTime={item.due_at}>{new Date(item.due_at).toLocaleString('ar')}</time></p>}
        {item.state === 'blocked' && <p className="mt-2 text-sm text-amber-200">تحقق من ربط الحقل والدبوس والمستلم وخطة التنفيذ قبل إعادة المحاولة.</p>}
        {verificationHint(item) && <p className="mt-2 text-sm text-slate-400">{verificationHint(item)}</p>}
        <details className="mt-2 break-words text-xs text-slate-400">
          <summary className="cursor-pointer">تفاصيل التتبع</summary>
          <p className="mt-1">مرجع القرار: <bdi>{item.decision_id}</bdi></p>
          <p>مرجع طلب التنفيذ: <bdi>{item.execution_request_id}</bdi></p>
          {item.pin_id && <p>دبوس التفتيش: <bdi>{item.pin_id}</bdi></p>}
          {item.task_id && <p>مرجع المهمة: <bdi>{item.task_id}</bdi></p>}
          {item.assigned_to && <p>معرّف المستلم: <bdi>{item.assigned_to}</bdi></p>}
          {item.outcome_id && <p>مرجع تأكيد النتيجة: <bdi>{item.outcome_id}</bdi></p>}
        </details>
        <div className="mt-3 flex flex-wrap gap-2">
          {item.can_receive && <button type="button" disabled={busy} onClick={() => act({ kind: 'receive', item })}
            className="rounded-lg bg-emerald-800 px-3 py-2 text-sm text-white disabled:opacity-50">
            {item.state === 'delivering' ? 'استكمال تسليم مهمة التفتيش' : 'إرسال مهمة التفتيش للمستلم'}
          </button>}
          {item.can_verify && <button type="button" disabled={busy} onClick={() => act({ kind: 'verify', item })}
            className="rounded-lg bg-emerald-800 px-3 py-2 text-sm text-white disabled:opacity-50">تأكيد نتيجة التفتيش المعتمدة</button>}
        </div>
      </li>)}
    </ol>}
  </section>;
}

export default function InspectionExecutionInbox({ fieldId }: { fieldId: string }) {
  const { tenantId, user, isAuthenticated, isDemoMode } = useAuthStore();
  const role = normalizeRole(user?.role);
  const userId = String(user?.id ?? user?.email ?? '');
  const authScope = getAuthScope();
  if (!fieldId || !tenantId || !userId || !isAuthenticated || isDemoMode ||
      !['owner', 'manager'].includes(role) || authScope !== JSON.stringify([tenantId, userId])) return null;
  // Remount all mutation state on a field/account/permission change; never reuse a prior notice.
  return <ScopedInbox key={JSON.stringify([authScope, role, fieldId])}
    fieldId={fieldId} tenantId={tenantId} userId={userId} role={role} authScope={authScope} />;
}
