// ═══════════════════════════════════════════════════════════════
// SAHOOL — كابينة المهام الموحّدة (Field Tasks Cabin) · شاشة دمج ثالثة
// ───────────────────────────────────────────────────────────────
// تصهر «المهام» (FieldView) مع نمط الكابينة المحمولة (Operations Center):
// شريط وجهات سفليّ (BottomTabBar) يفرز المهام بحالتها، ومسار خطوات (Stepper)
// يجسّد دورة حياة كلّ مهمّة من حالتها الحقيقيّة. يستهلك آخر لبنتَي دمج لم
// تُستعملا في شاشة بعد — فتكتمل تغطية المكوّنات العشرة عبر الشاشات.
// تجسيد UI_DESIGN_SPEC_UNIFIED.md §4 (كابينة المهام المحمولة).
//
// صدق البيانات: المهام من useTasks الحقيقيّة (kong /api/v1/tasks). موضع Stepper
// مشتقّ حرفيّاً من status (pending→1، in_progress→2، completed→3)؛ المُلغاة
// تُعرَض شارةً لا خطوةً مزيّفة. العدّ في StatGrid فعليّ. لا قيم ملفّقة: المدّة/
// الكلفة تُعرَض «—» إن غابت. الحالات (تحميل/فراغ/خطأ) صريحة. قراءة فقط (معاينة).
// ═══════════════════════════════════════════════════════════════
import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import {
  ListChecks, Clock, Loader, CheckCircle2, XCircle, Sprout, MapPin, Coins, Timer,
} from 'lucide-react';
import { useTasks, type Task } from '../hooks/useApi';
import {
  T, Card, Pill, Badge, SectionLabel, StatGrid, Stepper, BottomTabBar,
} from '../components/ds';

// ── وجهات الكابينة (فرز بالحالة) — يُعرَض في BottomTabBar السفليّ ──
type TabId = 'all' | 'pending' | 'in_progress' | 'completed';
const TABS: { id: TabId; label: string; icon: ReactNode }[] = [
  { id: 'all', label: 'الكلّ', icon: <ListChecks style={{ width: 14, height: 14 }} /> },
  { id: 'pending', label: 'مجدولة', icon: <Clock style={{ width: 14, height: 14 }} /> },
  { id: 'in_progress', label: 'جارية', icon: <Loader style={{ width: 14, height: 14 }} /> },
  { id: 'completed', label: 'مكتملة', icon: <CheckCircle2 style={{ width: 14, height: 14 }} /> },
];

const STEPS = ['مجدولة', 'جارية', 'مكتملة'];
// موضع المهمّة على المسار (1-based) من حالتها الحقيقيّة. المُلغاة بلا موضع.
function stepOf(status: Task['status']): number {
  if (status === 'completed') return 3;
  if (status === 'in_progress') return 2;
  return 1; // pending
}

const STATUS_AR: Record<string, string> = {
  pending: 'مجدولة', in_progress: 'جارية', completed: 'مكتملة', cancelled: 'ملغاة',
};
const statusTone = (s: string) =>
  s === 'completed' ? 'ok' : s === 'in_progress' ? 'warn' : s === 'cancelled' ? 'danger' : 'info';

// تنسيق تاريخ عربيّ مختصر (يتسامح مع القيم الغائبة/غير الصالحة → «—»).
function fmtDate(d?: string): string {
  if (!d) return '—';
  const t = new Date(d);
  return Number.isNaN(t.getTime()) ? '—' : t.toLocaleDateString('ar-SA', { day: 'numeric', month: 'long' });
}

// بطاقة مهمّة واحدة: مسار حالتها (Stepper) + بياناتها الحقيقيّة.
function TaskCard({ task }: { task: Task }) {
  const cancelled = task.status === 'cancelled';
  return (
    <Card pad={14} style={{ marginBottom: 10, opacity: cancelled ? 0.6 : 1 }}>
      <div className="flex items-center justify-between" style={{ marginBottom: 4 }}>
        <span style={{ fontWeight: 800, fontSize: 14, color: T.ink }}>{task.task_type || 'مهمّة'}</span>
        <Badge tone={statusTone(task.status)}>{STATUS_AR[task.status] ?? task.status}</Badge>
      </div>

      {task.field_name && (
        <div className="flex items-center gap-1" style={{ fontSize: 12, color: T.muted, marginBottom: 10 }}>
          <MapPin style={{ width: 12, height: 12 }} /> {task.field_name}
        </div>
      )}

      {/* مسار دورة الحياة — موضعه من الحالة الحقيقيّة (لا خطوة مزيّفة للمُلغاة) */}
      {cancelled ? (
        <div className="flex items-center gap-2" style={{ color: T.danger, fontSize: 13, padding: '6px 0' }}>
          <XCircle style={{ width: 16, height: 16 }} /> أُلغيت هذه المهمّة.
        </div>
      ) : (
        <div style={{ margin: '6px 0 10px' }}>
          <Stepper steps={STEPS} active={stepOf(task.status)} />
        </div>
      )}

      {/* بيانات حقيقيّة — تُعرَض «—» إن غابت (لا تلفيق) */}
      <div className="flex items-center gap-2" style={{ flexWrap: 'wrap' }}>
        <Pill tone="neutral" icon={<Clock style={{ width: 11, height: 11 }} />}>{fmtDate(task.recommended_date)}</Pill>
        <Pill tone="neutral" icon={<Timer style={{ width: 11, height: 11 }} />}>
          {typeof task.estimated_duration_min === 'number' ? `${task.estimated_duration_min} د` : '—'}
        </Pill>
        <Pill tone="neutral" icon={<Coins style={{ width: 11, height: 11 }} />}>
          {typeof task.estimated_cost_usd === 'number' ? `$${task.estimated_cost_usd}` : '—'}
        </Pill>
        {typeof task.priority === 'number' && (
          <Pill tone={task.priority >= 3 ? 'danger' : task.priority === 2 ? 'warn' : 'info'}>
            أولويّة {task.priority}
          </Pill>
        )}
      </div>
    </Card>
  );
}

