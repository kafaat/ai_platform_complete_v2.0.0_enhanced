// ═══════════════════════════════════════════════════════════════
// SAHOOL — TasksPage (مربوطة ببيانات حيّة)
// كانت تبذُر MOCK_TASKS وتعرضها افتراضيّاً. الآن: مهام حيّة من useTasks (/tasks)،
// إنجاز فعليّ عبر useCompleteTask (PATCH)، حالات موحّدة (StateViews)، وأزرار
// محكومة بالدور (RBAC: المُشاهِد لا يُعدّل). لا تلفيق.
// ═══════════════════════════════════════════════════════════════
import { InspectionHandoff } from './InspectionHandoff';
import { TaskCostTrace, TaskExpenseLink } from './TaskCostTrace';
import { useState } from 'react';
import TaskIrrigationObservationPanel from './TaskIrrigationObservationPanel';
import {
  Loader2, Check, Camera, Clock, AlertTriangle,
  Wrench, Droplets, Sprout, Bug, Wheat, RefreshCw,
  CheckCircle, Calendar,
} from 'lucide-react';
import { kongApi } from '../services/api';
import { toastStore } from '../services/websocket';
import { useTasks, useCompleteTask } from '../hooks/useApi';
import { useAuthStore } from '../hooks/useAuth';
import { canAccess, canMutate, canRecordExpense } from '../lib/permissions';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';
import { Card, Button, Pill } from '../components/ds/atoms';
import { Select } from '../components/ds/forms';
import { T, RADIUS, toneColors } from '../components/ds/tokens';
import { taskStatusAr, taskStatusTone } from '../components/ds/status';
import { TASK_TYPE_LABELS_AR as L } from '../lib/taskTypeLabels';

interface Task {
  source_scouting_pin_id?: string | null;
  task_id:               string;
  field_id:              string;
  field_name?:           string;
  task_type:             string;
  priority:              number;
  recommended_date:      string;
  status:                'pending' | 'in_progress' | 'completed' | 'cancelled';
  estimated_duration_min:number;
  estimated_cost_usd:    number;
  actual_cost_usd?:      number | null;
  notes?:                string;
  photo_url?:            string;
  assigned_to?:          string;
  tenant_id:             string;
}

// التسميات من مصدر مشترك مع لوحة مهامّ مساحة عمل الحقل (lib/taskTypeLabels).
const TASK_CONFIG: Record<string, { icon: typeof Wrench; label: string; color: string }> = {
  irrigation:    { icon: Droplets, label: L.irrigation,    color: '#3b82f6' },
  fertilization: { icon: Sprout,   label: L.fertilization, color: '#16a34a' },
  spraying:      { icon: Bug,      label: L.spraying,      color: '#f97316' },
  harvest:       { icon: Wheat,    label: L.harvest,       color: '#f59e0b' },
  scouting:      { icon: Wrench,   label: L.scouting,      color: '#8b5cf6' },
  soil_sampling: { icon: Wrench,   label: L.soil_sampling, color: '#92400e' },
};

// حالات المهام (تسمية + نغمة) موحّدة عبر DS (status.ts/tokens.ts) بدل
// خريطة الألوان الداكنة المحلّيّة السابقة.

const PRIORITY_MAP: Record<number, string> = { 1: 'حرج', 2: 'عالٍ', 3: 'متوسط', 4: 'منخفض', 5: 'روتيني' };

