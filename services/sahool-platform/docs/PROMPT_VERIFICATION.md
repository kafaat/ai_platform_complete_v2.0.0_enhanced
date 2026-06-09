# تقييم شمولية الـ Prompt — التحقّق الآلي

> **المنهجية:** قُورن الـ prompt آلياً (بـ `ast` + `grep`) مع الكود الفعلي، لا بالقراءة. هذا اتساقاً مع مبدأ "التحقّق قبل الحكم".

## الحكم المختصر

الـ prompt **شامل هيكلياً، غير دقيق تفصيلياً، ومبتور**.

### صحيح وشامل ✅
- البنية الكبرى: 7 طبقات، 29 وحدة — مطابقة تماماً.
- الأرقام الإجمالية: 29 وحدة، 240 اختبار، 4,388 سطر — صحيحة.
- المبادئ الستة، خريطة تدفّق القرار، ترتيب التنفيذ، سُلّم النماذج، الحالات الأربع — دقيقة.
- كل أسماء الوحدات الـ29 — مطابقة.

### خاطئ أو ناقص ❌
| المشكلة | التفصيل |
|--------|---------|
| ملفات اختبار وهمية | `test_provenance` (10)، `test_spatial_pipeline` (20)، `test_connectors_live` (6) — **لا توجد**؛ 36 اختباراً وهمياً |
| أعداد ملفات خاطئة | `test_crop_cards`: الـprompt=15، الواقع=20 |
| توقيعات غير مطابقة | 6+ دوال: `build_day_zero_advisory`، `compute_district_baseline`، `enforce_indication_ceiling`، `fertilizer_hint_from_ph`، `EvidenceType`(الواقع `EvidenceClass`+`EvidenceRuling`) |
| النص مبتور ومكرّر | قسم 1.1-1.8 مكرّر؛ قطع في `market_analyzer` ("import_substitutionابق") |
| تغطية جزئية | يوثّق ~60 من 166 واجهة في النواة (و211 في المشروع كاملاً) |

### التشخيص
الـ prompt **إعادة بناء تقريبية من الذاكرة/التوثيق، لا استخراج آلي من الكود**. لذا توقيعاته "نظيفة" أبسط من الفعلية، وفيه ملفات اختبار مثالية لا موجودة. لو نُفِّذ حرفياً، لبنى ملفات وهمية وأهمل التوزيع الفعلي.

### التوصية
استخدم الـ prompt التخطيطي **للبنية والمبادئ والترتيب** (ممتاز فيها)، واستخدم **الملحق أدناه** (المُستخرَج آلياً) **للتوقيعات والاختبارات الدقيقة**. معاً = prompt شامل ودقيق.

---

# ملحق التحقّق: الواقع الفعلي للنواة (مُستخرَج آلياً من الكود)

> هذا الملحق مُولَّد آلياً من الكود بـ `ast` — مصدر الحقيقة الوحيد. يصحّح أي
> اختلاف في الـ prompt التخطيطي (الذي يحوي ملفات اختبار وهمية وتوقيعات مبسّطة).

---

## ١. التوقيعات الفعلية (الواجهات العامة)

### `core/anwa_calendar.py`
- `class StarSeason`
- `def get_star_season(star_id)`
- `class TimingContext`
- `def anwa_timing_context(star_id)`
- `def explain_anwa_principle_ar()`

### `core/connectors/base.py`
- `class FetchStatus`
- `class ConnectorResult`
- `class BaseConnector`

### `core/connectors/copernicus.py`
- `class ImageryRequest`
- `class CopernicusConnector`

### `core/connectors/farmonaut.py`
- `class ImageType`
- `def validate_field_polygon(points)`
- `class CreditEstimate`
- `def estimate_monthly_credits(hectares, fields_count, weather_calls_per_day)`
- `class SenseDay`
- `class FarmonautConnector`

### `core/connectors/weather_openmeteo.py`
- `class WeatherInputs`
- `class OpenMeteoConnector`

### `core/crop_cards/loader.py`
- `def load_crop_card(crop_id)`
- `def list_crop_cards()`
- `def validate_crop_card(card)`
- `def load_variety_card(variety_id)`
- `def list_variety_cards()`
- `def varieties_of_crop(crop_id)`
- `def validate_variety_card(card)`

### `core/data_completeness.py`
- `class CompletenessResult`
- `def compute_completeness(provided_fields)`
- `class NotificationTrigger`
- `def build_notification(trigger, field_name, completeness)`

### `core/day_zero_advisory.py`
- `class AdvisoryItem`
- `class DayZeroAdvisory`
- `def build_day_zero_advisory(field_id)`

### `core/district_baseline.py`
- `class DistrictBaseline`
- `def compute_district_baseline(district_id, observable_id, analyzed_values)`
- `class FarmerContext`
- `def context_for_low_data_farmer(baseline, observable_name_ar)`

