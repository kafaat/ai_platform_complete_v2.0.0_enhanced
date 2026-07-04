import { ClipboardList, Tractor, AlertTriangle, ArrowRightCircle } from 'lucide-react';
import { buildOperationsSnapshot, type OperationsSnapshotInput, type OpsSeverity } from '../../lib/fieldOperations';
import { T } from '../ds';

const TONE: Record<OpsSeverity, { border: string; bg: string; fg: string }> = {
  ok: { border: '#14532d', bg: 'rgba(22,163,74,.08)', fg: '#86efac' },
  info: { border: '#1e3a8a', bg: 'rgba(59,130,246,.08)', fg: '#93c5fd' },
  warn: { border: '#854d0e', bg: 'rgba(245,158,11,.10)', fg: '#fcd34d' },
  critical: { border: '#7f1d1d', bg: 'rgba(239,68,68,.10)', fg: '#fca5a5' },
};

interface Props extends OperationsSnapshotInput {
  onOpenTasks?: () => void;
  onOpenAlerts?: () => void;
}

/** مركز العمليّات المصغّر: مهام · مهمّة تالية · معدّات · تنبيهات للحقل النشط. */
export default function OperationsCenterCard(props: Props) {
  const s = buildOperationsSnapshot(props);
  const tone = TONE[s.severity];
  return (
    <section
      className="mb-3 rounded-2xl border p-3"
      style={{ borderColor: tone.border, background: tone.bg }}
      data-testid="operations-center"
      aria-label="مركز العمليّات"
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <ClipboardList className="w-4 h-4" style={{ color: tone.fg }} aria-hidden="true" /> مركز العمليّات
        </span>
        <span className="text-[11px]" style={{ color: T.muted }}>{s.summary}</span>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <button
          type="button"
          onClick={props.onOpenTasks}
          disabled={!props.onOpenTasks}
          className="rounded-xl border p-2 text-right disabled:cursor-default"
          style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}
          data-testid="ops-tasks"
        >
          <div className="inline-flex items-center gap-1 text-[11px] font-bold" style={{ color: T.ink }}>
            <ClipboardList className="w-3.5 h-3.5" aria-hidden="true" /> المهام
          </div>
          <div className="text-lg font-extrabold" style={{ color: T.ink }}>{s.openTasks}</div>
          <div className="text-[10px]" style={{ color: s.overdueTasks ? '#fcd34d' : T.faint }}>
            {s.overdueTasks ? `${s.overdueTasks} متأخّرة` : 'لا متأخّرات'}
          </div>
        </button>

        <div className="rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }} data-testid="ops-equipment">
          <div className="inline-flex items-center gap-1 text-[11px] font-bold" style={{ color: T.ink }}>
            <Tractor className="w-3.5 h-3.5" aria-hidden="true" /> المعدّات
          </div>
          <div className="text-lg font-extrabold" style={{ color: T.ink }}>{s.equipment.ready}/{s.equipment.total}</div>
          <div className="text-[10px]" style={{ color: s.equipment.down ? '#fca5a5' : T.faint }}>
            {s.equipment.down ? `${s.equipment.down} متوقّفة` : 'جاهزة'}
          </div>
        </div>

        <button
          type="button"
          onClick={props.onOpenAlerts}
          disabled={!props.onOpenAlerts}
          className="rounded-xl border p-2 text-right disabled:cursor-default"
          style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}
          data-testid="ops-alerts"
        >
          <div className="inline-flex items-center gap-1 text-[11px] font-bold" style={{ color: T.ink }}>
            <AlertTriangle className="w-3.5 h-3.5" aria-hidden="true" /> التنبيهات
          </div>
          <div className="text-lg font-extrabold" style={{ color: T.ink }}>{s.activeAlerts}</div>
          <div className="text-[10px]" style={{ color: T.faint }}>نشِطة للحقل</div>
        </button>
      </div>

      {s.nextTask && (
        <div className="mt-2 inline-flex items-center gap-1 text-xs font-semibold" style={{ color: T.ink }}>
          <ArrowRightCircle className="w-3.5 h-3.5" style={{ color: tone.fg }} aria-hidden="true" />
          المهمّة التالية: {s.nextTask.label}
          {s.nextTask.overdue && <span style={{ color: '#fcd34d' }}> · متأخّرة</span>}
        </div>
      )}
    </section>
  );
}
