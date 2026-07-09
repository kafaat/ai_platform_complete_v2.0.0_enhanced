// SAHOOL UI-24 — Field Workspace Imagery API contracts
// لا تعرض الواجهة صوراً أو تواريخ بديلة؛ كل شيء يأتي من backend/raster facade.

import { kongApi } from './client';

export type FieldImageryIndex = 'truecolor' | 'ndvi' | 'ndmi' | 'ndre' | 'msavi' | string;

export interface FieldImageryDateOption {
  date: string;
  cloud_pct?: number | null;
  cloud_cover?: number | null;
  has_cog?: boolean;
  scene_id?: string | null;
  indices?: string[];
  acquisition_datetime?: string | null;
}

export interface FieldImageryTimelineItem {
  date: string;
  has_cog: boolean;
  cloud_pct: number | null;
  clear_pct?: number | null;
  quality_label?: 'high' | 'medium' | 'cloudy' | 'unknown' | string | null;
  indices: string[];
  scene_id?: string | null;
  acquisition_datetime?: string | null;
  thumbnail_url?: string | null;
}

export interface FieldImageryTimeline {
  field_id: string;
  months: number;
  count: number;
  items: FieldImageryTimelineItem[];
  degraded?: boolean;
  warning_ar?: string;
}

function normalizeDateOption(x: unknown): FieldImageryDateOption | null {
  if (typeof x === 'string') return { date: x };
  if (!x || typeof x !== 'object') return null;
  const obj = x as Record<string, unknown>;
  const date = String(obj.date ?? obj.acquisition_date ?? obj.datetime ?? '').slice(0, 10);
  if (!date) return null;
  return {
    date,
    cloud_pct: typeof obj.cloud_pct === 'number' ? obj.cloud_pct : (typeof obj.cloud_cover === 'number' ? obj.cloud_cover : null),
    cloud_cover: typeof obj.cloud_cover === 'number' ? obj.cloud_cover : null,
    has_cog: Boolean(obj.has_cog ?? obj.ready ?? false),
    scene_id: typeof obj.scene_id === 'string' ? obj.scene_id : null,
    indices: Array.isArray(obj.indices) ? (obj.indices as unknown[]).map(v => String(v)) : undefined,
    acquisition_datetime: typeof obj.acquisition_datetime === 'string' ? obj.acquisition_datetime : null,
  };
}

export const getFieldImageryAvailableDates = (
  fieldId: string,
  index: FieldImageryIndex = 'truecolor',
  limit = 120,
): Promise<FieldImageryDateOption[]> =>
  kongApi.get(`/api/v1/fields/${fieldId}/available-dates`, { params: { index, limit } }).then((r) => {
    const raw = (r.data as { dates?: unknown; items?: unknown } | unknown[] | undefined);
    const list = Array.isArray(raw) ? raw : Array.isArray((raw as { dates?: unknown[] })?.dates) ? (raw as { dates: unknown[] }).dates : Array.isArray((raw as { items?: unknown[] })?.items) ? (raw as { items: unknown[] }).items : [];
    return list.map(normalizeDateOption).filter(Boolean) as FieldImageryDateOption[];
  });

export const getFieldImageryTimeline = (fieldId: string, months = 24): Promise<FieldImageryTimeline> =>
  kongApi.get<FieldImageryTimeline>(`/api/v1/fields/${fieldId}/imagery/timeline`, { params: { months } }).then(r => r.data);
