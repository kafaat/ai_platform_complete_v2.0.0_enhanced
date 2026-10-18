import { beforeEach, describe, expect, it, vi } from 'vitest';
import { kongApi } from './client';
import { approveManualCandidate, createManualPlan, loadManualCandidates, manualPlanSource } from './irrigationManualCreation';
import type { DecisionReviewCandidate } from '../../lib/approvalsConsole';

vi.mock('./client', () => ({ kongApi: { get: vi.fn(), post: vi.fn() } }));
const candidate: DecisionReviewCandidate = {
  decision_id: 'd', field_id: 'f', stage: 'candidate', decision_type: 'irrigation', review_state: 'pending_approval',
  candidate_lineage_id: 'lineage', decision_value_digest: 'a'.repeat(64),
  decision_value: { season_id: 's', recommendation: { should_irrigate: true, target_refill_mm: 10 }, manual_execution_source: {
    field_id: 'f', season_id: 's', system_id: 'pivot', schema_version: 'manual-irrigation-source/v1', net_depth_mm: 10, target_depth_mm: 12.5, target_volume_m3: 125, application_efficiency: 0.8, irrigated_area_ha: 1, specification_digest: 'c'.repeat(64), specification: { evidence_level: 'user_declared', source_reference: 'field engineer', observed_at: '2026-01-01' }, water_truth: { canonical: { ledger_date: '2026-10-16', operational_eligible: true }, applied_water_status: 'recorded' },
    water_truth_digest: 'b'.repeat(64), valid_from: '2099-01-01T00:00:00Z', valid_until: '2099-01-02T00:00:00Z',
  } },
};

describe('manual irrigation authority boundary', () => {
  beforeEach(() => { vi.mocked(kongApi.get).mockReset(); vi.mocked(kongApi.post).mockReset(); });
  it.each([
    { target_volume_m3: null }, { target_volume_m3: 0 }, { target_depth_mm: true },
    { water_truth_digest: '' }, { field_id: 'foreign' }, { season_id: 'old' },
    { valid_until: '2020-01-01T00:00:00Z' }, { valid_from: 'unknown' },
  ])('does not build a plan from incomplete or mismatched input %j', overrides => {
    const bad = { ...candidate, decision_value: { ...candidate.decision_value, manual_execution_source: {
      ...(candidate.decision_value?.manual_execution_source as object), ...overrides,
    } } };
    expect(manualPlanSource(bad, 'f', 's')).toBeNull();
  });
  it('rejects a mirror queue instead of treating it as empty', async () => {
    vi.mocked(kongApi.get).mockResolvedValue({ data: { authoritative: false, persisted: false, count: 0, items: [] } });
    await expect(loadManualCandidates('f', 's')).rejects.toThrow();
  });
  it('never upgrades a rejected or mismatched review to approval', async () => {
    vi.mocked(kongApi.post).mockResolvedValue({ data: { state: 'rejected', decision_id: 'd', review_id: 'r' } });
    await expect(approveManualCandidate(candidate)).rejects.toThrow();
  });
  it('does not post a plan when the review digest differs', async () => {
    await expect(createManualPlan(candidate, { state: 'approved', previous_state: 'pending_approval', reviewed_by: 'r', reviewed_at: '2026-01-01', decision_id: 'd', review_id: 'r', candidate_lineage_id: 'lineage', decision_value_digest: 'c'.repeat(64) }, 'f', 's')).rejects.toThrow();
    expect(kongApi.post).not.toHaveBeenCalled();
  });
  it('checks the plan response identity before any execution may be created', async () => {
    vi.mocked(kongApi.post).mockResolvedValue({ data: { state: 'planned', execution_plan_id: 'plan-other', decision_id: 'other' } });
    await expect(createManualPlan(candidate, { state: 'approved', previous_state: 'pending_approval', reviewed_by: 'r', reviewed_at: '2026-01-01', decision_id: 'd', review_id: 'r', candidate_lineage_id: 'lineage', decision_value_digest: 'a'.repeat(64) }, 'f', 's')).rejects.toThrow();
  });
});
