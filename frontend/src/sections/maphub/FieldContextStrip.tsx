import { MapPin, Sprout, Layers, CalendarDays } from 'lucide-react';

const T = {
  card: 'rgba(15,23,42,0.72)',
  line: 'rgba(148,163,184,0.22)',
  ink: '#e5e7eb',
  muted: '#94a3b8',
  ok: '#22c55e',
  warn: '#f59e0b',
};

export type FieldContextStripProps = {
  fieldId: string | null | undefined;
  fieldName: string | null | undefined;
  cropName?: string | null;
  activeSeasonId?: string | null;
  activeLayerId?: string | null;
};

/**
 * UI-9 seam: makes field_id + season_id visible in the map operating surface.
 * This avoids hidden context drift while Field Workspace is being extracted.
 */
export function FieldContextStrip({ fieldId, fieldName, cropName, activeSeasonId, activeLayerId }: FieldContextStripProps) {
  if (!fieldId) return null;
  return (
    <div
      data-testid="maphub-field-context-strip"
      data-sahool-region="field-context"
      className="mb-3 grid grid-cols-1 gap-2 rounded-2xl border p-3 md:grid-cols-4"
      style={{ background: T.card, borderColor: T.line, color: T.ink }}
    >
      <div className="flex items-center gap-2 text-xs">
        <MapPin className="h-4 w-4" style={{ color: T.ok }} />
        <span className="font-semibold">{fieldName || fieldId}</span>
      </div>
      <div className="flex items-center gap-2 text-xs" style={{ color: T.muted }}>
        <Sprout className="h-4 w-4" />
        <span>{cropName || 'محصول غير محدد'}</span>
      </div>
      <div className="flex items-center gap-2 text-xs" style={{ color: activeSeasonId ? T.ok : T.warn }}>
        <CalendarDays className="h-4 w-4" />
        <span>{activeSeasonId ? `season_id: ${activeSeasonId}` : 'لا موسم نشط'}</span>
      </div>
      <div className="flex items-center gap-2 text-xs" style={{ color: T.muted }}>
        <Layers className="h-4 w-4" />
        <span>{activeLayerId ? `layer: ${activeLayerId}` : 'صورة الحقل الخام'}</span>
      </div>
    </div>
  );
}
