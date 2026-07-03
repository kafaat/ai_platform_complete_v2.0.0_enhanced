// ═══════════════════════════════════════════════════════════════
// SAHOOL — useFieldContext.ts («الحقل النشط» المشترك عبر الشاشات)
// ═══════════════════════════════════════════════════════════════
// FieldView source of truth. The selected field is session-scoped, validated
// against live field options by useSelectedField, and carries lightweight
// provenance so the UI can distinguish user choice, deep-link choice, and
// automatic fallback.
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

export type FieldSelectionSource = 'user' | 'route' | 'auto' | 'restore' | 'system';

export interface FieldSelectionMeta {
  source?: FieldSelectionSource;
  name?: string | null;
}

interface FieldContextState {
  selectedFieldId: string | null;
  selectedFieldName: string | null;
  selectionSource: FieldSelectionSource;
  selectedAt: number | null;
  // Actions
  setSelectedField: (id: string | null, meta?: FieldSelectionMeta) => void;
  clearSelectedField: () => void;
}

export const useFieldContextStore = create<FieldContextState>()(
  persist(
    (set) => ({
      selectedFieldId: null,
      selectedFieldName: null,
      selectionSource: 'restore',
      selectedAt: null,
      setSelectedField: (id: string | null, meta?: FieldSelectionMeta) => {
        const normalizedId = id ? String(id) : null;
        set({
          selectedFieldId: normalizedId,
          selectedFieldName: normalizedId ? (meta?.name ?? null) : null,
          selectionSource: meta?.source ?? 'user',
          selectedAt: normalizedId ? Date.now() : null,
        });
      },
      clearSelectedField: () => set({
        selectedFieldId: null,
        selectedFieldName: null,
        selectionSource: 'system',
        selectedAt: null,
      }),
    }),
    {
      name: 'sahool-field-context',
      // sessionStorage (not localStorage): the active field belongs to the current
      // browser session/tab and must not leak between accounts or long-lived sessions.
      storage: createJSONStorage(() => sessionStorage),
      partialize: (s) => ({
        selectedFieldId: s.selectedFieldId,
        selectedFieldName: s.selectedFieldName,
        selectionSource: s.selectionSource,
        selectedAt: s.selectedAt,
      }),
      version: 2,
    },
  ),
);