### `core/engines/fao56.py`
- `class GrowthStage`
- `class WeatherDay`
- `class CropKcProfile`
- `def penman_monteith_et0(w)`
- `def kc_for_age(profile, days_after_planting)`
- `def salinity_stress_ks(profile, soil_ece)`
- `def leaching_requirement(water_ec, crop_threshold_ece)`
- `class SoilZone`
- `class IrrigationResult`
- `def compute_irrigation(weather, crop, zone, days_after_planting, soil_ece, water_ec, effective_rainfall_mm, irrigation_efficiency)`
- `def gdd_daily(tmax, tmin, tbase)`
- `def gdd_accumulate(weather_days, tbase)`

### `core/engines/fertility.py`
- `class FertiliserNeed`
- `def fertiliser_need(nutrient, required_kg_ha, available_kg_ha, use_efficiency)`
- `def mineralisation_half_life_days(temp_c, cn_ratio, k_ref_per_day, q10, t_ref)`
- `def organic_matter_recommendation(current_om_pct, optimal_om_pct, soil_history)`

### `core/engines/fusion.py`
- `class Confidence`
- `class IndexReading`
- `def ensemble_variance(readings)`
- `def classify_confidence(fused_sigma)`
- `class FusionResult`
- `def fuse_health(readings, cloud_cover_pct, cwsi)`
- `def diagnose_stress(ndmi, cwsi, ndre, ndvi, salinity_index, ec_trend)`

### `core/engines/fuzzy.py`
- `class TrapezoidParams`
- `def trapezoidal_score(value, p)`
- `def descending_score(value, optimal_max, max_acceptable)`
- `def ascending_score(value, min_acceptable, optimal_min)`

### `core/engines/market_analyzer.py`
- `class PriceRisk`
- `class MarketSignal`
- `def coefficient_of_variation(prices)`
- `def classify_price_risk(cv)`
- `def import_substitution_gap(local_price, import_price)`
- `def analyse_market(crop_id, historical_prices, local_price, import_price)`
- `def regional_supply_signal(current_season_lai, historical_avg_lai)`

### `core/engines/suitability.py`
- `class SuitabilityClass`
- `class GoverningFactor`
- `class ModifyingFactor`
- `class SuitabilityResult`
- `def evaluate_suitability(crop_id, governing, modifying)`

### `core/engines/water_cost.py`
- `class WaterCostInputs`
- `def water_cost_per_m3(inp)`
- `def seasonal_water_cost(inp, etc_m3_per_ha, area_ha)`

### `core/engines/yield_interval.py`
- `class YieldInterval`
- `def conformal_interval(point_estimate, calibration_residuals, coverage)`
- `def pending_estimate()`

### `core/evidence_class.py`
- `class EvidenceClass`
- `class EvidenceRuling`
- `def classify_evidence(observable_id, observation_type)`
- `def enforce_indication_ceiling(observable_id, observation_type, proposed_confidence)`
- `def explain_evidence_principle_ar()`
- `class Corroboration`
- `def corroborate_indications(target_ar, indications)`

### `core/farmer_agency.py`
- `class FarmerResponse`
- `class AdvisoryDecision`
- `def record_farmer_response(decision, response, why_rejected_ar, modification_ar)`
- `class RejectionPattern`
- `def analyze_rejection_pattern(recommendation_type_ar, decisions)`

### `core/field_lifecycle.py`
- `class FieldQualityState`
- `class SoilTestChoice`
- `def resolve_state(soil_choice, provided_governors, lab_request_pending)`
- `def can_recommend(state, recommendation_type)`
- `def state_explanation_ar(state)`

### `core/learning/calibration_loop.py`
- `class CalibrationResult`
- `def read_yield_history(tenant_dir)`
- `def calibrate_zone_factor(actual_yields, model_predicted)`
- `def calibration_method_used(actual_yields, model_predicted)`
- `def run_calibration(district_dir, tenant_dirs, model_predict_fn)`
- `def write_calibration(district_dir, result)`

### `core/learning/model_selector.py`
- `class ModelTier`
- `class ModelDecision`
- `def effective_sample_size(n_records, n_farms, n_seasons)`
- `def select_model(n_records, n_farms, n_seasons)`

### `core/learning/recommendation_log.py`
- `class RecommendationRecord`
- `def log_recommendation(log_path, rec)`
- `def record_outcome(log_path, rec_id, actual_yield, outcome_date)`
- `def compute_mape(log_path)`
- `def load_log(log_path)`

### `core/provenance.py`
- `class Stage`
- `class Status`
- `class Confidence`
- `def confidence_from_error(relative_error)`
- `class Provenance`
- `def propagate_multiply(a, b)`
- `def propagate_add(values_errors)`
- `def pending(name, unit, ground_truth, verification)`

