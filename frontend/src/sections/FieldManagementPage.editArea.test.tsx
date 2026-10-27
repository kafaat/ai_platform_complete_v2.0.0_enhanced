// ═══════════════════════════════════════════════════════════════
// G-AREA-3 (تدقيق RS 2026-10-27) — مساحة الحقل في «تعديل الحقل» مُشتقّة من الهندسة
// ───────────────────────────────────────────────────────────────
// كان المودال يعرض «المساحة (هـ)» كحقل رقميّ قابل للتحرير ويمرّر area_ha إلى onSave،
// بينما handleEditSave يرسل name/crop فقط (FieldUpdateRequest لا يقبل area_ha) ثمّ يعيد
// الجلب — فيرى المستخدم «تم تعديل الحقل» وقيمته مُهمَلة. المساحة تُشتقّ من الحدود في
// الخادم، فالتحكّم يجب أن يكون عرضاً للقراءة فقط ولا يُمرَّر area_ha في الحمولة.
// ═══════════════════════════════════════════════════════════════
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { EditFieldModal } from './FieldManagementPage';

type FieldProp = ComponentProps<typeof EditFieldModal>['field'];
const FIELD = {
  field_id: 'f-1', name: 'حقل الوادي', area_ha: 12.34, crop: 'قمح صلب', soil: '',
  ndvi: 0, health: 'fair', stage: '—', gdd: 0, yield_est: 0, lat: 15, lon: 44,
} as FieldProp;

describe('G-AREA-3 — EditFieldModal area is read-only, derived from geometry', () => {
  it('shows the area but offers no editable number input for it', () => {
    render(<EditFieldModal field={FIELD} onSave={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.queryByRole('spinbutton')).toBeNull();
    expect(screen.getByText(/12\.34/)).toBeInTheDocument();
    expect(screen.getByText(/تُحسَب المساحة من حدود الحقل/)).toBeInTheDocument();
  });

  it('onSave payload carries only the fields the PATCH actually persists (no area_ha)', () => {
    const onSave = vi.fn();
    render(<EditFieldModal field={FIELD} onSave={onSave} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /حفظ/ }));
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave.mock.calls[0][0]).toEqual({ name: 'حقل الوادي', crop: 'قمح صلب' });
  });
});
