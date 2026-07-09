import type { ReactNode } from 'react';

export type FieldDrawerShellProps = {
  fieldId: string | null | undefined;
  open: boolean;
  children: ReactNode;
};

/**
 * UI-11 seam: isolates the drawer boundary without moving FieldDetailDrawer yet.
 * This keeps the current drawer behavior intact while making the field workspace
 * extraction point explicit and testable.
 */
export function FieldDrawerShell({ fieldId, open, children }: FieldDrawerShellProps) {
  return (
    <section
      data-testid="maphub-field-drawer-shell"
      data-sahool-region="field-drawer"
      data-field-id={fieldId ?? ''}
      data-open={open ? 'true' : 'false'}
      aria-label="درج تفاصيل الحقل"
    >
      {children}
    </section>
  );
}
