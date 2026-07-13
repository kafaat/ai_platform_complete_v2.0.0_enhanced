import {blockedUseExplanation, buildSoilWorkspaceSummary} from './soilWorkspace';

// Mirrors the canonical soil-profile.v1 snapshot (shared/contracts/soil/profile.py):
// completeness_score in [0,1]; quality_gate = {passed, executable, reasons};
// conflicts is a list of objects; blocked_use/allowed_use are string lists.
const snapshot = {
  profile_hash: 'a'.repeat(64),
  evidence_level: 'lab_verified',
  completeness_score: 0.8,
  quality_gate: {passed: true, executable: false, reasons: ['drainage_unverified']},
  conflicts: [{property: 'ph', reason: 'lab_vs_modelled_divergence'}],
  allowed_use: ['irrigation_scheduling'],
  blocked_use: ['gypsum_rate'],
};

describe('soil workspace', () => {
  it('explains blocked action', () =>
    expect(
      blockedUseExplanation({
        actionType: 'gypsum_rate',
        allowed: false,
        reasons: ['approved_water_profile_required'],
        approvalRequirement: 'soil_specialist',
      }),
    ).toContain('approved_water'));

  it('derives completeness from the canonical completeness_score', () => {
    const s = buildSoilWorkspaceSummary(snapshot, {executions: []});
    expect(s.completenessPct).toBe(80);
    expect(s.profileHash).toBe('a'.repeat(64));
    expect(s.evidenceLevel).toBe('lab_verified');
    expect(s.blockedUse).toEqual(['gypsum_rate']);
  });

  it('surfaces the quality gate and summarizes object conflicts', () => {
    const s = buildSoilWorkspaceSummary(snapshot, {});
    expect(s.qualityGate).toEqual({passed: true, executable: false, reasons: ['drainage_unverified']});
    expect(s.conflicts).toEqual(['ph: lab_vs_modelled_divergence']);
  });

  it('counts closed-loop executions honestly (in-progress vs completed)', () => {
    const closedLoop = {
      executions: [{completed_at: '2026-07-01T00:00:00Z'}, {}, {}],
      verifications: [{}],
      outcomes: [{}],
      learning: [{eligible_for_training: true}, {eligible_for_training: false}],
    };
    const s = buildSoilWorkspaceSummary(snapshot, closedLoop, 5);
    expect(s.closedLoop.executions).toBe(3);
    expect(s.closedLoop.completedExecutions).toBe(1);
    expect(s.closedLoop.inProgressExecutions).toBe(2);
    expect(s.closedLoop.verifications).toBe(1);
    expect(s.closedLoop.outcomes).toBe(1);
    expect(s.closedLoop.learning).toBe(2);
    expect(s.closedLoop.learningEligibleForTraining).toBe(1);
    expect(s.historyCount).toBe(5);
  });

  it('falls back to 0% completeness when no score is present, without inventing data', () => {
    const s = buildSoilWorkspaceSummary({evidence_level: 'baseline_only'}, {});
    expect(s.completenessPct).toBe(0);
    expect(s.qualityGate.passed).toBe(false);
    expect(s.conflicts).toEqual([]);
  });
});