export default function TasksPage() {
  const { user, tenantId } = useAuthStore();
  const canViewCosts = canAccess(user?.role, 'analytics');
  const canRecordCost = canRecordExpense(user?.role);
  const mutateAllowed = canMutate(user?.role, 'field');
  const { data, isLoading, isError, refetch, isFetching } = useTasks();
  const completeMut = useCompleteTask();

  const [observationTask, setObservationTask] = useState<Task | null>(null);
  const [filter, setFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [completing, setCompleting] = useState<string | null>(null);
  // تعديلات تفاؤليّة فوق البيانات الحيّة (بدء/إنجاز/صورة) دون استبدال المصدر.
  const [overrides, setOverrides] = useState<Record<string, Partial<Task>>>({});

  const apiTasks = ((data as { tasks?: Task[] } | undefined)?.tasks ?? []) as Task[];
  const tasks = apiTasks.map(t => ({ ...t, ...overrides[t.task_id] }));

  const statusTypes: Array<Task['status'] | 'all'> = ['all', 'pending', 'in_progress', 'completed'];

  const filtered = tasks.filter(t =>
    (filter === 'all' || t.status === filter) &&
    (typeFilter === 'all' || t.task_type === typeFilter)
  );

  const counts = {
    all: tasks.length,
    pending: tasks.filter(t => t.status === 'pending').length,
    in_progress: tasks.filter(t => t.status === 'in_progress').length,
    completed: tasks.filter(t => t.status === 'completed').length,
  };

  const setStatus = (taskId: string, patch: Partial<Task>) =>
    setOverrides(p => ({ ...p, [taskId]: { ...p[taskId], ...patch } }));

  const completeTask = async (taskId: string, actualCostUsd?: number) => {
    if (!mutateAllowed) return;
    setCompleting(taskId);
    try {
      await completeMut.mutateAsync({ taskId, actualCostUsd });
      setOverrides(previous => {
        const { status: _started, ...rest } = previous[taskId] ?? {};
        return { ...previous, [taskId]: rest };
      });
      toastStore.add('success', '✅ تم إنجاز المهمة', '');
    } catch {
      // صدق: لا نُعلن نجاحاً عند فشل الحفظ (كان يُعلَن نجاح زائف ويُخفي العطل).
      toastStore.add('error', '⚠️ تعذّر إنجاز المهمة', 'فشل الاتصال بالخادم — لم تُحفظ');
    } finally {
      setCompleting(null);
    }
  };

  const startTask = async (taskId: string) => {
    if (!mutateAllowed) return;
    try {
      await kongApi.patch(`/api/v1/tasks/${taskId}`, { status: 'in_progress' });
      setStatus(taskId, { status: 'in_progress' });
    } catch {
      toastStore.add('error', '⚠️ تعذّر بدء المهمة', 'فشل الاتصال بالخادم');
    }
  };

  const handlePhotoUpload = (taskId: string, file: File) => {
    if (!mutateAllowed) return;
    // معاينة محلّيّة فقط (blob) — لا رفع للخادم بعد (لا endpoint multipart). **لا نُكمل
    // المهمّة هنا**: كان الإكمال التلقائيّ عند اختيار صورة يوحي بإنجازٍ موثَّق بصورة بينما
    // السجلّ الدائم لا يحمل صورة (أثر تدقيق زائف — continuation-3 P0). المعاينة صريحة غير
    // محفوظة، والإكمال يبقى إجراءً مستقلّاً عبر زرّ «إنجاز». نُبطِل رابط المعاينة السابق
    // لتفادي تسريب object URL (continuation-3 P1).
    const url = URL.createObjectURL(file);
    setOverrides((p) => {
      const prev = p[taskId]?.photo_url;
      if (prev && prev.startsWith('blob:')) URL.revokeObjectURL(prev);
      return { ...p, [taskId]: { ...p[taskId], photo_url: url } };
    });
  };

  const renderTaskCard = (task: Task) => {
    const cfg = TASK_CONFIG[task.task_type] || TASK_CONFIG.scouting;
    const Icon = cfg.icon;
    // مقارنة تقويميّة محلّيّة (F5-12): كان `new Date(recommended_date) < new Date()`
    // يقارن تاريخاً بلا وقت (يُفسَّر UTC منتصف الليل) بلحظةٍ راهنة، فتصير مهمّة «اليوم»
    // متأخّرةً عند منتصف ليل UTC لا بعد مهلتها. نقارن تاريخ التقويم المحلّيّ نصّيّاً:
    // متأخّرة فقط إن كان تاريخها يوماً محلّيّاً سابقاً.
    const todayLocal = new Date().toLocaleDateString('en-CA'); // YYYY-MM-DD محلّيّ
    const isOld = !!task.recommended_date && task.recommended_date.slice(0, 10) < todayLocal && task.status === 'pending';

    return (
      <Card key={`${tenantId}:${task.task_id}`} style={{ border: `1px solid ${isOld ? T.danger : T.line}` }}>
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: `${cfg.color}22` }}>
            <Icon className="w-5 h-5" style={{ color: cfg.color }} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-0.5 flex-wrap">
              <span className="font-semibold text-sm" style={{ color: T.ink }}>{cfg.label}</span>
              <Pill tone={taskStatusTone(task.status)}>{taskStatusAr(task.status)}</Pill>
              <span className="text-[10px]" style={{ color: T.faint }}>أولوية: {PRIORITY_MAP[task.priority] || task.priority}</span>
              {isOld && <span className="text-[10px] flex items-center gap-0.5" style={{ color: T.danger }}><AlertTriangle className="w-3 h-3" /> متأخرة</span>}
            </div>
            <div className="text-xs mb-1" style={{ color: T.muted }}>{task.field_name || task.field_id}</div>
            <div className="text-xs mb-1" style={{ color: T.muted }}>
              معرّف المهمة <code dir="ltr" className="select-all">{task.task_id}</code>
            </div>
            {task.field_id && <button type="button" onClick={() => setObservationTask(task)} className="my-2 rounded border px-3 py-1 text-sm">مشاهدات الري والفحص</button>}
            {task.source_scouting_pin_id && <InspectionHandoff fieldId={task.field_id} taskId={task.task_id} />}
            {task.notes && <p className="text-xs leading-relaxed mb-2" style={{ color: T.brownSoft }}>{task.notes}</p>}
            <div className="flex flex-wrap items-center gap-3 text-[11px]" style={{ color: T.faint }}>
              {task.recommended_date && <span className="flex items-center gap-1"><Calendar className="w-3 h-3" />{task.recommended_date}</span>}
              {task.estimated_duration_min != null && <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{task.estimated_duration_min} دقيقة</span>}
              {task.estimated_cost_usd != null && <span className="flex items-center gap-1" style={{ color: T.gold }}>التقدير: ${task.estimated_cost_usd}</span>}
              {canViewCosts && task.actual_cost_usd != null && <span>التكلفة الفعلية: ${task.actual_cost_usd}</span>}
            </div>
            {canViewCosts && tenantId && <TaskCostTrace key={user?.email} taskId={task.task_id} fieldId={task.field_id}
              tenant={tenantId} subject={user?.email ?? ''} amount={task.actual_cost_usd} canRecord={canRecordCost} />}
            {!canViewCosts && canRecordCost && <p className="my-2 text-sm"><TaskExpenseLink taskId={task.task_id} fieldId={task.field_id} /></p>}
            {task.photo_url && (
              <div className="mt-2">
                <img src={task.photo_url} alt="معاينة" loading="lazy" decoding="async" className="h-20 rounded-lg object-cover" />
                {task.photo_url.startsWith('blob:') && (
                  <div className="text-[10px] mt-0.5" style={{ color: T.faint }}>معاينة محلّيّة — لم تُرفَع بعد</div>
                )}
              </div>
            )}
          </div>
          {mutateAllowed && task.status !== 'cancelled' && (
            <div className="flex flex-col gap-1.5 shrink-0">
              {task.status === 'pending' && (
                <Button tone="gold" full={false} onClick={() => startTask(task.task_id)}
                  style={{ padding: '6px 12px', fontSize: 11, fontWeight: 700 }}>
                  بدء
                </Button>
              )}
              <form key={task.status} className="grid gap-1.5" onSubmit={event => {
                event.preventDefault();
                const input = event.currentTarget.elements.namedItem('actualCost') as HTMLInputElement;
                if (!input.reportValidity()) return;
                void completeTask(task.task_id, input.value === '' ? undefined : input.valueAsNumber);
              }}>
                <label className="grid gap-1 text-xs">
                  التكلفة الفعلية بالدولار {task.status !== 'completed' && '(اختياري)'}
                  <input name="actualCost" required={task.status === 'completed'} type="number" min="0" max="99999999.99" step="0.01"
                    placeholder={task.actual_cost_usd?.toString()} className="w-28 rounded border px-2 py-1" />
                </label>
                <button type="submit" disabled={completing !== null}
                  className="inline-flex items-center justify-center gap-1 rounded px-3 py-1.5 text-xs font-bold"
                  style={{ background: T.green, color: '#fff' }}>
                  {completing === task.task_id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                  {task.status === 'completed' ? 'حفظ تصحيح التكلفة' : 'إنجاز'}
                </button>
              </form>
              {task.status !== 'completed' && <label className="flex items-center justify-center gap-1 cursor-pointer"
                style={{ padding: '6px 12px', borderRadius: RADIUS.md, border: `1px solid ${T.line}`, color: T.muted, fontSize: 11, fontWeight: 700 }}>
                <Camera className="w-3 h-3" /> صورة
                <input type="file" accept="image/*" className="hidden"
                  onChange={e => e.target.files?.[0] && handlePhotoUpload(task.task_id, e.target.files[0])} />
              </label>}
            </div>
          )}
          {task.status === 'completed' && <CheckCircle className="w-5 h-5 shrink-0 mt-1" style={{ color: T.ok }} />}
        </div>
      </Card>
    );
  };

  if (isLoading) return <LoadingState message="جارٍ تحميل المهام…" />;
  if (isError) return <ErrorState title="تعذّر تحميل المهام" onRetry={() => refetch()} />;

  return (
    <div className="space-y-5 max-w-4xl mx-auto" dir="rtl">
      <div className="flex flex-wrap items-center gap-3 justify-between">
        <div>
          <h2 className="text-xl font-bold" style={{ color: T.ink }}>المهام الميدانية</h2>
          <p className="text-sm" style={{ color: T.muted }}>مُنشأة تلقائياً من وكلاء الري والتسميد والمكافحة</p>
        </div>
        <button onClick={() => refetch()}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm"
          style={{ border: `1px solid ${T.line}`, color: T.muted }}>
          <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} /> تحديث
        </button>
      </div>

      <div className="flex flex-wrap gap-2 items-end">
        {statusTypes.map(s => {
          const active = filter === s;
          // النغمات الدافئة من DS: all = ذهبيّ، والبقيّة عبر taskStatusTone.
          const { fg, bg } = s === 'all' ? { fg: T.gold, bg: T.warnBg } : toneColors(taskStatusTone(s));
          const cnt = counts[s as keyof typeof counts] ?? 0;
          return (
            <button key={s} onClick={() => setFilter(s)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-all"
              style={{ background: active ? bg : T.card, border: `1px solid ${active ? fg : T.line}`, color: active ? fg : T.muted }}>
              {s === 'all' ? 'الكل' : taskStatusAr(s)}
              <span className="text-[11px] px-1.5 rounded-full" style={{ background: active ? `${fg}22` : T.card2, color: active ? fg : T.muted }}>{cnt}</span>
            </button>
          );
        })}
        <div className="mr-auto" style={{ minWidth: 160 }}>
          <Select
            value={typeFilter}
            onChange={v => setTypeFilter(v)}
            options={[
              { value: 'all', label: 'كل الأنواع' },
              ...Object.entries(TASK_CONFIG).map(([k, v]) => ({ value: k, label: v.label })),
            ]}
          />
        </div>
      </div>

      {observationTask && <TaskIrrigationObservationPanel key={`${tenantId}:${user?.id ?? user?.email}:${observationTask.task_id}`} taskId={observationTask.task_id} fieldId={observationTask.field_id} onClose={() => setObservationTask(null)} />}
      <div className="space-y-3">
        {filtered.map(renderTaskCard)}
        {filtered.length === 0 && (
          <EmptyState
            icon={<CheckCircle className="w-10 h-10 text-emerald-700" />}
            title={filter === 'completed' ? 'لا توجد مهام منجزة' : 'لا توجد مهام في هذه الفئة 🎉'}
            hint={apiTasks.length === 0 ? 'لا مهام واردة من الخدمة حاليّاً' : undefined}
          />
        )}
      </div>
    </div>
  );
}
