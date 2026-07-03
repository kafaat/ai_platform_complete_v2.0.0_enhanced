// useSelectedField — FieldView source-of-truth hook.
//
// It wraps useFieldOptions and binds the active field to the session-scoped
// FieldView store. It also supports a route/deep-link field id so screens can
// open /...?field_id=... without duplicating local selection logic.
import { useCallback, useEffect, useMemo } from 'react';
import { useFieldOptions } from './useFieldOptions';
import { FieldSelectionMeta, useFieldContextStore } from './useFieldContext';
import { resolveFieldViewSelection } from '../lib/fields';

export interface UseSelectedFieldOptions {
  routeFieldId?: string | null;
  autoSelect?: boolean;
}

export function useSelectedField(config: UseSelectedFieldOptions = {}) {
  const { routeFieldId = null, autoSelect = true } = config;
  const query = useFieldOptions();
  const options = query.options;
  const selectedFieldId = useFieldContextStore((s) => s.selectedFieldId);
  const selectedFieldName = useFieldContextStore((s) => s.selectedFieldName);
  const selectionSource = useFieldContextStore((s) => s.selectionSource);
  const selectedAt = useFieldContextStore((s) => s.selectedAt);
  const setSelectedField = useFieldContextStore((s) => s.setSelectedField);
  const clearSelectedField = useFieldContextStore((s) => s.clearSelectedField);

  const selection = useMemo(
    () => resolveFieldViewSelection({ options, storedFieldId: selectedFieldId, routeFieldId }),
    [options, selectedFieldId, routeFieldId],
  );

  const fieldId = selection.fieldId;
  const field = useMemo(() => options.find((o) => o.id === fieldId), [options, fieldId]);

  const setFieldId = useCallback((id: string | null, meta?: FieldSelectionMeta) => {
    const next = id ? String(id) : null;
    const nextField = next ? options.find((o) => o.id === next) : undefined;
    setSelectedField(next, {
      source: meta?.source ?? 'user',
      name: meta?.name ?? nextField?.name ?? null,
    });
  }, [options, setSelectedField]);

  // Converge the persisted FieldView store to the resolved live field. This
  // heals deleted/stale fields, respects valid route ids, and keeps empty states
  // honest when the user has no fields.
  useEffect(() => {
    if (!autoSelect) return;
    if (!options.length) {
      if (selectedFieldId) clearSelectedField();
      return;
    }
    if (!fieldId) return;
    if (fieldId !== selectedFieldId || selectedFieldName !== (field?.name ?? null)) {
      setSelectedField(fieldId, {
        source: selection.reason === 'route' ? 'route' : selection.reason === 'fallback' ? 'auto' : selectionSource,
        name: field?.name ?? null,
      });
    }
  }, [
    autoSelect,
    options.length,
    fieldId,
    field?.name,
    selectedFieldId,
    selectedFieldName,
    selection.reason,
    selectionSource,
    setSelectedField,
    clearSelectedField,
  ]);

  return {
    ...query,
    fieldId,
    field,
    setFieldId,
    clearFieldId: clearSelectedField,
    storedFieldId: selectedFieldId,
    selectedFieldName,
    selectionSource,
    selectedAt,
    selectionReason: selection.reason,
    routeFieldIsInvalid: selection.routeFieldIsInvalid,
    storedFieldIsInvalid: selection.storedFieldIsInvalid,
    hasFields: options.length > 0,
    isEmpty: !query.isLoading && !query.isError && options.length === 0,
  };
}