### `core/recommendation_engine.py`
- `class RecommendationStatus`
- `class FarmerSignal`
- `class BackendDetail`
- `class FarmerView`
- `class Recommendation`
- `def generate_recommendation(validation, irrigation, suitability, zone_factor, zone_factor_status, local_knowledge, field_state)`

### `core/soil_recommendations.py`
- `class FertilizerHint`
- `def fertilizer_hint_from_ph(soil_ph)`
- `class IrrigationHint`
- `def irrigation_hint_from_texture(texture)`
- `class CropBias`
- `def crop_bias_from_texture(texture)`
- `def soil_to_recommendations(texture, soil_ph)`

### `core/spatial/index_scheduler.py`
- `class IndexCadence`
- `class IndexPolicy`
- `def get_index_policy(index_id)`
- `def should_compute_now(index_id, days_since_last, purpose_active)`
- `def cost_summary(active_indices)`

### `core/spatial/indicators.py`
- `class SpatialIndex`
- `class GeoBBox`
- `class Severity`
- `class ZoneOfInterest`
- `def detect_zones_of_interest(grid, index, bbox, threshold_std, min_cluster)`
- `def link_farmer_knowledge(zones, farmer_knowledge)`
- `class SoilZone`
- `def classify_soil_zones(bsi_grid, ndvi_grid, bbox, min_cluster)`

### `core/spatial/pipeline.py`
- `class Satellite`
- `class ImageQuality`
- `class FieldAOI`
- `class AcquisitionPlan`
- `def decide_source(cloud_cover_pct)`
- `class RasterTile`
- `def compute_ndvi_from_bands(nir, red)`
- `class TimelineEntry`
- `def build_timeline(tiles)`
- `def detect_temporal_change(timeline, index_name)`
- `def polygon_area_ha(coords)`
- `def compute_bsi_from_bands(swir1, red, nir, blue)`
- `def estimate_soil_texture(bsi, ndvi)`
- `def clay_minerals_ratio(swir1, swir2)`
- `def iron_oxide_ratio(red, blue)`
- `def refine_soil_texture(bsi, ndvi, clay_ratio, iron_ratio)`
- `def detect_growth_stage_from_ndvi(ndvi_series)`
- `def crop_type_consistency_check(observed_ndvi_peak, expected_crop, expected_peak_range)`
- `def estimate_lai_from_ndvi(ndvi)`

**المجموع الفعلي: 166 واجهة عامة في `core/` فقط** (top-level).

> **توضيح رقمي مهمّ (لتجنّب لبس):** هذا العدد (166) يخصّ `core/` **حصراً**. أمّا الرقم 211 في `SAHOOL_SOURCE_DOCUMENTATION.md` فيعدّ **كامل المشروع** (يشمل `lite_store`, `api/`, `scripts/` خارج النواة) — وهو ما يتحقّق منه `tools_check_doc_consistency.py` بـ `ROOT/**`. الرقمان صحيحان، كلٌّ في نطاقه: 166 = نواة، 211 = المشروع كاملاً.

---

## ٢. التوزيع الفعلي للاختبارات (24 ملفاً، لا ملفات وهمية)

| الملف | العدد |
|------|------|
| `test_anwa_calendar.py` | 7 |
| `test_completeness.py` | 8 |
| `test_connectors.py` | 6 |
| `test_crop_cards.py` | 20 |
| `test_day_zero.py` | 8 |
| `test_district_baseline.py` | 9 |
| `test_engines.py` | 25 |
| `test_evidence_class.py` | 17 |
| `test_farmer_agency.py` | 7 |
| `test_farmer_knowledge.py` | 10 |
| `test_farmonaut.py` | 7 |
| `test_field_lifecycle.py` | 6 |
| `test_field_state.py` | 5 |
| `test_gaps_v91.py` | 7 |
| `test_improvements_v91.py` | 6 |
| `test_index_scheduler.py` | 7 |
| `test_learning.py` | 12 |
| `test_maestro_bridge.py` | 5 |
| `test_recommendation_engine.py` | 5 |
| `test_recommendation_log.py` | 7 |
| `test_remaining_engines.py` | 13 |
| `test_security_v91.py` | 5 |
| `test_soil_recommendations.py` | 12 |
| `test_soil_remote.py` | 26 |
| **المجموع** | **240** |

> **تصحيحات مقابل الـ prompt التخطيطي:**
> - `test_provenance.py` (10): **غير موجود** — provenance مُختبَر ضمن `test_engines.py`
> - `test_spatial_pipeline.py` (20): **غير موجود** — pipeline مُختبَر ضمن `test_soil_remote.py` (26)
> - `test_connectors_live.py` (6): **غير موجود** — لم يُبنَ (تكامل حيّ مؤجّل)
> - `test_crop_cards.py`: الواقع **20** لا 15 (أُضيفت 5 اختبارات cranberry)
