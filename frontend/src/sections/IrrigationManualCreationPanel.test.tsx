import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import IrrigationManualOperationsPanel from './IrrigationManualOperationsPanel';
import { kongApi } from '../services/api/client';

vi.mock('../services/api/client', () => ({ kongApi: { get: vi.fn(), post: vi.fn() } }));
vi.mock('./IrrigationScenarioComparisonPanel', () => ({ default: () => null }));

const candidate = {
  decision_id: 'dec-1', field_id: 'field-a', decision_type: 'irrigation', stage: 'candidate',
  review_state: 'pending_approval', candidate_lineage_id: 'lineage-1', decision_value_digest: 'd'.repeat(64),
  decision_value: { season_id: 'season-a', recommendation: { should_irrigate: true, target_refill_mm: 10 } },
};
function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><IrrigationManualOperationsPanel fieldId="field-a" seasonId="season-a" /></QueryClientProvider>);
}

describe('manual irrigation field workspace callers', () => {
  beforeEach(() => {
    vi.mocked(kongApi.post).mockReset();
    vi.mocked(kongApi.get).mockReset().mockImplementation(async (url) => ({ data: String(url).includes('review-queue')
      ? { authoritative: true, persisted: true, items: [candidate], count: 1 } : [] }));
  });

  it('submits only after the farmer clicks and reports a failed or blocked submission honestly', async () => {
    vi.mocked(kongApi.post).mockResolvedValue({ data: { status: 'dependency_unavailable', recommendation: null, limitations: ['weather_unavailable'] } });
    mount();
    const button = await screen.findByRole('button', { name: 'تقديم توصية الري للمراجعة' });
    expect(kongApi.post).not.toHaveBeenCalled();
    expect(button).toBeDisabled();
    const entries: Record<string, string> = { 'معرف نظام الري': 'system-1', 'المساحة المروية بالهكتار': '1', 'كفاءة التطبيق من صفر إلى واحد': '0.8', 'مرجع بيانات النظام والكفاءة': 'مهندس الري — تقرير الحقل', 'وقت توثيق البيانات': '2026-01-01T00:00', 'بداية فترة التشغيل': '2099-01-01T01:00', 'نهاية فترة التشغيل': '2099-01-01T03:00' };
    for (const [label, value] of Object.entries(entries)) fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.click(button);
    await screen.findByText('weather_unavailable');
    expect(kongApi.post).toHaveBeenCalledExactlyOnceWith('/api/v1/fields/field-a/irrigation-recommendation', expect.objectContaining({ submit_to_decision: true, manual_execution: expect.objectContaining({ system_id: 'system-1', application_efficiency: 0.8, irrigated_area_ha: 1 }) }));
    expect(screen.getByText(/لم تتوفر توصية قابلة للتقديم/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'إنشاء خطة الري' })).not.toBeInTheDocument();
  });

  it('does not manufacture missing water, system, volume or approval proof for the current producer', async () => {
    mount();
    await screen.findByText(/مصدر خطة التنفيذ غير مكتمل/);
    expect(screen.getByRole('button', { name: 'اعتماد هذه النسخة من التوصية' })).toBeDisabled();
    expect(kongApi.post).not.toHaveBeenCalled();
  });

  it('makes planning and record creation separate actions only for a complete server-source contract fixture', async () => {
    const complete = { ...candidate, decision_value: { ...candidate.decision_value, manual_execution_source: {
      field_id: 'field-a', season_id: 'season-a', system_id: 'system-1', schema_version: 'manual-irrigation-source/v1', net_depth_mm: 10, target_depth_mm: 12.5, target_volume_m3: 125, application_efficiency: 0.8, irrigated_area_ha: 1, specification_digest: 'c'.repeat(64), specification: { evidence_level: 'user_declared', source_reference: 'field engineer', observed_at: '2026-01-01' }, water_truth: { canonical: { ledger_date: '2026-10-16', operational_eligible: true }, applied_water_status: 'recorded' },
      water_truth_digest: 'a'.repeat(64), valid_from: '2099-01-01T01:00:00Z', valid_until: '2099-01-01T03:00:00Z',
    } } };
    vi.mocked(kongApi.get).mockImplementation(async url => ({ data: String(url).includes('review-queue')
      ? { authoritative: true, persisted: true, items: [complete], count: 1 } : [] }));
    vi.mocked(kongApi.post).mockImplementation(async url => ({ data: String(url).endsWith('/review')
      ? { state: 'approved', previous_state: 'pending_approval', decision_id: 'dec-1', review_id: 'review-1', candidate_lineage_id: 'lineage-1', decision_value_digest: 'd'.repeat(64), reviewed_by: 'reviewer', reviewed_at: '2026-10-16T00:00:00Z' }
      : String(url).endsWith('/execution-plan')
        ? { state: 'planned', execution_plan_id: 'plan-1', decision_id: 'dec-1', review_id: 'review-1', candidate_lineage_id: 'lineage-1', plan_digest: 'b'.repeat(64) }
        : { execution_id: 'exec-1', state: 'recommended', execution_plan_id: 'plan-1' } }));
    mount();
    fireEvent.click(await screen.findByRole('button', { name: 'اعتماد هذه النسخة من التوصية' }));
    const plan = await screen.findByRole('button', { name: 'إنشاء خطة الري' });
    expect(kongApi.post).toHaveBeenCalledTimes(1);
    fireEvent.click(plan);
    const create = await screen.findByRole('button', { name: 'إنشاء سجل تنفيذ ري يدوي' });
    expect(kongApi.post).toHaveBeenCalledTimes(2);
    fireEvent.click(create);
    await screen.findByText(/حُفظ سجل التنفيذ/);
    expect(kongApi.post).toHaveBeenCalledTimes(4);
    expect(kongApi.post).toHaveBeenLastCalledWith('/api/v1/irrigation/engineering/manual-executions', {
      execution_plan_id: 'plan-1', mode: 'manual_measured', idempotency_key: 'manual-execution:plan-1:manual_measured',
    });
    await waitFor(() => expect(create).toBeDisabled());
  });
});

