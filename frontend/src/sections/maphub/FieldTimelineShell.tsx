import type { ReactNode } from 'react';

export type FieldTimelineKind = 'imagery' | 'operations' | 'learning';

export type FieldTimelineShellProps = {
  fieldId: string | null | undefined;
  activeSeasonId?: string | null;
  kind: FieldTimelineKind;
  visible: boolean;
  children: ReactNode;
};

/**
 * UI-11 seam: timeline boundary for imagery now, operations/learning later.
 * It deliberately does not synthesize timeline events; children remain the live
 * existing MapHub blocks until backend timeline endpoints are wired.
 */
export function FieldTimelineShell({ fieldId, activeSeasonId, kind, visible, children }: FieldTimelineShellProps) {
  if (!visible) return null;
  return (
    <section
      data-testid="maphub-field-timeline-shell"
      data-sahool-region="season-timeline"
      data-timeline-kind={kind}
      data-field-id={fieldId ?? ''}
      data-season-id={activeSeasonId ?? ''}
      aria-label="خط زمني تشغيلي للحقل"
    >
      {children}
    </section>
  );
}
