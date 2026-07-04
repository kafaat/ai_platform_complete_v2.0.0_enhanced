// Admin Runtime Console — يعكس مسارات التشغيل الإداريّة المُخزَّنة (readiness ·
// dead-letter events/outbox · security denials · offline queue · automation) في
// كونسول إدارة واحد. صدق: العدّادات من الخادم كما هي، DLQ>0 يُعرَض تنبيهاً لا
// يُخفى، وnote_ar الخادم تُعرَض، والصفحة مقصورة على owner/manager (canManage).

export interface ReadinessCheck {
  key: string;
  status: 'ok' | 'warn' | 'block' | string;
  detail_ar?: string | null;
}

export interface ReadinessReport {
  ready: boolean;
  is_production: boolean;
  blockers: string[];
  warnings: string[];
  checks: ReadinessCheck[];
}

export interface DeadLetterResponse {
  dead_letter: Record<string, unknown>[];
  total: number;
  note_ar?: string;
}

export interface SecurityDenialsResponse {
  denials: Record<string, unknown>[];
  summary: Record<string, unknown>;
}

export interface QueueStatusResponse {
  tenant_id: string;
  total_in_queue: number;
  by_status: Record<string, number>;
}

export interface AutomationRunsResponse {
  runs: Record<string, unknown>[];
  summary: Record<string, unknown>;
}

export interface ReadinessCounters {
  ok: number;
  warn: number;
  block: number;
}

/** عدّادات فحوص الجاهزيّة من قائمة الخادم — الحالات غير المعروفة تُحصى warn (حذر). */
export function readinessCounters(report: ReadinessReport | null | undefined): ReadinessCounters {
  const c: ReadinessCounters = { ok: 0, warn: 0, block: 0 };
  for (const check of report?.checks ?? []) {
    if (check.status === 'ok') c.ok += 1;
    else if (check.status === 'block') c.block += 1;
    else c.warn += 1;
  }
  return c;
}

export type DlqHealth = 'healthy' | 'attention' | 'unknown';

/** صحّة قوائم الموتى: أيّ total>0 ⇒ attention (توجيه الخادم نفسه: «نبّه لو total>0»). */
export function dlqHealth(
  events: DeadLetterResponse | null | undefined,
  outbox: DeadLetterResponse | null | undefined,
): DlqHealth {
  if (!events && !outbox) return 'unknown';
  const total = (events?.total ?? 0) + (outbox?.total ?? 0);
  return total > 0 ? 'attention' : 'healthy';
}

/** رقاقات by_status لقائمة offline — تُسقِط الأصفار (عرض ما هو موجود فعلاً). */
export function queueStatusChips(q: QueueStatusResponse | null | undefined): { status: string; count: number }[] {
  if (!q?.by_status) return [];
  return Object.entries(q.by_status)
    .filter(([, count]) => typeof count === 'number' && count > 0)
    .map(([status, count]) => ({ status, count }))
    .sort((a, b) => b.count - a.count);
}
