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

// The payloads arrive untyped (the hook passes `unknown`), so each field is narrowed where it is
// read instead of being asserted: a value of the wrong shape reads as absent, never as data.
type Payload = Record<string, unknown>;

const EVIDENCE_LEVELS: readonly SoilEvidenceLevel[] = [
  'baseline_only',
  'modelled',
  'analog_guided',
  'field_observed',
  'lab_verified',
  'operational_verified',
];

function asRecord(value: unknown): Payload {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Payload)
    : {};
}

function asList(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function asStrings(value: unknown): string[] {
  return asList(value).filter((item): item is string => typeof item === 'string');
}

function evidenceLevel(value: unknown): SoilEvidenceLevel {
  // The snapshot's evidence_level is a closed enum (shared/contracts/soil/profile.py); a value
  // outside it is not evidence, so it reads as the lowest level rather than being passed on.
  return EVIDENCE_LEVELS.find((level) => level === value) ?? 'baseline_only';
}

function completenessPct(profile: Payload): number {
  // Canonical snapshot carries completeness_score in [0,1].
  const score = profile.completeness_score;
  if (typeof score === 'number' && Number.isFinite(score)) {
    return Math.max(0, Math.min(100, Math.round(score * 100)));
  }
  // Tolerant fallback for any legacy/partial payload that exposes property counts.
  const gate = asRecord(profile.quality_gate);
  const completed = Number(gate.completed_properties ?? profile.completed_properties);
  const required = Number(gate.required_properties ?? profile.required_properties);
  if (Number.isFinite(completed) && Number.isFinite(required) && required > 0) {
    return Math.max(0, Math.min(100, Math.round((completed / required) * 100)));
  }
  return 0;
}

function conflictLabel(conflict: unknown): string {
  if (typeof conflict === 'string') return conflict;
  if (conflict && typeof conflict === 'object') {
    const c = conflict as Payload;
    const prop = c.property ?? c.field ?? c.name;
    const reason = c.reason ?? c.type ?? c.detail;
    if (prop && reason) return `${String(prop)}: ${String(reason)}`;
    if (prop) return String(prop);
    if (reason) return String(reason);
  }
  return 'conflict';
}

function qualityGateView(profile: Payload): SoilQualityGateView {
  const gate = asRecord(profile.quality_gate);
  return {
    passed: Boolean(gate.passed),
    executable: Boolean(gate.executable),
    reasons: asList(gate.reasons).map((r) => String(r)),
  };
}

function closedLoopCounts(closedLoop: Payload): SoilClosedLoopCounts {
  const executions = asList(closedLoop.executions);
  const learning = asList(closedLoop.learning);
  const completedExecutions = executions.filter((x) => asRecord(x).completed_at).length;
  return {
    executions: executions.length,
    inProgressExecutions: executions.length - completedExecutions,
    completedExecutions,
    verifications: asList(closedLoop.verifications).length,
    outcomes: asList(closedLoop.outcomes).length,
    learning: learning.length,
    learningEligibleForTraining: learning.filter((x) => asRecord(x).eligible_for_training).length,
  };
}

export function buildSoilWorkspaceSummary(
  profilePayload: unknown,
  closedLoopPayload: unknown,
  historyCount = 0,
): SoilWorkspaceSummary {
  const profile = asRecord(profilePayload);
  return {
    profileHash: typeof profile.profile_hash === 'string' ? profile.profile_hash : '',
    evidenceLevel: evidenceLevel(profile.evidence_level),
    completenessPct: completenessPct(profile),
    qualityGate: qualityGateView(profile),
    conflicts: asList(profile.conflicts).map(conflictLabel),
    allowedUse: asStrings(profile.allowed_use),
    blockedUse: asStrings(profile.blocked_use),
    historyCount: Number.isFinite(Number(historyCount)) ? Number(historyCount) : 0,
    closedLoop: closedLoopCounts(asRecord(closedLoopPayload)),
  };
}
