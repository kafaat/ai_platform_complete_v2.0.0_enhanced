import { kongApi } from "./client";

export type IrrigationObservationOutcome =
  | "irrigated"
  | "not_irrigated"
  | "unknown";
export type IrrigationQuantityMethod =
  | "meter"
  | "estimated_flow"
  | "declared_volume"
  | "unknown";
export interface TaskIrrigationObservation {
  observation_id: string;
  execution_id: string;
  source: "farmer_task" | "field_inspection";
  outcome: IrrigationObservationOutcome;
  occurred_at: string;
  quantity_method: IrrigationQuantityMethod;
  meter_start_m3?: number;
  meter_end_m3?: number;
  flow_m3_h?: number;
  duration_minutes?: number;
  interruptions_minutes: number;
  volume_m3?: number | null;
  irrigated_area_ha?: number;
  notes?: string;
}

export interface StoredTaskIrrigationObservation extends TaskIrrigationObservation {
  computed: {
    volume_m3: number | null;
    depth_mm: number | null;
    quality: string;
    ledger_eligible: false;
  };
  received_at: string;
}

export async function listTaskIrrigationObservations(
  taskId: string,
): Promise<StoredTaskIrrigationObservation[]> {
  const { data } = await kongApi.get("/api/v1/tasks", {
    params: { irrigation_task_id: taskId },
  });
  if (!data || !Array.isArray(data.irrigation_observations))
    throw new Error("استجابة سجل مشاهدات الري غير صالحة");
  return data.irrigation_observations;
}
export async function recordTaskIrrigationObservation(
  taskId: string,
  observation: TaskIrrigationObservation,
): Promise<void> {
  await kongApi.post(
    "/api/v1/observations",
    { task_id: taskId, irrigation_observation: observation },
    {
      headers: { "Idempotency-Key": observation.observation_id },
    },
  );
}
