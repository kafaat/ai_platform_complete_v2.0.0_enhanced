// UI-W2: فشل حفظ الحقل يجب أن يصل إلى AddFieldWithMap (رفضٌ لا نجاح صامت)، وإلّا
// يمسح الابن مفتاح التكرار الثابت فتحمل إعادة المحاولة مفتاحاً جديداً (تكرار محتمل
// بعد مهلة التزم الخادم قبلها). نلتقط onSave الحقيقيّ الذي تمرّره الصفحة ونستدعيه.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';

const captured = vi.hoisted(() => ({ onSave: null as null | ((d: unknown) => Promise<void>) }));
const post = vi.hoisted(() => vi.fn());
const toastAdd = vi.hoisted(() => vi.fn());

vi.mock('../components/AddFieldWithMap', () => ({
  default: ({ onSave }: { onSave: (d: unknown) => Promise<void> }) => {
    captured.onSave = onSave;
    return <section aria-label="add-field-form" />;
  },
}));
vi.mock('../components/AddSeasonWithStages', () => ({ default: () => null }));
vi.mock('../components/FieldDetailPanel', () => ({ default: () => null }));
vi.mock('../components/fieldsetup/FieldSetupWizard', () => ({ default: () => null }));
vi.mock('../components/FieldIndicatorMap', () => ({ default: () => null }));
vi.mock('../services/api', async (orig) => {
  const real = await orig<typeof import('../services/api')>();
  return { ...real, kongApi: { ...real.kongApi, post } };
});
vi.mock('../services/websocket', () => ({ toastStore: { add: toastAdd } }));
vi.mock('../hooks/useApi', () => ({
  useFields: () => ({ data: { fields: [] }, isLoading: false, isError: false, refetch: vi.fn() }),
  useSimulateSeason: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false, isError: false, data: undefined }),
}));
vi.mock('../hooks/useAuth', () => ({ useAuthStore: () => ({ user: { role: 'owner' } }) }));
vi.mock('../lib/fieldMapView', () => ({ saveFieldMapView: vi.fn() }));

import FieldManagementPage from './FieldManagementPage';

const FIELD = {
  name: 'حقل', manager: 'م', crop: 'wheat', soil_type: 'loam',
  geometry: { type: 'Polygon', coordinates: [[[44, 15], [44.1, 15], [44.1, 15.1], [44, 15]]] },
  idempotency_key: 'field-create-key-1',
};

// نستدعي onSave داخل act (تحديثات الحالة) ونعيد نتيجته المُسوّاة للفحص.
async function callSave(): Promise<{ ok: true } | { ok: false; error: unknown }> {
  let outcome: { ok: true } | { ok: false; error: unknown } = { ok: true };
  await act(async () => {
    try {
      await captured.onSave!(FIELD);
    } catch (error) {
      outcome = { ok: false, error };
    }
  });
  return outcome;
}

function openAddField() {
  render(<FieldManagementPage />);
  fireEvent.click(screen.getByText('رسم حقل فقط'));
  expect(screen.getByRole('region', { name: 'add-field-form' })).toBeInTheDocument();
  expect(captured.onSave).toBeTypeOf('function');
}

beforeEach(() => {
  cleanup();
  captured.onSave = null;
  post.mockReset();
  toastAdd.mockReset();
});

describe('UI-W2: FieldManagementPage propagates field save failures', () => {
  it('rejects onSave when POST /api/v1/fields fails (so the child keeps its retry key)', async () => {
    const err = Object.assign(new Error('timeout'), { response: { status: 503, data: { detail: 'db down' } } });
    post.mockRejectedValueOnce(err);
    openAddField();
    expect(await callSave()).toEqual({ ok: false, error: err });
    // الإبلاغ بالتنبيه يبقى (لا ابتلاع، لا ازدواج صامت).
    expect(toastAdd).toHaveBeenCalledWith('error', expect.any(String), expect.any(String));
    // المفتاح يُرسَل ترويسةً لا في الجسم.
    expect(post).toHaveBeenCalledWith(
      '/api/v1/fields',
      expect.not.objectContaining({ idempotency_key: expect.anything() }),
      { headers: { 'Idempotency-Key': 'field-create-key-1' } },
    );
  });

  it('resolves onSave on success', async () => {
    post.mockResolvedValueOnce({ data: { field_id: 'f-1', name: 'حقل' } });
    openAddField();
    expect(await callSave()).toEqual({ ok: true });
  });
});
