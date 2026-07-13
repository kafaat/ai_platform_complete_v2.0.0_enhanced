export type SoilEvidenceLevel = 'baseline_only'|'modelled'|'analog_guided'|'field_observed'|'lab_verified'|'operational_verified';
export interface SoilWorkspaceSummary {
  profileHash: string;
  evidenceLevel: SoilEvidenceLevel;
  completenessPct: number;
  conflicts: string[];
  allowedUse: string[];
  blockedUse: string[];
  historyCount: number;
  pendingApprovals: number;
  latestExecutionStatus?: string;
}
export interface SoilActionPolicyView {
  actionType: string;
  allowed: boolean;
  reasons: string[];
  approvalRequirement: 'none'|'agronomist'|'soil_specialist'|'engineer'|'dual';
}
export function blockedUseExplanation(policy: SoilActionPolicyView): string {
  if (policy.allowed) return 'Allowed by current soil evidence';
  if (!policy.reasons.length) return 'Blocked until required soil evidence is available';
  return policy.reasons.join(', ');
}
export function buildSoilWorkspaceSummary(profile: any, closedLoop: any): SoilWorkspaceSummary {
  const gate = profile?.quality_gate ?? {};
  const completed = Number(gate.completed_properties ?? profile?.completed_properties ?? 0);
  const required = Math.max(1, Number(gate.required_properties ?? profile?.required_properties ?? 1));
  return {
    profileHash: profile?.profile_hash ?? '',
    evidenceLevel: profile?.evidence_level ?? 'baseline_only',
    completenessPct: Math.min(100, Math.round((completed / required) * 100)),
    conflicts: profile?.conflicts ?? [],
    allowedUse: profile?.allowed_use ?? [],
    blockedUse: profile?.blocked_use ?? [],
    historyCount: Number(profile?.history_count ?? 0),
    pendingApprovals: (closedLoop?.executions ?? []).filter((x:any)=>!x.completed_at).length,
    latestExecutionStatus: closedLoop?.executions?.[0]?.completed_at ? 'completed' : closedLoop?.executions?.length ? 'in_progress' : undefined,
  };
}
