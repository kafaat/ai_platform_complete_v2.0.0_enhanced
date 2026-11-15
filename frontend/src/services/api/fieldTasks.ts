import { kongApi } from './client';

export type FieldTaskStatus = 'pending' | 'planned' | 'in_progress' | 'completed' | 'cancelled' | string;

export interface SatelliteSource {
  asset_id: string;
  scene_id: string;
  acquisition_date: string;
  index_name: string;
  satellite: string | null;
  algorithm_version: string | null;
  geometry_revision: number | null;
}

export interface TerrainSource {
  source_key: string;
  kind: 'dem_product' | 'field_record';
  product_id?: string | null;
  dem_version?: string | null;
  geometry_hash?: string | null;
  generated_at?: string | null;
  cell_size_m?: number | null;
  algorithm_version?: string | null;
  elevation_m?: number | null;
  slope_pct?: number | null;
  aspect?: string | null;
  summaries: Record<string, Record<string, number>>;
}

export interface FieldTaskSummary {
  estimated_cost_usd?: number | null;
  actual_cost_usd?: number | null;
  terrain_sources?: TerrainSource[];
  satellite_sources?: SatelliteSource[];
  task_id?: string;
  id?: string;
  field_id?: string;
  title_ar?: string;
  title?: string;
  task_type?: string; // ما يعيده الخادم فعلاً (TaskSummary) — مصدر التسمية في مساحة العمل
  description_ar?: string;
  status?: FieldTaskStatus;
  priority?: number | string;
  recommended_date?: string | null;
  due_at?: string | null;
  notes?: string | null;
  [key: string]: unknown;
}

export interface FieldTaskListResponse {
  tasks: FieldTaskSummary[];
  degraded?: boolean;
  warning_ar?: string;
}

export const getFieldTasks = (fieldId: string): Promise<FieldTaskListResponse> =>
  kongApi.get<FieldTaskListResponse>('/api/v1/tasks', { params: { field_id: fieldId } }).then(r => r.data);
