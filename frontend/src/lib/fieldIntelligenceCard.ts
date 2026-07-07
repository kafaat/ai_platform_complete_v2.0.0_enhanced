// fieldIntelligenceCard — عقد بطاقة ذكاء الحقل (V65) + مساعِدات عرض نقيّة.
//
// يطابق مخرَج الخلفيّة: كلّ قسم إمّا { status:'present', ... } أو
// { status:'missing', reason }. الواجهة تعرض الحاضر بقيمته والمفقود بسببه صراحةً
// (لا اختلاق) — نفس فلسفة الخلفيّة. مساعِدات نقيّة فقط (بلا React) لتُختبَر منفصلةً.

export interface CardSection {
  status: 'present' | 'missing';
  reason?: string;
}

export interface LatestSceneSection extends CardSection {
  scene_id?: string | null;
  acquisition_date?: string | null;
  provider?: string | null;
  cloud_cover?: number | null;
  cog_ready?: boolean | null;
}

export interface FieldConditionSection extends CardSection {
  effective_status?: string;
  reason?: string;
  primary_driver?: string;
  crop_vigor?: number;
  crop_vigor_confidence?: string;
  salinity_class?: string;
  salinity_risk?: number;
  heat_risk?: number;
  ndvi_trend?: string;
}

export interface NdviVsHistoricalSection extends CardSection {
  current?: number;
  historical_mean?: number;
  n_history?: number;
  anomaly?: number;
  label?: 'above_historical' | 'below_historical' | 'near_historical';
}

export interface WaterDeficitSection extends CardSection {
  value?: number | null;
}

export interface SoilBaselineSection extends CardSection {
  warning?: string;
  texture?: string;
  clay_pct?: number;
  sand_pct?: number;
  silt_pct?: number;
  ph?: number;
  soc_pct?: number;
  cec?: number;
}

export interface TerrainSection extends CardSection {
  mean_slope_deg?: number;
  max_slope_deg?: number;
  dominant_aspect?: string;
  elevation_mean_m?: number;
  erosion_risk?: 'very_low' | 'low' | 'medium' | 'high' | 'severe';
}

export interface WeatherWindowSection extends CardSection {
  date?: string;
  et0_mm?: number;
  temp_max_c?: number;
  temp_min_c?: number;
  precipitation_mm?: number;
  wind_max_ms?: number;
  heat_flag?: 'critical' | 'elevated' | 'normal';
  frost_flag?: boolean;
}

export interface WeakZonesSection extends CardSection {
  count?: number;
  zone_ids?: string[];
}

export interface EvidenceSection extends CardSection {
  sources?: string[];
  count?: number;
}

export interface ScoutingSection extends CardSection {
  action?: string;
  priority?: string;
  reason?: string;
}

export interface ProviderStatusSection extends CardSection {
  providers?: { default?: string | null; active?: string[]; planned?: string[] };
}

export interface RiskAlertsSection {
  count: number;
  top_severity?: string | null;
  items?: unknown[];
}

export interface ConfidenceSection {
  value?: number | null;
  reason?: string | null;
}

export interface FieldIntelligenceCard {
  schema: string;
  field_id?: string | null;
  generated_at?: string | null;
  sections: {
    latest_scene: LatestSceneSection;
    provider_status: ProviderStatusSection;
    field_condition: FieldConditionSection;
    ndvi_vs_historical: NdviVsHistoricalSection;
    water_deficit: WaterDeficitSection;
    soil_baseline: SoilBaselineSection;
    weather_window: WeatherWindowSection;
    terrain: TerrainSection;
    weak_zones: WeakZonesSection;
    evidence: EvidenceSection;
    scouting_recommendation: ScoutingSection;
    risk_alerts: RiskAlertsSection;
    confidence: ConfidenceSection;
  };
  completeness: number;
  missing_sections: string[];
}

export interface FieldIntelligenceAnalyzeResponse {
  field_id?: string;
  field_intelligence_card?: FieldIntelligenceCard;
}

