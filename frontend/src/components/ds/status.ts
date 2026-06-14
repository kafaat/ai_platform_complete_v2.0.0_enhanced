// status.ts — تسميات/نغمات الحالات الموحّدة (DS) — مصدر واحد للحقيقة.
// كانت خرائط حالات المهام/المعدّات تُعاد تعريفها في كلّ شاشة بصياغات متباينة
// (مثلاً pending = «معلّقة» مرّةً و«مجدولة» أخرى). وُحِّدت هنا فوق نظام النغمات.
import type { Tone } from './tokens';

// ── حالات المهام (pending|in_progress|completed|cancelled) ──
// pending = «مجدولة» (يطابق أوّل خطوة في مسار المهمّة Stepper).
export const TASK_STATUS_AR: Record<string, string> = {
  pending: 'مجدولة', in_progress: 'جارية', completed: 'مكتملة', cancelled: 'ملغاة',
};
export function taskStatusAr(status?: string): string {
  return TASK_STATUS_AR[(status ?? '').toLowerCase()] ?? (status || '—');
}
export function taskStatusTone(status?: string): Tone {
  const s = (status ?? '').toLowerCase();
  if (s === 'completed') return 'ok';
  if (s === 'in_progress') return 'warn';
  if (s === 'cancelled') return 'danger';
  return 'info'; // pending / غير معروف
}

// ── حالات المعدّات (active|operational|maintenance|broken|down) ──
export const EQUIP_STATUS_AR: Record<string, string> = {
  active: 'تعمل', operational: 'تعمل', maintenance: 'صيانة', broken: 'معطّلة', down: 'متوقّفة',
};
export function equipStatusAr(status?: string): string {
  return EQUIP_STATUS_AR[(status ?? '').toLowerCase()] ?? (status || '—');
}
export function equipStatusTone(status?: string): Tone {
  const s = (status ?? '').toLowerCase();
  if (s === 'active' || s === 'operational') return 'ok';
  if (s === 'maintenance') return 'warn';
  if (s === 'broken' || s === 'down') return 'danger';
  return 'neutral';
}