function savedCandidate(withPlan = false) {
  return { ...candidate, review_state: 'approved',
    decision_value: { ...candidate.decision_value, manual_execution_source: {
      schema_version: 'manual-irrigation-source/v1', field_id: 'field-a', season_id: 'season-a', system_id: 'system-1',
      net_depth_mm: 10, target_depth_mm: 12.5, target_volume_m3: 125, application_efficiency: 0.8, irrigated_area_ha: 1,
      water_truth_digest: 'a'.repeat(64), specification_digest: 'c'.repeat(64),
      specification: { evidence_level: 'user_declared', source_reference: 'Survey 17', observed_at: '2026-01-01' },
      water_truth: { canonical: { ledger_date: '2026-10-16', operational_eligible: true }, applied_water_status: 'recorded' },
      valid_from: '2099-01-01T01:00:00Z', valid_until: '2099-01-01T03:00:00Z',
    } },
    review: { state: 'approved', previous_state: 'pending_approval', decision_id: 'dec-1', review_id: 'review-1', candidate_lineage_id: 'lineage-1', decision_value_digest: 'd'.repeat(64), reviewed_by: 'reviewer', reviewed_at: '2026-10-16T00:00:00Z' },
    execution_plan: withPlan ? { plan_state: 'planned', execution_plan_id: 'plan-1', decision_id: 'dec-1', review_id: 'review-1', candidate_lineage_id: 'lineage-1', decision_value_digest: 'd'.repeat(64), plan_digest: 'b'.repeat(64) } : null,
  };
}