export const SECTION_LABELS_AR: Record<string, string> = {
  latest_scene: 'أحدث مشهد',
  provider_status: 'حالة المزوّدين',
  field_condition: 'حالة الحقل',
  ndvi_vs_historical: 'NDVI مقابل التاريخيّ',
  water_deficit: 'العجز المائيّ',
  soil_baseline: 'خطّ أساس التربة',
  weather_window: 'نافذة الطقس',
  terrain: 'التضاريس',
  weak_zones: 'المناطق الضعيفة',
  evidence: 'الأدلّة',
  scouting_recommendation: 'توصية الاستطلاع',
  risk_alerts: 'التنبيهات',
  confidence: 'الثقة',
};

export function isPresent(s?: CardSection | null): boolean {
  return !!s && s.status === 'present';
}

export function completenessPct(c?: number): number {
  return Math.max(0, Math.min(100, Math.round((c ?? 0) * 100)));
}

export function ndviLabelAr(label?: string): string {
  switch (label) {
    case 'above_historical':
      return 'فوق المعدّل التاريخيّ';
    case 'below_historical':
      return 'تحت المعدّل التاريخيّ';
    case 'near_historical':
      return 'قرب المعدّل التاريخيّ';
    default:
      return '—';
  }
}

export function ndviLabelTone(label?: string): string {
  switch (label) {
    case 'above_historical':
      return '#86efac';
    case 'below_historical':
      return '#fca5a5';
    default:
      return '#cbd5e1';
  }
}

/** سبب المفقود بالعربيّة (خريطة قصيرة؛ المجهول يُعرَض كما هو بصدق). */
export function missingReasonAr(reason?: string): string {
  const map: Record<string, string> = {
    no_scene_supplied: 'لا مشهد متاح',
    no_provider_status_supplied: 'حالة المزوّدين غير متاحة (raster متعذّر)',
    insufficient_history: 'تاريخ NDVI غير كافٍ',
    no_current_ndvi: 'لا NDVI حاليّ',
    no_water_deficit_signal: 'لا إشارة عجز مائيّ',
    no_zone_data: 'لا بيانات مناطق',
    no_provenance: 'لا أدلّة',
    no_condition_signals: 'لا إشارات تشخيصيّة بعد',
    no_soil_baseline_supplied: 'خطّ أساس التربة غير متاح (soil-service/إحداثيّات)',
    no_weather_window_supplied: 'نافذة الطقس غير متاحة (توقّع/إحداثيّات)',
    no_terrain_supplied: 'التضاريس غير متاحة (لا DEM/هندسة حقل)',
  };
  return (reason && map[reason]) || reason || 'غير متاح';
}

/** تسمية + لون خطر التعرية (عتبات ميل مشتركة؛ المجهول يُعرَض كما هو). */
export function erosionRiskAr(risk?: string): { label: string; danger: boolean } {
  const map: Record<string, string> = {
    very_low: 'تعرية منخفضة جدّاً',
    low: 'تعرية منخفضة',
    medium: 'تعرية متوسّطة',
    high: 'تعرية عالية',
    severe: 'تعرية شديدة',
  };
  return { label: (risk && map[risk]) || risk || '—', danger: risk === 'high' || risk === 'severe' };
}

/** تسمية عربيّة لعلَم الحرارة اليوميّ (عتبات مشتركة؛ المجهول يُعرَض كما هو). */
export function heatFlagAr(flag?: string): string {
  switch (flag) {
    case 'critical':
      return 'حرارة حرجة';
    case 'elevated':
      return 'حرارة مرتفعة';
    case 'normal':
      return 'حرارة معتدلة';
    default:
      return flag || '—';
  }
}

/** تسمية عربيّة للحالة الفعليّة/المُحرِّك الأساسيّ (المجهول يُعرَض كما هو بصدق). */
export function conditionDriverAr(driver?: string): string {
  const map: Record<string, string> = {
    salinity_limited: 'محكوم بالملوحة',
    heat_limited: 'محكوم بالحرارة',
    vigor_led: 'حيويّة جيّدة تقود الحالة',
    declining: 'اتّجاه متراجع',
    low_vigor: 'حيويّة منخفضة',
  };
  return (driver && map[driver]) || driver || '—';
}
