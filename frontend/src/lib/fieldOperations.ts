// FieldView Operations Center Lite — مستوحى من John Deere Operations Center / Agworld:
// يربط الحقل النشط بحالة التشغيل — المهام المفتوحة · المهمّة التالية · حالة المعدّات ·
// التنبيهات — من بيانات حيّة فعليّة (tasks/equipment/alerts). لا اختلاق: المهامّ
// والتنبيهات تُرشَّح لهذا الحقل؛ المعدّات على مستوى المستأجِر (أسطول). غياب البيانات
// يظهر كأصفار حقيقيّة لا كتقدير.
export type OpsSeverity = 'ok' | 'info' | 'warn' | 'critical';

export interface OpsTask {
  field_id: string;
  task_type: string;
  priority: number;
  recommended_date: string;
  status: 'pending' | 'in_progress' | 'completed' | 'cancelled';
}

export interface OpsEquipment {
  status: string; // active | broken | maintenance | …
}

export interface OpsAlert {
  field_id: string | null;
  status: string;
}

export interface OperationsSnapshotInput {
  fieldId: string | null;
  tasks: OpsTask[];
  equipment: OpsEquipment[];
  alerts: OpsAlert[];
}

export interface OperationsSnapshot {
  openTasks: number;
  overdueTasks: number;
  nextTask: { label: string; overdue: boolean; status: string } | null;
  equipment: { total: number; ready: number; down: number };
  activeAlerts: number;
  severity: OpsSeverity;
  summary: string;
}

const TASK_LABELS: Record<string, string> = {
  scouting: 'استكشاف ميدانيّ',
  irrigation: 'ريّ',
  fertilization: 'تسميد',
  spraying: 'رشّ',
  harvest: 'حصاد',
  planting: 'زراعة',
  soil_sampling: 'أخذ عيّنات تربة',
  maintenance: 'صيانة',
};

function labelFor(taskType: string): string {
  return TASK_LABELS[taskType] ?? taskType;
}

function dateMs(s: string): number | null {
  const d = String(s ?? '').slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return null;
  const ms = Date.parse(`${d}T00:00:00Z`);
  return Number.isFinite(ms) ? ms : null;
}

export function buildOperationsSnapshot(input: OperationsSnapshotInput, nowMs = Date.now()): OperationsSnapshot {
  const fieldTasks = input.fieldId ? input.tasks.filter((t) => t.field_id === input.fieldId) : [];
  const open = fieldTasks.filter((t) => t.status === 'pending' || t.status === 'in_progress');
  const overdue = open.filter((t) => {
    const ms = dateMs(t.recommended_date);
    return t.status === 'pending' && ms != null && ms < nowMs;
  });

  // المهمّة التالية: أعلى أولويّة ثمّ أقرب تاريخ موصى.
  const next = [...open].sort((a, b) => {
    if (b.priority !== a.priority) return b.priority - a.priority;
    return (dateMs(a.recommended_date) ?? Infinity) - (dateMs(b.recommended_date) ?? Infinity);
  })[0];
  const nextTask = next
    ? {
        label: labelFor(next.task_type),
        overdue: next.status === 'pending' && (dateMs(next.recommended_date) ?? Infinity) < nowMs,
        status: next.status,
      }
    : null;

  const total = input.equipment.length;
  const down = input.equipment.filter((e) => e.status === 'broken' || e.status === 'maintenance').length;
  const ready = total - down;

  const activeAlerts = (input.fieldId
    ? input.alerts.filter((a) => a.field_id === input.fieldId)
    : input.alerts
  ).filter((a) => a.status === 'active').length;

  let severity: OpsSeverity = 'ok';
  if (activeAlerts >= 3 || overdue.length >= 3) severity = 'critical';
  else if (down > 0 || overdue.length > 0 || activeAlerts > 0) severity = 'warn';
  else if (open.length > 0) severity = 'info';

  const parts: string[] = [];
  parts.push(`${open.length} مهمّة مفتوحة`);
  if (overdue.length) parts.push(`${overdue.length} متأخّرة`);
  if (down) parts.push(`${down} معدّة متوقّفة`);
  if (activeAlerts) parts.push(`${activeAlerts} تنبيه`);
  const summary = input.fieldId ? parts.join(' · ') : 'اختر حقلاً لعرض حالة التشغيل.';

  return { openTasks: open.length, overdueTasks: overdue.length, nextTask, equipment: { total, ready, down }, activeAlerts, severity, summary };
}
