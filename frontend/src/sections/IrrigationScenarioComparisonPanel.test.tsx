import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import IrrigationScenarioComparisonPanel from './IrrigationScenarioComparisonPanel';
import type { ManualExecutionRecord } from '../services/api/irrigationManualOperations';
import { kongApi } from '../services/api/client';

vi.mock('../services/api/client', () => ({ kongApi: { post: vi.fn() } }));

function record(id: string, overrides: Partial<ManualExecutionRecord> = {}): ManualExecutionRecord {
  return {
    execution_id: id, field_id: 'field-a', season_id: 'season-a', system_id: 'pivot-a',
    recommendation_id: `recommendation-${id}`, execution_mode: 'manual_measured', state: 'reconciled',
    target_depth_mm: 10, target_volume_m3: 100, nominal_flow_m3_h: 50,
    valid_from: '2026-10-01T00:00:00Z', valid_until: '2026-10-02T00:00:00Z',
    stopped_at: '2026-10-01T12:00:00Z',
    ledger_eligible: true, as_applied: { quality: 'measured_meter', actual_volume_m3: 100 },
    ...overrides,
  };
}

const response = {
  status: 'measured_comparison', baseline_execution_id: 'baseline', candidate_execution_id: 'candidate',
  water: { baseline_volume_m3: 100, candidate_volume_m3: 80, baseline_minus_candidate_m3: 20,
    baseline_depth_mm: 10, candidate_depth_mm: 9.9999, baseline_minus_candidate_mm: 0.0001 },
  runtime: { baseline_hours: 2, candidate_hours: null, baseline_minus_candidate_hours: null },
  causal_effect: { status: 'not_established' }, energy: { status: 'not_measured' },
  economics: { status: 'not_computed' }, reasons: [], warnings_ar: ['الطقس غير مضبوط.'],
};

function mount(executions = [record('baseline'), record('candidate'), record('third')]) {
  return render(<IrrigationScenarioComparisonPanel fieldId="field-a" seasonId="season-a" executions={executions} />);
}

function choosePair() {
  fireEvent.change(screen.getByRole('combobox', { name: 'تنفيذ خط الأساس' }), { target: { value: 'baseline' } });
  fireEvent.change(screen.getByRole('combobox', { name: 'التنفيذ المقارن' }), { target: { value: 'candidate' } });
}

