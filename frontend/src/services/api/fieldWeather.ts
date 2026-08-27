// SAHOOL UI-25 — Field Workspace Weather API contracts
// weather facade فقط؛ لا fallback من الواجهة ولا تقدير يدوي.

import { kongApi } from './client';

export interface FieldWeatherOperationWindow {
  operation: 'spraying' | 'harvesting' | 'sowing' | 'fertilizing' | 'irrigation' | string;
  /** طابعٌ زمنيٌّ حقيقيّ من المزوّد، أو `null`. كان يحمل رمزاً (`"+72h"`) فيُصيَّر
   *  كما هو للمزارع؛ والإزاحةُ صارت في `start_offset_hours` باسمها. */
  start_at?: string | null;
  /** إزاحةُ الإطار بالساعات من لحظة الطلب (`0` = الآن). */
  start_offset_hours?: number | null;
  end_at?: string | null;
  suitability?: 'optimal' | 'acceptable' | 'poor' | 'unsafe' | string;
  score?: number | null;
  limiting_factors?: string[];
  confidence?: number | null;
}

export interface FieldWeatherOperationWindowsResponse {
  field_id: string;
  season_id?: string | null;
  windows: FieldWeatherOperationWindow[];
  degraded?: boolean;
  warning_ar?: string;
}

export interface FieldDiseaseRisk {
  risk_level: 'low' | 'moderate' | 'high' | string;
  diseases_ar: string[];
  advice_ar?: string;
  field_id: string;
  crop?: string | null;
  temperature_c?: number | null;
  humidity_pct?: number | null;
  rain_mm_3d?: number | null;
  source?: string;
}

export const getFieldWeatherOperationWindows = (
  fieldId: string,
  params?: { season_id?: string | null; horizon_hours?: number },
): Promise<FieldWeatherOperationWindowsResponse> =>
  kongApi.get<FieldWeatherOperationWindowsResponse>(`/api/v1/fields/${fieldId}/weather/operation-windows`, { params }).then(r => r.data);

export const getFieldDiseaseRisk = (fieldId: string): Promise<FieldDiseaseRisk> =>
  kongApi.get<FieldDiseaseRisk>(`/api/v1/fields/${fieldId}/weather/disease-risk`).then(r => r.data);
