import { AlertTriangle, ListChecks } from 'lucide-react';

const T = {
  card: 'rgba(15,23,42,0.72)',
  line: 'rgba(148,163,184,0.22)',
  ink: '#e5e7eb',
  muted: '#94a3b8',
  warn: '#f59e0b',
};

export type PriorityQueuePanelProps = {
  fieldId: string | null | undefined;
  activeSeasonId?: string | null;
  hasAlerts: boolean;
  hasTasks: boolean;
  hasWeatherWindow: boolean;
};

/**
 * UI-10 seam: placeholder operating queue, not a fabricated dashboard.
 * Until the backend priority-queue endpoint is fully wired, it shows honest readiness
 * from already loaded UI signals and keeps the future queue contract visible.
 */
export function PriorityQueuePanel({ fieldId, activeSeasonId, hasAlerts, hasTasks, hasWeatherWindow }: PriorityQueuePanelProps) {
  if (!fieldId) return null;
  const availableSignals = [hasAlerts, hasTasks, hasWeatherWindow].filter(Boolean).length;
  return (
    <aside
      data-testid="maphub-priority-queue-panel"
      data-sahool-region="operational-priority-queue"
      className="mb-3 rounded-2xl border p-3"
      style={{ background: T.card, borderColor: T.line, color: T.ink }}
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="inline-flex items-center gap-2 text-sm font-bold">
          <ListChecks className="h-4 w-4" /> أولوية اليوم
        </div>
        <span className="rounded-full px-2 py-0.5 text-[11px]" style={{ border: `1px solid ${T.line}`, color: T.muted }}>
          {availableSignals}/3 مصادر جاهزة
        </span>
      </div>
      {activeSeasonId ? (
        <div className="grid grid-cols-1 gap-1 text-xs md:grid-cols-3" style={{ color: T.muted }}>
          <span>{hasAlerts ? 'تنبيهات متاحة للترتيب' : 'لا تنبيهات نشطة'}</span>
          <span>{hasTasks ? 'مهام متاحة للترتيب' : 'لا مهام مفتوحة'}</span>
          <span>{hasWeatherWindow ? 'نافذة طقس متاحة' : 'نافذة الطقس غير محسوبة'}</span>
        </div>
      ) : (
        <div className="inline-flex items-center gap-2 text-xs" style={{ color: T.warn }}>
          <AlertTriangle className="h-4 w-4" /> لا تُبنى أولوية تشغيلية كاملة بدون موسم نشط.
        </div>
      )}
    </aside>
  );
}
