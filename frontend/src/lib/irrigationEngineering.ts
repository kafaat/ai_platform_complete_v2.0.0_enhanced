export type IrrigationSystemType =
  | "center_pivot"
  | "linear_move"
  | "reel"
  | "sprinkler"
  | "drip"
  | "pump_only"
  | "valve_network";

export type ExecutionMode =
  | "recommendation_only"
  | "manual_estimated"
  | "manual_measured"
  | "supervised"
  | "automated";

export interface IrrigationEngineeringSummary {
  status: "pass" | "degraded" | "fail" | "incomplete";
  blocking_constraints: string[];
  warnings: string[];
  calculations: Record<string, number | null>;
  capability_graph: {
    system_type: IrrigationSystemType;
    supported_execution_modes: ExecutionMode[];
    commissioning_status: string;
    blocking_constraints: string[];
  };
  manual_operation: {
    execution_mode: ExecutionMode;
    target_depth_mm: number;
    target_volume_m3: number;
    estimated_runtime_h: number | null;
    recommended_speed_percent: number | null;
    requires_completion_confirmation: boolean;
    ledger_update_allowed_before_confirmation: boolean;
  };
  content_digest: string;
}

export const IRRIGATION_ENGINEERING_SECTIONS = [
  "system",
  "water_demand",
  "hydraulics",
  "pump",
  "energy",
  "geometry",
  "capability_graph",
  "commissioning",
  "manual_operation",
  "execution",
  "evidence",
  "summary",
] as const;
