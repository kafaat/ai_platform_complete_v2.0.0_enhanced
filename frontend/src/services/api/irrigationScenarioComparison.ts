import { kongApi } from './client';

export interface IrrigationScenarioComparison {
  status: 'measured_comparison' | 'needs_data';
  baseline_execution_id: string;
  candidate_execution_id: string;
  water: {
    baseline_volume_m3: number | null;
    candidate_volume_m3: number | null;
    baseline_minus_candidate_m3: number | null;
    baseline_depth_mm: number | null;
    candidate_depth_mm: number | null;
    baseline_minus_candidate_mm: number | null;
  };
  runtime: {
    baseline_hours: number | null;
    candidate_hours: number | null;
    baseline_minus_candidate_hours: number | null;
  };
  causal_effect: { status: 'not_established' };
  energy: { status: 'not_measured' };
  economics: { status: 'not_computed' };
  reasons: string[];
  warnings_ar: string[];
}

/** Read-only comparison: the server loads the measured executions in the user's tenant. */
export async function compareIrrigationExecutions(
  fieldId: string,
  baselineExecutionId: string,
  candidateExecutionId: string,
): Promise<IrrigationScenarioComparison> {
  const { data } = await kongApi.post('/api/v1/outcome/measure', {
    field_id: fieldId,
    planned: {},
    actual: {},
    irrigation_comparison: {
      baseline_execution_id: baselineExecutionId,
      candidate_execution_id: candidateExecutionId,
    },
  });
  const comparison = data?.irrigation_comparison;
  if (!comparison || !['measured_comparison', 'needs_data'].includes(comparison.status)
    || comparison.baseline_execution_id !== baselineExecutionId
    || comparison.candidate_execution_id !== candidateExecutionId
    || !comparison.water || !comparison.runtime || !Array.isArray(comparison.warnings_ar)) {
    throw new Error('comparison response does not match requested executions');
  }
  return comparison;
}
