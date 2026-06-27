// ═══════════════════════════════════════════════════════════════
// SAHOOL — TasksPage (مربوطة ببيانات حيّة)
// كانت تبذُر MOCK_TASKS وتعرضها افتراضيّاً. الآن: مهام حيّة من useTasks (/tasks)،
// إنجاز فعليّ عبر useCompleteTask (PATCH)، حالات موحّدة (StateViews)، وأزرار
// محكومة بالدور (RBAC: المُشاهِد لا يُعدّل). لا تلفيق.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import {
  Loader2, Check, Camera, Clock, AlertTriangle,
  Wrench, Droplets, Sprout, Bug, Wheat, RefreshCw,
  CheckCircle, Calendar,
} from 'lucide-react';
import { kongApi } from '../services/api';
import { toastStore } from '../services/websocket';
import { useTasks, useCompleteTask } from '../hooks/useApi';
import { useAuthStore } from '../hooks/useAuth';
import { canMutate } from '../lib/permissions';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';
import { Card, Button, Pill } from '../components/ds/atoms';
import { Select } from '../components/ds/forms';
import { T, RADIUS, toneColors } from '../components/ds/tokens';
import { taskStatusAr, taskStatusTone } from '../components/ds/status';

interface Task {
  task_id:               string;
  field_id:              string;
  field_name?:           string;
  task_type:             string;
  priority:              number;
  recommended_date:      string;
  status:                'pending' | 'in_progress' | 'completed' | 'cancelled';
  estimated_duration_min:number;
  estimated_cost_usd:    number;
  notes?:                string;
  photo_url?:            string;
  assigned_to?:          string;
  tenant_id:             string;
}

const TASK_CONFIG: Record<string, { icon: typeof Wrench; label: string; color: string }> = {
  irrigation:    { icon: Droplets, label: 'ري',              color: '#3b82f6' },
  fertilization: { icon: Sprout,   label: 'تسميد',           color: '#16a34a' },
  spraying:      { icon: Bug,      label: 'رش مبيدات',       color: '#f97316' },
  harvest:       { icon: Wheat,    label: 'حصاد',            color: '#f59e0b' },
  scouting:      { icon: Wrench,   label: 'استكشاف',         color: '#8b5cf6' },
  soil_sampling: { icon: Wrench,   label: 'أخذ عينات تربة',  color: '#92400e' },
};

// حالات المهام (تسمية + نغمة) موحّدة عبر DS (status.ts/tokens.ts) بدل
// خريطة الألوان الداكنة المحلّيّة السابقة.

const PRIORITY_MAP: Record<number, string> = { 1: 'حرج', 2: 'عالٍ', 3: 'متوسط', 4: 'منخفض', 5: 'روتيني' };

export default function TasksPage() {
  const { user } = useAuthStore();
  const mutateAllowed = canMutate(user?.role);
  const { data, isLoading, isError, refetch, isFetching } = useTasks();
  const completeMut = useCompleteTask();

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

  const completeTask = async (taskId: string) => {
    if (!mutateAllowed) return;
    setCompleting(taskId);
    try {
      await completeMut.mutateAsync({ taskId }); // PATCH فعليّ
      setStatus(taskId, { status: 'completed' });
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
    // معاينة محلّيّة فقط (blob: غير صالح على الخادم). لا نُرسل الرابط المحلّيّ
    // كـphoto_url — الرفع الفعليّ للملفّ يحتاج endpoint multipart (مؤجَّل بصدق).
    const url = URL.createObjectURL(file);
    setStatus(taskId, { photo_url: url });
    void completeTask(taskId); // الإنجاز يُحفظ فعليّاً (بلا رابط blob زائف)
  };

  const TaskCard = ({ task }: { task: Task }) => {
    const cfg = TASK_CONFIG[task.task_type] || TASK_CONFIG.scouting;
    const Icon = cfg.icon;
    const isOld = new Date(task.recommended_date) < new Date() && task.status === 'pending';

    return (
      <Card style={{ border: `1px solid ${isOld ? T.danger : T.line}` }}>
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
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
            {task.notes && <p className="text-xs leading-relaxed mb-2" style={{ color: T.brownSoft }}>{task.notes}</p>}
            <div className="flex flex-wrap items-center gap-3 text-[11px]" style={{ color: T.faint }}>
              {task.recommended_date && <span className="flex items-center gap-1"><Calendar className="w-3 h-3" />{task.recommended_date}</span>}
              {task.estimated_duration_min != null && <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{task.estimated_duration_min} دقيقة</span>}
              {task.estimated_cost_usd != null && <span className="flex items-center gap-1" style={{ color: T.gold }}>${task.estimated_cost_usd}</span>}
            </div>
            {task.photo_url && <img src={task.photo_url} alt="توثيق" loading="lazy" decoding="async" className="mt-2 h-20 rounded-lg object-cover" />}
          </div>
          {mutateAllowed && task.status !== 'completed' && task.status !== 'cancelled' && (
            <div className="flex flex-col gap-1.5 flex-shrink-0">
              {task.status === 'pending' && (
                <Button tone="gold" full={false} onClick={() => startTask(task.task_id)}
                  style={{ padding: '6px 12px', fontSize: 11, fontWeight: 700 }}>
                  بدء
                </Button>
              )}
              <Button onClick={() => completeTask(task.task_id)} disabled={completing === task.task_id}
                full={false} style={{ padding: '6px 12px', fontSize: 11, fontWeight: 700, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
                {completing === task.task_id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                إنجاز
              </Button>
              <label className="flex items-center justify-center gap-1 cursor-pointer"
                style={{ padding: '6px 12px', borderRadius: RADIUS.md, border: `1px solid ${T.line}`, color: T.muted, fontSize: 11, fontWeight: 700 }}>
                <Camera className="w-3 h-3" /> صورة
                <input type="file" accept="image/*" className="hidden"
                  onChange={e => e.target.files?.[0] && handlePhotoUpload(task.task_id, e.target.files[0])} />
              </label>
            </div>
          )}
          {task.status === 'completed' && <CheckCircle className="w-5 h-5 flex-shrink-0 mt-1" style={{ color: T.ok }} />}
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

      <div className="space-y-3">
        {filtered.map(t => <TaskCard key={t.task_id} task={t} />)}
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