describe('Irrigation scenario comparison', () => {
  beforeEach(() => { vi.mocked(kongApi.post).mockReset(); });

  it('requires two eligible measurements and excludes estimated, unverified and other-field records', () => {
    mount([record('baseline'), record('estimate', { execution_mode: 'manual_estimated' }),
      record('unverified', { state: 'confirmed' }), record('foreign', { field_id: 'field-b' }),
      record('other-season', { season_id: 'season-b' }), record('not-eligible', { ledger_eligible: false }),
      record('estimated-quality', { as_applied: { quality: 'estimated_nominal' } })]);
    expect(screen.getByText(/يلزم تنفيذان مؤهلان/)).toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(kongApi.post).not.toHaveBeenCalled();
  });

  it('submits identities only to the read-only outcome calculation, preserving missing measurements', async () => {
    vi.mocked(kongApi.post).mockResolvedValue({ data: { irrigation_comparison: response } });
    mount();
    expect(screen.getByRole('button', { name: 'حساب المقارنة' })).toBeDisabled();
    choosePair();
    const candidate = screen.getByRole('combobox', { name: 'التنفيذ المقارن' });
    expect(within(candidate).queryByRole('option', { name: /baseline/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'حساب المقارنة' }));
    await screen.findByText('مقارنة القياسات المسجلة');
    expect(kongApi.post).toHaveBeenCalledExactlyOnceWith('/api/v1/outcome/measure', {
      field_id: 'field-a', planned: {}, actual: {},
      irrigation_comparison: { baseline_execution_id: 'baseline', candidate_execution_id: 'candidate' },
    });
    const duration = screen.getByRole('row', { name: /مدة التشغيل/ });
    expect(within(duration).getAllByText('غير مقاس')).toHaveLength(2);
    const depth = screen.getByRole('row', { name: /عمق الري/ });
    expect(within(depth).getByText((0.0001).toLocaleString('ar-YE', { maximumFractionDigits: 4 })))
      .toBeInTheDocument();
    expect(screen.getByText(/القيمة الاقتصادية: غير محسوبة/)).toBeInTheDocument();
    expect(screen.getByText(/لا يثبت وفر المياه/)).toBeInTheDocument();
    expect(screen.getByText('الطقس غير مضبوط.')).toBeInTheDocument();
  });

  it('clears a calculated result when the selected pair changes', async () => {
    vi.mocked(kongApi.post).mockResolvedValue({ data: { irrigation_comparison: response } });
    mount(); choosePair(); fireEvent.click(screen.getByRole('button', { name: 'حساب المقارنة' }));
    await screen.findByText('مقارنة القياسات المسجلة');
    fireEvent.change(screen.getByRole('combobox', { name: 'التنفيذ المقارن' }), { target: { value: 'third' } });
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.queryByText('مقارنة القياسات المسجلة')).not.toBeInTheDocument();
  });

  it('scopes selections and results to the field and season, with readable dates', async () => {
    vi.mocked(kongApi.post).mockResolvedValue({ data: { irrigation_comparison: response } });
    const { rerender } = mount();
    expect(within(screen.getByRole('combobox', { name: 'تنفيذ خط الأساس' }))
      .getByRole('option', { name: /baseline/ })).toHaveTextContent('UTC');
    choosePair(); fireEvent.click(screen.getByRole('button', { name: 'حساب المقارنة' }));
    await screen.findByText('مقارنة القياسات المسجلة');
    rerender(<IrrigationScenarioComparisonPanel fieldId="field-b" seasonId="season-b"
      executions={[record('baseline', { field_id: 'field-b', season_id: 'season-b' }),
        record('candidate', { field_id: 'field-b', season_id: 'season-b' })]} />);
    expect(screen.getByRole('combobox', { name: 'تنفيذ خط الأساس' })).toHaveValue('');
    expect(screen.getByRole('combobox', { name: 'التنفيذ المقارن' })).toHaveValue('');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'حساب المقارنة' })).toBeDisabled();
  });

  it('shows insufficient evidence without displaying differences as zero', async () => {
    vi.mocked(kongApi.post).mockResolvedValue({ data: { irrigation_comparison: {
      ...response, status: 'needs_data', warnings_ar: ['المساحة غير متطابقة.'],
    } } });
    mount(); choosePair(); fireEvent.click(screen.getByRole('button', { name: 'حساب المقارنة' }));
    await screen.findByText('الأدلة غير كافية للمقارنة');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.getByText('المساحة غير متطابقة.')).toBeInTheDocument();
  });

  it('fails visibly on an unavailable or unauthorized comparison and makes no execution request', async () => {
    vi.mocked(kongApi.post).mockRejectedValue({ response: { status: 403 } });
    mount(); choosePair(); fireEvent.click(screen.getByRole('button', { name: 'حساب المقارنة' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('تعذر حساب المقارنة');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(kongApi.post).toHaveBeenCalledTimes(1);
    expect(vi.mocked(kongApi.post).mock.calls[0][0]).toBe('/api/v1/outcome/measure');
  });

  it('rejects a response for another execution pair', async () => {
    vi.mocked(kongApi.post).mockResolvedValue({ data: { irrigation_comparison: {
      ...response, baseline_execution_id: 'wrong-baseline',
    } } });
    mount(); choosePair(); fireEvent.click(screen.getByRole('button', { name: 'حساب المقارنة' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('تعذر حساب المقارنة');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });
});