describe('persisted irrigation workflow recovery', () => {
  beforeEach(() => { vi.mocked(kongApi.post).mockReset(); vi.mocked(kongApi.get).mockReset(); });
  it('restores approval from server on a fresh mount and displays declaration and net/gross distinctly', async () => {
    vi.mocked(kongApi.get).mockImplementation(async url => ({ data: String(url).includes('review-queue')
      ? { authoritative: true, persisted: true, items: [savedCandidate()], count: 1 } : [] }));
    mount();
    expect(await screen.findByRole('button', { name: 'إنشاء خطة الري' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: 'اعتماد هذه النسخة من التوصية' })).not.toBeInTheDocument();
    expect(screen.getByText(/ليست قياسًا متحققًا/)).toHaveTextContent('Survey 17');
    expect(screen.getByText(/الصافي: 10 مم/)).toHaveTextContent('الإجمالي: 12.5 مم');
    expect(kongApi.get).toHaveBeenCalledWith('/api/v1/decisions/review-queue', { params: { field_id: 'field-a', season_id: 'season-a' } });
    expect(kongApi.post).not.toHaveBeenCalled();
  });
  it('restores a saved plan, replays source persistence, then creates without duplicate approval', async () => {
    vi.mocked(kongApi.get).mockImplementation(async url => ({ data: String(url).includes('review-queue')
      ? { authoritative: true, persisted: true, items: [savedCandidate(true)], count: 1 } : [] }));
    vi.mocked(kongApi.post).mockImplementation(async url => ({ data: String(url).endsWith('/execution-plan')
      ? { state: 'planned', execution_plan_id: 'plan-1', decision_id: 'dec-1', review_id: 'review-1', candidate_lineage_id: 'lineage-1', plan_digest: 'b'.repeat(64) }
      : { execution_id: 'exec-1', state: 'approved', execution_plan_id: 'plan-1' } }));
    mount();
    fireEvent.click(await screen.findByRole('button', { name: 'إنشاء سجل تنفيذ ري يدوي' }));
    await screen.findByText(/حُفظ سجل التنفيذ/);
    expect(kongApi.post).toHaveBeenCalledTimes(2);
    expect(kongApi.post).toHaveBeenNthCalledWith(1, '/api/v1/decisions/dec-1/execution-plan', expect.objectContaining({
      idempotency_key: 'manual-plan:dec-1:review-1', constraints: expect.objectContaining({ net_depth_mm: 10, target_depth_mm: 12.5, target_volume_m3: 125, valid_from: '2099-01-01T01:00:00Z' }),
    }));
    expect(kongApi.post).toHaveBeenLastCalledWith('/api/v1/irrigation/engineering/manual-executions', expect.objectContaining({ execution_plan_id: 'plan-1' }));
  });
  it('does not create a manual record when recovery of the platform source fails', async () => {
    vi.mocked(kongApi.get).mockImplementation(async url => ({ data: String(url).includes('review-queue')
      ? { authoritative: true, persisted: true, items: [savedCandidate(true)], count: 1 } : [] }));
    vi.mocked(kongApi.post).mockRejectedValue(new Error('source save unavailable'));
    mount();
    fireEvent.click(await screen.findByRole('button', { name: 'إنشاء سجل تنفيذ ري يدوي' }));
    await screen.findByRole('alert');
    expect(kongApi.post).toHaveBeenCalledTimes(1);
    expect(kongApi.post).not.toHaveBeenCalledWith('/api/v1/irrigation/engineering/manual-executions', expect.anything());
  });
  it('reports a foreign plan replay conflict without creating a duplicate execution', async () => {
    vi.mocked(kongApi.get).mockImplementation(async url => ({ data: String(url).includes('review-queue')
      ? { authoritative: true, persisted: true, items: [savedCandidate(true)], count: 1 } : [] }));
    vi.mocked(kongApi.post).mockRejectedValue({ response: { status: 409, data: { detail: 'execution_plan_already_exists' } } });
    mount();
    fireEvent.click(await screen.findByRole('button', { name: 'إنشاء سجل تنفيذ ري يدوي' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('توجد خطة أنشئت من مسار آخر');
    expect(kongApi.post).toHaveBeenCalledTimes(1);
    expect(kongApi.post).not.toHaveBeenCalledWith('/api/v1/irrigation/engineering/manual-executions', expect.anything());
  });

});
