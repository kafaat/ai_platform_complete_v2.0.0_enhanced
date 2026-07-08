// fieldSeasonState — أنواع «الحقيقة التشغيليّة الموحّدة للحقل-الموسم».
// مطابقة لمخرَج api/field_season_projection.assemble_field_season_state (schema field_season_state.v1).
// صدق: كلّ حقل قد يكون null/فارغاً؛ evidence_missing يُعلن الناقص، لا رقم مُختلَق.

export interface StageRisk {
  code: string;
  severity: string; // none | low | medium | high
  reason_ar: string;
  factor: string;
}

export interface WeatherStageRisks {
  stage: string | null;
  risks: StageRisk[];
  overall_severity: string;
  requires_action: boolean;
  confidence: string;
}

export interface EoStageMismatch {
  status: string; // aligned | below_expected | above_expected | inconclusive
  severity: string;
  reason_ar: string;
  scene_quality_ok: boolean | null;
  confidence: string;
}

export interface FieldSeasonState {
  schema: string;
  field_id: string | null;
  season_id: string | null;
  crop: string | null;
  cultivar: string | null;
  current_stage: string | null;
  current_stage_ar: string | null;
  stage_source: string | null; // gdd | days | null
  days_after_sowing: number | null;
  accumulated_gdd: number | null;
  gdd_to_maturity: number | null;
  gdd_fraction: number | null;
  current_kc: number | null;
  calendar_status: string | null;
  water_deficit_7d_mm: number | null;
  water_deficit_14d_mm: number | null;
  water_stress_factor: number | null;
  eo_stage_mismatch: EoStageMismatch | null;
  weather_stage_risks: WeatherStageRisks | null;
  open_operations: number | null;
  season_confidence: string; // low | medium
  requires_review: boolean;
  evidence_used: string[];
  evidence_missing: string[];
  disclaimer_ar: string;
}