export default function FieldTasksCabin() {
  const [tab, setTab] = useState<TabId>('all');
  const tasksQ = useTasks();

  const tasks: Task[] = useMemo(
    () => (Array.isArray(tasksQ.data?.tasks) ? tasksQ.data.tasks : []),
    [tasksQ.data],
  );

  // عدّ فعليّ لكلّ حالة (StatGrid + شارات).
  const counts = useMemo(() => {
    const c = { pending: 0, in_progress: 0, completed: 0, cancelled: 0 };
    for (const t of tasks) if (t.status in c) c[t.status as keyof typeof c] += 1;
    return c;
  }, [tasks]);

  const shown = tab === 'all' ? tasks : tasks.filter((t) => t.status === tab);

  return (
    <div dir="rtl" style={{ background: T.cream, minHeight: '100%', padding: 16 }}>
      <div
        style={{
          maxWidth: 420, margin: '0 auto', background: T.cream,
          borderRadius: 22, border: `1px solid ${T.line}`, overflow: 'hidden',
          boxShadow: '0 12px 40px rgba(44,26,14,.10)',
          display: 'flex', flexDirection: 'column', minHeight: 600,
        }}
      >
        {/* ── Header ── */}
        <div style={{ background: T.brown, color: '#fff', padding: '18px 16px 22px', flexShrink: 0 }}>
          <div className="flex items-center justify-between">
            <div>
              <div style={{ fontSize: 12, color: T.goldSoft }}>كابينة الميدان</div>
              <div style={{ fontSize: 18, fontWeight: 800 }}>المهام</div>
            </div>
            <Pill tone={tasks.length ? 'info' : 'ok'} icon={<ListChecks style={{ width: 12, height: 12 }} />}>
              {tasks.length} مهمّة
            </Pill>
          </div>
          <div style={{ fontSize: 11, color: '#D8C7B3', marginTop: 6 }}>
            مسار كلّ مهمّة من حالتها الحقيقيّة — kong /tasks
          </div>
        </div>

        {/* ── المحتوى القابل للتمرير ── */}
        <div style={{ padding: 14, flex: 1, overflowY: 'auto' }}>
          {/* نظرة سريعة (StatGrid) — عدّ فعليّ */}
          <Card pad={14} style={{ marginBottom: 10 }}>
            <SectionLabel action={<Badge tone={tasksQ.isLoading ? 'neutral' : tasksQ.isError ? 'danger' : 'ok'}>
              {tasksQ.isLoading ? 'تحميل…' : tasksQ.isError ? 'خطأ' : 'مباشر'}
            </Badge>}>
              نظرة المهام
            </SectionLabel>
            <StatGrid
              items={[
                { label: 'مجدولة', value: counts.pending, color: T.info, icon: <Clock style={{ width: 16, height: 16, color: T.info }} /> },
                { label: 'جارية', value: counts.in_progress, color: T.warn, icon: <Loader style={{ width: 16, height: 16, color: T.warn }} /> },
                { label: 'مكتملة', value: counts.completed, color: T.ok, icon: <CheckCircle2 style={{ width: 16, height: 16, color: T.ok }} /> },
                { label: 'ملغاة', value: counts.cancelled, color: counts.cancelled ? T.danger : T.muted, icon: <XCircle style={{ width: 16, height: 16, color: counts.cancelled ? T.danger : T.muted }} /> },
              ]}
            />
          </Card>

          {/* قائمة المهام المفلترة بالوجهة */}
          {tasksQ.isLoading ? (
            <div style={{ color: T.muted, fontSize: 13, padding: '16px 0', textAlign: 'center' }}>جارٍ تحميل المهام…</div>
          ) : tasksQ.isError ? (
            <div style={{ color: T.danger, fontSize: 13, padding: '16px 0', textAlign: 'center' }}>تعذّر تحميل المهام.</div>
          ) : tasks.length === 0 ? (
            <div className="flex flex-col items-center" style={{ color: T.muted, fontSize: 13, padding: '24px 0', gap: 8 }}>
              <Sprout style={{ width: 28, height: 28, color: T.faint }} />
              لا مهام مُسجّلة بعد.
            </div>
          ) : shown.length === 0 ? (
            <div style={{ color: T.muted, fontSize: 13, padding: '24px 0', textAlign: 'center' }}>
              لا مهام في وجهة «{TABS.find((x) => x.id === tab)?.label}».
            </div>
          ) : (
            shown.map((t) => <TaskCard key={t.task_id} task={t} />)
          )}
        </div>

        {/* ── شريط الوجهات السفليّ (فرز بالحالة) ── */}
        <BottomTabBar tabs={TABS} active={tab} onChange={setTab} />
      </div>

      <p style={{ textAlign: 'center', color: T.muted, fontSize: 11, marginTop: 14 }}>
        كابينة المهام الموحّدة — قائمة <code>/tasks</code> الحقيقيّة. موضع المسار مشتقّ من
        حالة المهمّة، والعدّ فعليّ. لا قيم ملفّقة (المدّة/الكلفة «—» إن غابت). الحالات صادقة.
      </p>
    </div>
  );
}
