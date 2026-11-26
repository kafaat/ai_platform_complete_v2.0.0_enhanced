// Interpret the server-owned fleet assessment; never derive service due from hours.
export interface EquipmentReadiness {
  readiness: 'unknown' | 'attention_required' | 'degraded' | 'ready';
  total: number;
  unavailable: number;
  coverage: number;
  assets: { id: string; name: string; status: 'due' | 'not_due' | 'not_evaluated'; basis: string | null; constraints: string[] }[];
}

const record = (value: unknown): Record<string, unknown> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid equipment summary');
  return value as Record<string, unknown>;
};
const count = (value: unknown): number => {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) throw new Error('Invalid equipment count');
  return value;
};

export function readEquipmentReadiness(payload: unknown): EquipmentReadiness {
  const envelope = record(payload);
  const summary = record(envelope.intelligence);
  if (summary.schema_version !== 'equipment_intelligence.v2' || !Array.isArray(envelope.assets) || !Array.isArray(summary.assessments)) {
    throw new Error('Unsupported equipment summary');
  }
  const readiness = summary.readiness;
  if (readiness !== 'unknown' && readiness !== 'attention_required' && readiness !== 'degraded' && readiness !== 'ready') {
    throw new Error('Invalid equipment readiness');
  }
  const names = new Map<string, string>();
  for (const value of envelope.assets) {
    const asset = record(value);
    if (typeof asset.equipment_id !== 'string' || !asset.equipment_id || typeof asset.name !== 'string' || names.has(asset.equipment_id)) throw new Error('Invalid equipment identity');
    names.set(asset.equipment_id, asset.name);
  }
  const seen = new Set<string>();
  const assets = summary.assessments.map((value: unknown): EquipmentReadiness["assets"][number] => {
    const assessment = record(value);
    const { asset_id: id, status, basis, constraints } = assessment;
    if (typeof id !== 'string' || !names.has(id) || seen.has(id) || (status !== 'due' && status !== 'not_due' && status !== 'not_evaluated') || (basis !== null && basis !== 'service_meter' && basis !== 'next_service_date') || !Array.isArray(constraints) || !constraints.every(c => typeof c === 'string')) {
      throw new Error('Invalid equipment assessment');
    }
    if ((status === 'not_evaluated') !== (basis === null)) throw new Error('Invalid equipment evidence basis');
    seen.add(id);
    return { id, name: names.get(id)!, status, basis, constraints: constraints as string[] };
  });
  const total = count(summary.total_assets);
  const unavailable = count(summary.unavailable);
  const coverage = summary.assessment_coverage;
  if (total !== names.size || total !== assets.length || unavailable > total || typeof coverage !== 'number' || !Number.isFinite(coverage) || coverage < 0 || coverage > 1) throw new Error('Inconsistent equipment summary');
  for (const [status, key] of [['due', 'service_due'], ['not_due', 'service_not_due'], ['not_evaluated', 'service_not_evaluated']] as const) {
    if (count(summary[key]) !== assets.filter(a => a.status === status).length) throw new Error('Inconsistent equipment assessments');
  }
  if ((total === 0 || assets.every(a => a.status === 'not_evaluated')) && (readiness !== 'unknown' || coverage !== 0)) throw new Error('Unsupported fleet readiness claim');
  return { readiness, total, unavailable, coverage, assets };
}
