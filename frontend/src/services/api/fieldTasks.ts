import { kongApi } from './client';

export type FieldTaskStatus = 'pending' | 'planned' | 'in_progress' | 'completed' | 'cancelled' | string;

export interface FieldTaskSummary {
  task_id?: string;
  id?: string;
  field_id?: string;
  title_ar?: string;
  title?: string;
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
