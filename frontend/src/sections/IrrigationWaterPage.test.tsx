// IrrigationWaterPage contract (owner pilot report 2026-11-13, rounds 1 and 2):
// the page is a calculation that is not saved to a field. It sends no field_id,
// says so, and sends a water-source type (the seven of v168), never `field:<name>`.
// Owner decision 2026-11-14: a separate, explicit "حفظ كنتيجة مخبر لحقل" action stores the
// same measurement through the existing lab-water flow (a water sample of the picked field,
// then POST /api/v1/lab/water-results on that sample); the calculator path is unchanged.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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
const lab = vi.hoisted(() => ({
  createSample: vi.fn(),
  submitWater: vi.fn(),
  samples: [] as Record<string, unknown>[],
}));
vi.mock('../hooks/useApi', () => ({
  useWaterAnalysis: () => mut,
  useCreateLabSample: () => ({ mutateAsync: lab.createSample, isPending: false }),
  useLabSamples: (fieldId?: string) => ({ data: fieldId ? lab.samples : [] }),
}));
vi.mock('../hooks/useWaterFieldOps', () => ({
  useSubmitWaterLabResult: () => ({ mutateAsync: lab.submitWater, isPending: false }),
}));
vi.mock('../hooks/useFieldOptions', () => ({
  useFieldOptions: () => ({
    options: [
      { id: 'fld_7', name: 'Wadi plot', lat: 15.25, lon: 44.5, geometry: null, area: 1, crop: '' },
      { id: 'fld_9', name: 'No point', lat: null, lon: null, geometry: null, area: 1, crop: '' },
    ],
  }),
}));

import IrrigationWaterPage from './IrrigationWaterPage';

const renderPage = () => render(<MemoryRouter><IrrigationWaterPage /></MemoryRouter>);
const lastPayload = () =>
  mut.mutate.mock.calls[mut.mutate.mock.calls.length - 1]?.[0] as Record<string, unknown>;
const analyze = () => fireEvent.click(screen.getByRole('button', { name: /تحليل العيّنة/ }));

