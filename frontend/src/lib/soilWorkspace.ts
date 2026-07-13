// Soil governance workspace summary — maps the canonical soil-profile.v1 snapshot
// (shared/contracts/soil/profile.py) and the P4 closed-loop payload
// (soil-service GET /v1/fields/{id}/soil/closed-loop) into a read-only view model.
// Honest mapping: completeness comes from the snapshot's `completeness_score` (0..1),
// the quality gate is surfaced as-is (passed/executable/reasons), and closed-loop
// counters are derived from the real execution/verification/outcome/learning records.

export type SoilEvidenceLevel =
  | 'baseline_only'
  | 'modelled'
  | 'analog_guided'
  | 'field_observed'
  | 'lab_verified'
  | 'operational_verified';

export interface SoilQualityGateView {
  passed: boolean;
  executable: boolean;
  reasons: string[];
}

export interface SoilClosedLoopCounts {
  executions: number;
  inProgressExecutions: number; // executions with no completed_at
  completedExecutions: number;
  verifications: number;
  outcomes: number;
  learning: number;
  learningEligibleForTraining: number;
}

export interface SoilWorkspaceSummary {
  profileHash: string;
  evidenceLevel: SoilEvidenceLevel;
  completenessPct: number; // derived from snapshot.completeness_score (0..1)
  qualityGate: SoilQualityGateView;
  conflicts: string[]; // human-readable summaries of snapshot.conflicts (list of objects)
  allowedUse: string[];
  blockedUse: string[];
  historyCount: number; // length of the profile/history response, passed in by the caller
  closedLoop: SoilClosedLoopCounts;
}

export interface SoilActionPolicyView {
  actionType: string;
  allowed: boolean;
  reasons: string[];
  approvalRequirement: 'none' | 'agronomist' | 'soil_specialist' | 'engineer' | 'dual';
}

export function blockedUseExplanation(policy: SoilActionPolicyView): string {
  if (policy.allowed) return 'Allowed by current soil evidence';
  if (!policy.reasons.length) return 'Blocked until required soil evidence is available';
  return policy.reasons.join(', ');
}

function completenessPct(profile: any): number {
  // Canonical snapshot carries completeness_score in [0,1].
  const score = profile?.completeness_score;
  if (typeof score === 'number' && Number.isFinite(score)) {
    return Math.max(0, Math.min(100, Math.round(score * 100)));
  }
  // Tolerant fallback for any legacy/partial payload that exposes property counts.
  const gate = profile?.quality_gate ?? {};
  const completed = Number(gate.completed_properties ?? profile?.completed_properties);
  const required = Number(gate.required_properties ?? profile?.required_properties);
  if (Number.isFinite(completed) && Number.isFinite(required) && required > 0) {
    return Math.max(0, Math.min(100, Math.round((completed / required) * 100)));
  }
  return 0;
}

function conflictLabel(conflict: any): string {
  if (typeof conflict === 'string') return conflict;
  if (conflict && typeof conflict === 'object') {
    const prop = conflict.property ?? conflict.field ?? conflict.name;
    const reason = conflict.reason ?? conflict.type ?? conflict.detail;
    if (prop && reason) return `${prop}: ${reason}`;
    if (prop) return String(prop);
    if (reason) return String(reason);
  }
  return 'conflict';
}

function qualityGateView(profile: any): SoilQualityGateView {
  const gate = profile?.quality_gate ?? {};
  return {
    passed: Boolean(gate.passed),
    executable: Boolean(gate.executable),
    reasons: Array.isArray(gate.reasons) ? gate.reasons.map((r: any) => String(r)) : [],
  };
}

function closedLoopCounts(closedLoop: any): SoilClosedLoopCounts {
  const executions: any[] = Array.isArray(closedLoop?.executions) ? closedLoop.executions : [];
  const verifications: any[] = Array.isArray(closedLoop?.verifications)
    ? closedLoop.verifications
    : [];
  const outcomes: any[] = Array.isArray(closedLoop?.outcomes) ? closedLoop.outcomes : [];
  const learning: any[] = Array.isArray(closedLoop?.learning) ? closedLoop.learning : [];
  const completedExecutions = executions.filter((x) => x?.completed_at).length;
  return {
    executions: executions.length,
    inProgressExecutions: executions.length - completedExecutions,
    completedExecutions,
    verifications: verifications.length,
    outcomes: outcomes.length,
    learning: learning.length,
    learningEligibleForTraining: learning.filter((x) => x?.eligible_for_training).length,
  };
}

export function buildSoilWorkspaceSummary(
  profile: any,
  closedLoop: any,
  historyCount = 0,
): SoilWorkspaceSummary {
  const conflicts = Array.isArray(profile?.conflicts) ? profile.conflicts.map(conflictLabel) : [];
  return {
    profileHash: profile?.profile_hash ?? '',
    evidenceLevel: profile?.evidence_level ?? 'baseline_only',
    completenessPct: completenessPct(profile),
    qualityGate: qualityGateView(profile),
    conflicts,
    allowedUse: Array.isArray(profile?.allowed_use) ? profile.allowed_use : [],
    blockedUse: Array.isArray(profile?.blocked_use) ? profile.blocked_use : [],
    historyCount: Number.isFinite(Number(historyCount)) ? Number(historyCount) : 0,
    closedLoop: closedLoopCounts(closedLoop),
  };
}
