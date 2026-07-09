import { AlertTriangle, ClipboardList, Crosshair, History, MapPin, PlusCircle } from 'lucide-react';

const T = {
  card: 'rgba(15,23,42,0.72)',
  line: 'rgba(148,163,184,0.22)',
  ink: '#e5e7eb',
  muted: '#94a3b8',
  ok: '#22c55e',
  warn: '#f59e0b',
};

export type MapActionPaletteProps = {
  fieldId: string | null | undefined;
  canMutate: boolean;
  hasGeometry: boolean;
  hasActiveSeason: boolean;
  hasAlerts: boolean;
  hasTasks: boolean;
  onPinScouting: () => void;
  onOpenTimeline: () => void;
  onOpenAlerts: () => void;
  onAddField: () => void;
};

/**
 * UI-12 scaffold: every map signal should have an honest next action.
 * Buttons are disabled when the required context is missing; no invented actions,
 * no fabricated task creation, and no simulated backend writes are performed here.
 */
export function MapActionPalette({
  fieldId,
  canMutate,
  hasGeometry,
  hasActiveSeason,
  hasAlerts,
  hasTasks,
  onPinScouting,
  onOpenTimeline,
  onOpenAlerts,
  onAddField,
}: MapActionPaletteProps) {
  const fieldReady = Boolean(fieldId && hasGeometry);
  return (
    <section
      data-testid="maphub-action-from-map-palette"
      data-sahool-region="action-from-map"
      data-field-id={fieldId ?? ''}
      className="mb-3 rounded-2xl border p-3"
      style={{ background: T.card, borderColor: T.line, color: T.ink }}
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="inline-flex items-center gap-2 text-sm font-bold">
          <Crosshair className="h-4 w-4" style={{ color: T.ok }} /> إجراءات من الخريطة
        </div>
        <span className="text-[11px]" style={{ color: hasActiveSeason ? T.muted : T.warn }}>
          {hasActiveSeason ? 'موسم نشط متاح' : 'لا موسم نشط'}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <button
          type="button"
          onClick={onPinScouting}
          disabled={!canMutate || !fieldReady}
          className="inline-flex items-center justify-center gap-1 rounded-lg px-2 py-2 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-50"
          style={{ background: '#14532d', color: '#dcfce7', border: `1px solid ${T.line}` }}
          title="يفتح وضع تثبيت ملاحظة ميدانية على الخريطة"
        >
          <MapPin className="h-3.5 w-3.5" /> ملاحظة ميدانية
        </button>
        <button
          type="button"
          onClick={onOpenTimeline}
          disabled={!fieldReady}
          className="inline-flex items-center justify-center gap-1 rounded-lg px-2 py-2 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-50"
          style={{ background: '#1e293b', color: T.ink, border: `1px solid ${T.line}` }}
        >
          <History className="h-3.5 w-3.5" /> Timeline
        </button>
        <button
          type="button"
          onClick={onOpenAlerts}
          disabled={!hasAlerts}
          className="inline-flex items-center justify-center gap-1 rounded-lg px-2 py-2 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-50"
          style={{ background: '#451a03', color: '#fed7aa', border: `1px solid ${T.line}` }}
        >
          <AlertTriangle className="h-3.5 w-3.5" /> التنبيهات
        </button>
        <button
          type="button"
          onClick={onAddField}
          disabled={!canMutate}
          className="inline-flex items-center justify-center gap-1 rounded-lg px-2 py-2 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-50"
          style={{ background: '#0f172a', color: T.ink, border: `1px solid ${T.line}` }}
        >
          <PlusCircle className="h-3.5 w-3.5" /> حقل جديد
        </button>
      </div>
      <div className="mt-2 flex flex-wrap gap-2 text-[11px]" style={{ color: T.muted }}>
        <span><ClipboardList className="mr-1 inline h-3 w-3" />{hasTasks ? 'مهام مفتوحة متاحة' : 'لا مهام مفتوحة'}</span>
        {!fieldReady && <span style={{ color: T.warn }}>الإجراءات التشغيلية تحتاج field_id + هندسة حقل.</span>}
      </div>
    </section>
  );
}
