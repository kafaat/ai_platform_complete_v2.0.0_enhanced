import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
const state = vi.hoisted(() => ({ data: { fields: [] as Record<string, unknown>[] }, refetch: vi.fn(), post: vi.fn(), patch: vi.fn(), importField: null as any }));
vi.mock('../components/AddFieldWithMap', () => ({ default: () => null }));
vi.mock('../components/AddSeasonWithStages', () => ({ default: () => null }));
vi.mock('../components/FieldDetailPanel', () => ({ default: () => null }));
vi.mock('../components/FieldIndicatorMap', () => ({ default: () => null }));
vi.mock('../components/fieldsetup/FieldSetupWizard', () => ({ default: (props: any) => { state.importField = props.onImportField; return null; } }));
vi.mock('../services/api', async original => ({ ...await original<typeof import('../services/api')>(), kongApi: { post: state.post, patch: state.patch } }));
vi.mock('../services/websocket', () => ({ toastStore: { add: vi.fn() } }));
vi.mock('../hooks/useApi', () => ({ useFields: () => ({ data: state.data, refetch: state.refetch, isLoading: false, isError: false }), useSimulateSeason: () => ({}) }));
vi.mock('../hooks/useAuth', () => ({ useAuthStore: () => ({ user: { role: 'owner' } }) }));
import FieldManagementPage, { mapField } from './FieldManagementPage';
beforeEach(() => { cleanup(); vi.clearAllMocks(); state.data = { fields: [{ field_id: 'f1', name_ar: 'الحقل القديم', crop: 'قمح صلب', area_ha: 2 }] }; state.refetch.mockResolvedValue({}); });
describe('source audit field repairs', () => {
  it('absent/invalid measurements stay unknown while real zero and negative NDVI are preserved', () => {
    expect(mapField({field_id:'f1'})).toMatchObject({ ndvi: null, health: 'unknown', gdd: null, yield_est: null });
    expect(mapField({ndvi:0}).ndvi).toBe(0);
    expect(mapField({ndvi:-0.2}).ndvi).toBe(-0.2);
    for (const ndvi of [NaN, Infinity, 2, '', null, true]) expect(mapField({ndvi}).ndvi).toBeNull();
  });
  it('replaces local rows when authoritative query data changes', async () => {
    const view = render(<FieldManagementPage />);
    expect(await screen.findByText('الحقل القديم')).toBeInTheDocument();
    state.data = { fields: [{ field_id:'f1', name_ar:'الحقل المحدث', crop:'بصل', area_ha:3 }] };
    view.rerender(<FieldManagementPage />);
    expect(await screen.findByText('الحقل المحدث')).toBeInTheDocument();
    expect(screen.queryByText('الحقل القديم')).not.toBeInTheDocument();
  });
  it('updates visible row from PATCH response even before the next list fetch', async () => {
    state.patch.mockResolvedValue({ data:{ field_id:'f1', name_ar:'اسم محفوظ', crop:'قمح صلب', area_ha:2 } });
    render(<FieldManagementPage />);
    fireEvent.click(await screen.findByRole('button',{name:'تعديل الحقل القديم'}));
    fireEvent.click(screen.getByRole('button',{name:'حفظ'}));
    expect(await screen.findByText('اسم محفوظ')).toBeInTheDocument();
    expect(state.patch).toHaveBeenCalledWith('/api/v1/fields/f1', expect.any(Object));
  });
  it('wizard import preserves stable retry key in the header, not request body', async () => {
    state.post.mockResolvedValue({data:{field_id:'new',name_ar:'مستورد'}});
    render(<FieldManagementPage />);
    fireEvent.click(screen.getByText(/تهيئة حقل جديد/));
    const payload={name:'مستورد',format:'geojson',content:'{}',idempotency_key:'stable-key'};
    await act(async()=>{await state.importField(payload);});
    expect(state.post).toHaveBeenCalledWith('/api/v1/fields/import', {name:'مستورد',format:'geojson',content:'{}'}, {headers:{'Idempotency-Key':'stable-key'}});
  });
});
