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

  it('reads a malformed payload as absent instead of passing it on', () => {
    const s = buildSoilWorkspaceSummary(
      {
        profile_hash: 42,
        evidence_level: 'trust_me',
        allowed_use: ['irrigation_scheduling', 7, null],
        blocked_use: 'gypsum_rate',
        quality_gate: ['passed'],
        conflicts: 'ph',
      },
      {executions: 'many', learning: [null, {eligible_for_training: true}]},
    );
    expect(s.profileHash).toBe('');
    expect(s.evidenceLevel).toBe('baseline_only');
    expect(s.allowedUse).toEqual(['irrigation_scheduling']);
    expect(s.blockedUse).toEqual([]);
    expect(s.qualityGate).toEqual({passed: false, executable: false, reasons: []});
    expect(s.conflicts).toEqual([]);
    expect(s.closedLoop.executions).toBe(0);
    expect(s.closedLoop.learning).toBe(2);
    expect(s.closedLoop.learningEligibleForTraining).toBe(1);
  });

  it('keeps every evidence level the contract defines', () => {
    for (const level of [
      'baseline_only',
      'modelled',
      'analog_guided',
      'field_observed',
      'lab_verified',
      'operational_verified',
    ]) {
      expect(buildSoilWorkspaceSummary({evidence_level: level}, null).evidenceLevel).toBe(level);
    }
  });

  it('reads a missing profile or closed loop as empty', () => {
    const s = buildSoilWorkspaceSummary(null, undefined);
    expect(s.completenessPct).toBe(0);
    expect(s.closedLoop.executions).toBe(0);
  });
});
