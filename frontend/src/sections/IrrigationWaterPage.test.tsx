// IrrigationWaterPage contract (owner pilot report 2026-11-13, rounds 1 and 2):
// the page is a calculation that is not saved to a field. It sends no field_id,
// says so, and sends a water-source type (well/canal/mixed), never `field:<name>`.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router';

// If the page still read the selected field, it would get one here.
vi.mock('../hooks/useSelectedField', () => ({
  useSelectedField: () => ({ fieldId: 'fld_1', field: { id: 'fld_1', name: 'North block' } }),
}));
vi.mock('../components/FieldSelector', () => ({ default: () => <div>field-selector</div> }));

const mut = vi.hoisted(() => ({
  mutate: vi.fn(),
  isPending: false,
  isError: false,
  data: undefined as unknown,
}));
vi.mock('../hooks/useApi', () => ({ useWaterAnalysis: () => mut }));

import IrrigationWaterPage from './IrrigationWaterPage';

const renderPage = () => render(<MemoryRouter><IrrigationWaterPage /></MemoryRouter>);
const lastPayload = () =>
  mut.mutate.mock.calls[mut.mutate.mock.calls.length - 1]?.[0] as Record<string, unknown>;
const analyze = () => fireEvent.click(screen.getByRole('button', { name: /تحليل العيّنة/ }));

describe('IrrigationWaterPage', () => {
  beforeEach(() => {
    mut.mutate.mockReset();
    mut.data = undefined;
  });

  it('sends a water-source type and no field binding', () => {
    renderPage();
    analyze();
    const payload = lastPayload();
    expect(payload.source).toBe('well');
    expect(payload).not.toHaveProperty('field_id');
    expect(JSON.stringify(payload)).not.toContain('field:');
    expect(JSON.stringify(payload)).not.toContain('fld_1');
  });

  it('sends the water source the user picks', () => {
    renderPage();
    fireEvent.change(screen.getByLabelText('مصدر الماء'), { target: { value: 'canal' } });
    analyze();
    expect(lastPayload().source).toBe('canal');
  });

  it('offers only the backend water-source types', () => {
    renderPage();
    const options = Array.from(
      (screen.getByLabelText('مصدر الماء') as HTMLSelectElement).options,
    ).map(o => o.value);
    expect(options).toEqual(['well', 'canal', 'mixed']);
  });

  it('says the calculation is not saved to a field and shows no field selector', () => {
    renderPage();
    expect(screen.getByRole('note').textContent).toContain('لا تُحفظ النتيجة ولا تُربط بأيّ حقل');
    expect(screen.queryByText('field-selector')).toBeNull();
  });

  it('names an uncomputable index instead of calling it missing data', () => {
    mut.mutate.mockImplementation(() => {
      mut.data = {
        sample_id: 's', source: 'well', persisted: false,
        indices: { sar: null, rsc_meq_l: null, ec_dsm: 0.5, ph: null },
        classification: {
          salinity: { class: 'low' }, alkalinity_rsc: { class: null }, sodicity_sar: { class: null },
        },
        hazard_flags_ar: [], verdict: 'insufficient_data', suitable_ar: 'بيانات غير كافية للحكم العامّ',
        missing_inputs: [], data_complete: false,
        indices_not_computable: [
          { index: 'sar', reason: 'numeric_overflow', code: 'WATER-NUMERIC-OVERFLOW' },
        ],
      };
    });
    const { rerender } = renderPage();
    analyze();
    rerender(<MemoryRouter><IrrigationWaterPage /></MemoryRouter>);
    expect(screen.getByText(/مؤشّرات تعذّر حسابها \(ليست بيانات ناقصة\)/).textContent)
      .toContain('SAR: القيم تتجاوز نطاق الحساب العدديّ');
    expect(screen.getByText('نتيجة حساب غير محفوظة وغير مرتبطة بحقل.')).toBeTruthy();
  });
});