describe('IrrigationWaterPage', () => {
  beforeEach(() => {
    mut.mutate.mockReset();
    mut.data = undefined;
    lab.createSample.mockReset();
    lab.submitWater.mockReset();
    lab.samples = [];
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
    // v168 irrigation_water_sources.source_type, in its order; no 'mixed' (a blend is
    // several sources with v214 mixing ratios).
    expect(options).toEqual(['well', 'reservoir', 'canal', 'river', 'municipal', 'rainwater', 'other']);
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
  const showResult = (data: unknown) => {
    mut.mutate.mockImplementation(() => { mut.data = data; });
    const { rerender, container } = renderPage();
    analyze();
    rerender(<MemoryRouter><IrrigationWaterPage /></MemoryRouter>);
    return container;
  };
  const base = {
    sample_id: 's', source: 'well', persisted: false,
    indices: { sar: 14.14, rsc_meq_l: 2, ec_dsm: 2, ph: 7.4 },
    classification: {
      salinity: { class: 'moderate' }, alkalinity_rsc: { class: 'marginal' },
      sodicity_sar: { class: 'medium' }, infiltration_fao29: { class: 'slight_to_moderate' },
    },
    hazard_flags_ar: [], missing_inputs: [], data_complete: true,
  };

  it('shows the FAO-29 slight-to-moderate tier in amber with its reasons, not a green check', () => {
    const container = showResult({
      ...base,
      verdict: 'suitable_with_restrictions',
      suitable_ar: 'صالح مع قيود وإدارة: الملوحة: EC 2 dS/m — قيود طفيفة إلى متوسّطة',
      restriction_flags_ar: [
        'الملوحة: EC 2 dS/m — قيود طفيفة إلى متوسّطة',
        'القلويّة: RSC 2 meq/L — هامشي — إدارة ريّ جيّدة + مراقبة',
      ],
    });
    const box = screen.getByTestId('water-verdict');
    expect(box.getAttribute('data-verdict')).toBe('suitable_with_restrictions');
    expect(box.textContent).toContain('صالح مع قيود وإدارة');
    expect(box.textContent).not.toContain('صالح للريّ');
    const reasons = screen.getByRole('list', { name: 'قيود الاستعمال (FAO-29)' });
    expect(reasons.querySelectorAll('li')).toHaveLength(2);
    expect(reasons.textContent).toContain('RSC 2 meq/L');
    expect(container.querySelector('.text-emerald-400')).toBeNull();
    expect(container.querySelector('.text-amber-400')).not.toBeNull();
  });

  it('keeps the green check for water with no restriction', () => {
    const container = showResult({
      ...base, verdict: 'suitable', suitable_ar: 'صالح للريّ', restriction_flags_ar: [],
    });
    expect(screen.getByTestId('water-verdict').textContent).toContain('صالح للريّ');
    expect(container.querySelector('.text-emerald-400')).not.toBeNull();
    expect(screen.queryByRole('list', { name: 'قيود الاستعمال (FAO-29)' })).toBeNull();
  });
  // ── save as a lab result for a field ─────────────────────────────────────────
  const fill = (label: RegExp, value: string) =>
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  const openSave = () => fireEvent.click(screen.getByRole('button', { name: 'حفظ كنتيجة مخبر لحقل' }));
  const saveButton = () => screen.getByRole('button', { name: /حفظ النتيجة للحقل/ });

  it('sends a newly offered v168 source to the calculator', () => {
    renderPage();
    fireEvent.change(screen.getByLabelText('مصدر الماء'), { target: { value: 'rainwater' } });
    analyze();
    expect(lastPayload().source).toBe('rainwater');
  });

  it('saves the measurement for the picked field through the lab sample and water-result flow', async () => {
    lab.createSample.mockResolvedValue({ sample_id: 'w-new1', field_id: 'fld_7', kind: 'water', status: 'sampled' });
    lab.submitWater.mockResolvedValue({
      sample_id: 'w-new1', result_id: 'r-1', quality_status: 'unreviewed', verdict: 'suitable_with_restrictions',
    });
    renderPage();
    fill(/الصوديوم Na/, '4');
    fill(/التوصيليّة EC/, '1.2');
    fireEvent.change(screen.getByLabelText('مصدر الماء'), { target: { value: 'river' } });
    openSave();
    expect(saveButton()).toHaveProperty('disabled', true); // no field picked yet
    fireEvent.change(screen.getByLabelText('الحقل'), { target: { value: 'fld_7' } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(lab.submitWater).toHaveBeenCalledTimes(1));

    const sample = lab.createSample.mock.calls[0][0];
    expect(sample).toMatchObject({
      field_id: 'fld_7', kind: 'water', latitude: 15.25, longitude: 44.5, source: 'river', status: 'collected',
    });
    expect(typeof sample.idempotency_key).toBe('string');
    const result = lab.submitWater.mock.calls[0][0];
    expect(result).toMatchObject({ sample_id: 'w-new1', source: 'river', na: 4, ec_dsm: 1.2 });
    // The field binding is the sample; the water result carries no field_id.
    expect(result).not.toHaveProperty('field_id');
    // The calculator was not used for the save.
    expect(mut.mutate).not.toHaveBeenCalled();
    expect((await screen.findByRole('status')).textContent).toContain('بانتظار المراجعة');
    expect(screen.getByRole('status').textContent).toContain('صالح مع قيود');
    // The stored source type is the user's declaration, not a verified water source (R5).
    expect(screen.getByRole('status').textContent).toContain('«نهر» معلَن من المُدخِل وغير مُتحقَّق منه');
  });

  it('records on an open water sample of the field without creating another', async () => {
    lab.samples = [
      { sample_id: 'w-open', field_id: 'fld_7', kind: 'water', status: 'in_lab' },
      { sample_id: 'w-done', field_id: 'fld_7', kind: 'water', status: 'approved' },
      { sample_id: 's-soil', field_id: 'fld_7', kind: 'soil', status: 'sampled' },
    ];
    lab.submitWater.mockResolvedValue({ sample_id: 'w-open', result_id: 'r-2', quality_status: 'unreviewed' });
    renderPage();
    openSave();
    fireEvent.change(screen.getByLabelText('الحقل'), { target: { value: 'fld_7' } });
    const choices = Array.from((screen.getByLabelText('عيّنة الماء') as HTMLSelectElement).options).map(o => o.value);
    expect(choices).toEqual(['__new__', 'w-open']); // only water samples awaiting a first result
    fireEvent.change(screen.getByLabelText('عيّنة الماء'), { target: { value: 'w-open' } });
    fireEvent.click(saveButton());
    await waitFor(() => expect(lab.submitWater).toHaveBeenCalledTimes(1));
    expect(lab.createSample).not.toHaveBeenCalled();
    expect(lab.submitWater.mock.calls[0][0].sample_id).toBe('w-open');
  });

  it('asks for a sample location when the field has none', () => {
    renderPage();
    openSave();
    fireEvent.change(screen.getByLabelText('الحقل'), { target: { value: 'fld_9' } });
    expect(saveButton()).toHaveProperty('disabled', true);
    fill(/خط العرض/, '14.1');
    fill(/خط الطول/, '43.9');
    expect(saveButton()).toHaveProperty('disabled', false);
  });

  it('reuses the sample it created when the water result failed and the user retries', async () => {
    lab.createSample.mockResolvedValue({ sample_id: 'w-once', field_id: 'fld_7', kind: 'water', status: 'sampled' });
    lab.submitWater
      .mockRejectedValueOnce({ response: { status: 503, data: { detail: 'db down' } } })
      .mockResolvedValueOnce({ sample_id: 'w-once', result_id: 'r-3', quality_status: 'unreviewed' });
    renderPage();
    openSave();
    fireEvent.change(screen.getByLabelText('الحقل'), { target: { value: 'fld_7' } });
    fireEvent.click(saveButton());
    expect((await screen.findByRole('alert')).textContent).toContain('db down');
    fireEvent.click(saveButton());
    await waitFor(() => expect(lab.submitWater).toHaveBeenCalledTimes(2));
    expect(lab.createSample).toHaveBeenCalledTimes(1);
    expect(lab.submitWater.mock.calls[1][0].sample_id).toBe('w-once');
  });

  it('keeps the calculator free of the field picked for saving', () => {
    renderPage();
    openSave();
    fireEvent.change(screen.getByLabelText('الحقل'), { target: { value: 'fld_7' } });
    analyze();
    const payload = lastPayload();
    expect(payload).not.toHaveProperty('field_id');
    expect(JSON.stringify(payload)).not.toContain('fld_7');
    expect(lab.createSample).not.toHaveBeenCalled();
    expect(lab.submitWater).not.toHaveBeenCalled();
  });
});
