# Prompt تنفيذي: بناء نواة منصّة سهول الزراعية (SAHOOL Core)

> **هذا الملف مُولَّد آلياً من الكود الفعلي** (عبر `ast`) — كل توقيع ورقم مُستخرَج من المصدر، لا من الذاكرة. صالح للتطبيق المباشر في مشروع جديد.
>
> **الهدف:** بناء نواة قرار زراعي محايدة الموقع بلغة Python. **النطاق:** النواة فقط (`core/`) — لا طبقة بيانات، لا واجهة، لا API.

---

## معايير القبول (Definition of Done)

| المعيار | القيمة |
|--------|--------|
| الوحدات | 29 وحدة Python (غير `__init__`) |
| الحجم | ~4,388 سطراً |
| الاختبارات | 240 اختباراً ناجحاً، 24 ملف اختبار |
| الواجهات | 166 واجهة عامة في `core/` (top-level) |
| القاعدة | SQLite (<50 مزرعة، عزل برمجي بـ `tenant_id`) |
| اللغة | docstring عربي لكل واجهة (يشرح **لماذا** لا فقط **ماذا**) |

---

## المبادئ الستة الحاكمة (غير قابلة للتفاوض)

1. **الصدق الإحصائي الصارم:** لا أرقام وهمية. `zone_factor=null` حتى المعايرة. الثقة فئة (`none`/`low`/`medium`/`high`) لا نسبة مئوية مزيّفة.
2. **الاستشعار يوجّه، المختبر يحكم:** المؤشّرات الطيفية (NDVI, BSI, SI) = **قرائن** (ثقة سقفها منخفض). التحاليل المخبرية (EC, pH, نسيج) = **أدلّة** (تحكم).
3. **القاعدة الذهبية:** غياب حاكم صارم → الحقل `BLOCKED` → **لا توصية**. الثقة = أضعف حلقة.
4. **السلامة لا تُتخطّى:** المبيدات/فترات الأمان (PHI) محجوبة دائماً ما لم تكتمل البيانات.
5. **حياد النواة عن الموقع:** `core/` لا تعرف أي مزرعة. `grep -rE "(sakha|6.17|142ha)" core/` يجب أن يكون فارغاً. السياق يُحقَن لا يُضمَّن.
6. **فصل عرض المزارع عن الخلفية:** `FarmerView` (إشارة + قرار) منفصل عن `BackendDetail` (المؤشّرات الخام + نسب الخطأ).

### المنهجية الهندسية لكل وحدة
1. كود + docstring عربي (لماذا لا فقط ماذا).
2. اختبارات وحدة تحرس المبادئ (مثلاً: اختبار يؤكّد أن القرينة لا تُرفَع لدليل).
3. متحقّق آلي يضمن: (عدد الاختبارات على القرص = الجدول = الرأس) و(الواجهات = التوثيق).
4. تحقّق حياد النواة (`grep`) قبل كل إصدار.

### ترتيب التنفيذ الموصى
المحرّكات (`fao56` → `fuzzy` → `suitability`) → `provenance` → `evidence_class` → المايسترو (`recommendation_engine`) → الباقي. كل وحدة تُتبع باختباراتها فوراً؛ لا انتقال قبل نجاحها.

---

## الطبقة 1: المحرّكات الفيزيائية (`core/engines/`)

### `core/engines/fao56.py` (330 أسطر)

**`class GrowthStage`**
**`class WeatherDay`** — Daily weather inputs for ET0. All from weather-service.
  - الحقول: `temp_max_c: float`, `temp_min_c: float`, `humidity_pct: float`, `wind_speed_m_s: float`, `solar_radiation_mj_m2: float`, `latitude_deg: float`, `elevation_m: float`, `day_of_year: int`
**`class CropKcProfile`** — The CONSTANT — biological water fingerprint of a crop.
  - الحقول: `crop_id: str`, `kc_initial: float`, `kc_mid: float`, `kc_end: float`, `stage_days: list[int]`, `salt_tolerance_ece: float`, `salt_slope_pct: float`, `source: str`
- `def penman_monteith_et0(w: WeatherDay) -> float`
  - Reference evapotranspiration (mm/day) via FAO-56 Penman-Monteith.
- `def kc_for_age(profile: CropKcProfile, days_after_planting: int) -> tuple[float, GrowthStage]`
  - Return (Kc, stage) for the crop's age. The CONSTANT side of the eq.
- `def salinity_stress_ks(profile: CropKcProfile, soil_ece: float) -> float`
  - Yield/ET reduction factor from soil salinity.
- `def leaching_requirement(water_ec: float, crop_threshold_ece: float) -> float`
  - Fraction of extra water needed to flush salts.
**`class SoilZone`** — A management zone. Al-Jawf is NOT one soil — sandy/loam/mixed.
  - الحقول: `zone_id: str`, `texture: str`, `taw_mm_per_m: float`, `raw_fraction: float`, `ke_factor: float`, `drainage: str`, `area_ha: float`, `source: str`
**`class IrrigationResult`**
  - الحقول: `zone_id: str`, `texture: str`, `et0_mm: float`, `kc: float`, `stage: str`, `etc_mm: float`, `ks_salinity: float`, `etc_adjusted_mm: float`, `effective_rainfall_mm: float`, `leaching_fraction: float`, `net_irrigation_mm: float`, `gross_irrigation_mm: float`, `m3_per_ha: float`, `total_m3_zone: float`, `irrigation_interval_days: float`, `night_irrigation_recommended: bool`, `dtr_c: float`, `notes: list[str]`
- `def compute_irrigation(weather: WeatherDay, crop: CropKcProfile, zone: SoilZone, days_after_planting: int, soil_ece: float, water_ec: float, effective_rainfall_mm: float = 0.0, irrigation_efficiency: float = 0.85) -> IrrigationResult`
  - Full FAO-56 chain for ONE zone on ONE day.
- `def gdd_daily(tmax: float, tmin: float, tbase: float = 10.0) -> float`
  - درجات النمو اليومية (Growing Degree Days).
- `def gdd_accumulate(weather_days: list[dict], tbase: float = 10.0) -> float`
  - يجمع GDD التراكمي من أيام طقس (كل يوم: {'tmax':.., 'tmin':..}).

### `core/engines/fertility.py` (104 أسطر)

**`class FertiliserNeed`**
  - الحقول: `nutrient: str`, `required_kg_ha: float`, `available_kg_ha: float`, `deficit_kg_ha: float`, `fertiliser_kg_ha: float`, `note_ar: str`
- `def fertiliser_need(nutrient: str, required_kg_ha: float, available_kg_ha: float, use_efficiency: float = 0.5) -> FertiliserNeed`
  - Difference equation. Efficiency 0.5 typical for N (urea).
- `def mineralisation_half_life_days(temp_c: float, cn_ratio: float, k_ref_per_day: float = 0.05, q10: float = 2.0, t_ref: float = 20.0) -> dict`
  - Q10 mineralisation half-life. Accounts for C:N delay.
- `def organic_matter_recommendation(current_om_pct: float, optimal_om_pct: float, soil_history: str) -> dict`
  - Compost need to reach optimal OM. History adjusts the baseline.

### `core/engines/fusion.py` (159 أسطر)

**`class Confidence`**
**`class IndexReading`**
  - الحقول: `name: str`, `value: float`, `sigma: float`, `weight: float`, `family: str`
- `def ensemble_variance(readings: list[IndexReading]) -> float`
  - Correlation-aware fused variance. The honest version.
- `def classify_confidence(fused_sigma: float) -> Confidence`
  - Category, not a fake percentage.
**`class FusionResult`**
  - الحقول: `fused_value: float`, `fused_sigma: float`, `confidence: Confidence`, `dominant_family: str`, `cloud_cover_pct: float`, `notes: list[str]`
- `def fuse_health(readings: list[IndexReading], cloud_cover_pct: float, cwsi: float | None = None) -> FusionResult`
  - Fuse multi-family indices into one health estimate + honest confidence.
- `def diagnose_stress(ndmi: float, cwsi: float, ndre: float, ndvi: float, salinity_index: float, ec_trend: str) -> dict`
  - Confirmed diagnosis, not 'check irrigation or fertiliser' guess.

### `core/engines/fuzzy.py` (72 أسطر)

**`class TrapezoidParams`** — Four corners of the trapezoid. Outside [min_acc, max_acc] => dead zone.
  - الحقول: `min_acceptable: float`, `optimal_min: float`, `optimal_max: float`, `max_acceptable: float`
- `def trapezoidal_score(value: float, p: TrapezoidParams) -> float`
  - Return membership score in [0, 1]. Hard 0 outside acceptable range.
- `def descending_score(value: float, optimal_max: float, max_acceptable: float) -> float`
  - For factors where lower is better (salinity, SAR). 1.0 below optimal,
- `def ascending_score(value: float, min_acceptable: float, optimal_min: float) -> float`
  - For factors where higher is better (organic matter, soil depth).

### `core/engines/market_analyzer.py` (155 أسطر)

**`class PriceRisk`**
**`class MarketSignal`**
  - الحقول: `crop_id: str`, `price_risk: PriceRisk`, `cv: float | None`, `gap_score: float | None`, `opportunity_ar: str`, `data_quality: str`
- `def coefficient_of_variation(prices: list[float]) -> float | None`
  - CV = std/mean. Needs >= 3 points to be meaningful.
- `def classify_price_risk(cv: float | None) -> PriceRisk`
- `def import_substitution_gap(local_price: float | None, import_price: float | None) -> float | None`
  - (import - local)/local. Positive => local is cheaper => substitution
- `def analyse_market(crop_id: str, historical_prices: list[float], local_price: float | None = None, import_price: float | None = None) -> MarketSignal`
- `def regional_supply_signal(current_season_lai: list[float], historical_avg_lai: float | None) -> dict`
  - يقدّر *اتجاه* العرض الإقليمي من LAI حقول المنصّة (لا رقم مطلق).

### `core/engines/suitability.py` (155 أسطر)

**`class SuitabilityClass`**
**`class GoverningFactor`** — Knock-out factor. Outside acceptable => crop fails (N).
  - الحقول: `name: str`, `name_ar: str`, `value: float`, `min_acceptable: float`, `max_acceptable: float`, `measurement_error: float`, `source: str`
**`class ModifyingFactor`** — Weighted, treatable factor scored by fuzzy membership.
  - الحقول: `name: str`, `name_ar: str`, `value: float`, `trapezoid: TrapezoidParams`, `weight: float`, `measurement_error: float`, `source: str`
**`class SuitabilityResult`**
  - الحقول: `crop_id: str`, `suitability: SuitabilityClass`, `score: float`, `confidence: Confidence`, `failed_governing: list[str]`, `breakdown: list[dict]`, `reason_ar: str`
- `def evaluate_suitability(crop_id: str, governing: list[GoverningFactor], modifying: list[ModifyingFactor]) -> SuitabilityResult`
  - Gate 1 (agronomic). Governing first (knock-out), then weighted modifiers.

### `core/engines/water_cost.py` (121 أسطر)

**`class WaterCostInputs`**
  - الحقول: `well_depth_m: float`, `pump_type: str`, `pump_efficiency: float`, `diesel_price_usd_per_liter: Optional[float]`, `diesel_kwh_per_liter: float`, `solar_capital_usd: Optional[float]`, `solar_lifetime_years: int`, `solar_maintenance_annual_pct: float`, `solar_m3_per_year: Optional[float]`, `solar_dust_derate_pct: float`, `grid_price_usd_per_kwh: Optional[float]`, `grid_efficiency: float`
- `def water_cost_per_m3(inp: WaterCostInputs) -> dict`
  - Return {low, high, mid, basis} in USD/m3. Range, not a fake point.
- `def seasonal_water_cost(inp: WaterCostInputs, etc_m3_per_ha: float, area_ha: float) -> dict`
  - Total seasonal water cost for a field as a range.

### `core/engines/yield_interval.py` (70 أسطر)

**`class YieldInterval`**
  - الحقول: `status: str`, `point_estimate: float | None`, `lower: float | None`, `upper: float | None`, `coverage: float | None`, `n_calibration: int`, `note_ar: str`
- `def conformal_interval(point_estimate: float, calibration_residuals: list[float], coverage: float = 0.9) -> YieldInterval`
  - Build a conformal prediction interval from held-out residuals.
- `def pending_estimate() -> YieldInterval`
  - Explicit 'not yet calibrated' — the honest default for Al-Jawf now.

---

## الطبقة 2: الاستشعار المكاني (`core/spatial/`)

### `core/spatial/index_scheduler.py` (124 أسطر)

**`class IndexCadence`**
**`class IndexPolicy`** — سياسة تفعيل مؤشّر — متى يُحسب ولماذا.
  - الحقول: `index_id: str`, `cadence: IndexCadence`, `purpose_ar: str`, `refresh_days: int | None`, `rationale_ar: str`
- `def get_index_policy(index_id: str) -> IndexPolicy | None`
  - يُرجع سياسة تفعيل مؤشّر.
- `def should_compute_now(index_id: str, days_since_last: int | None, purpose_active: bool = False) -> dict`
  - يقرّر هل يُحسب المؤشّر الآن — يوفّر التكلفة بتجنّب الحساب غير الضروري.
- `def cost_summary(active_indices: 'list[str]') -> dict`
  - يلخّص أي المؤشّرات دائمة (تكلفة متكرّرة) وأيها عند الطلب (تكلفة مرّة).

### `core/spatial/indicators.py` (265 أسطر)

**`class SpatialIndex`** — المؤشرات القابلة للعرض المكاني (لكل بكسل).
**`class GeoBBox`** — الإطار الجغرافي للـ grid (لتحويل البكسل لإحداثية).
  - الحقول: `min_lon: float`, `min_lat: float`, `max_lon: float`, `max_lat: float`
**`class Severity`**
**`class ZoneOfInterest`** — منطقة اهتمام مكتشفة — بإحداثية يمكن الوصول لها.
  - الحقول: `index: SpatialIndex`, `center_lon: float`, `center_lat: float`, `pixel_count: int`, `mean_value: float`, `field_mean: float`, `severity: Severity`, `interpretation_ar: str`, `farmer_knowledge_match: str`, `directs_sampling: bool`
- `def detect_zones_of_interest(grid: 'list[list[float]]', index: SpatialIndex, bbox: GeoBBox, threshold_std: float = 1.0, min_cluster: int = 3) -> list[ZoneOfInterest]`
  - يكشف مناطق القيم الشاذّة (أعلى/أقل من المتوسط بانحراف معياري).
- `def link_farmer_knowledge(zones: list[ZoneOfInterest], farmer_knowledge: list) -> list[ZoneOfInterest]`
  - يربط منطقة الاهتمام بمعرفة المزارع المكانية (إن طابقت النطاق).
**`class SoilZone`** — منطقة تربة مصنّفة من BSI — لخريطة تنوّع النسيج (موجّه لا حاكم).
  - الحقول: `center_lon: float`, `center_lat: float`, `pixel_count: int`, `texture_class: str`, `mean_bsi: float`, `confidence: str`, `directs_sampling: bool`, `note_ar: str`
- `def classify_soil_zones(bsi_grid: 'list[list[float]]', ndvi_grid: 'list[list[float]]', bbox: 'GeoBBox', min_cluster: int = 3) -> list[SoilZone]`
  - يقسّم الحقل لمناطق نسيج تربة من شبكة BSI — خريطة تنوّع التربة.

### `core/spatial/pipeline.py` (377 أسطر)

**`class Satellite`**
**`class ImageQuality`**
**`class FieldAOI`** — منطقة الاهتمام = حدود الحقل (تأتي من PostGIS / GeoJSON).
  - الحقول: `tenant_id: str`, `field_id: str`, `polygon: list[tuple[float, float]]`, `min_lon: float`, `min_lat: float`, `max_lon: float`, `max_lat: float`
**`class AcquisitionPlan`** — خطة الجلب — متى وأي قمر.
  - الحقول: `aoi: FieldAOI`, `revisit_days: int`, `prefer: Satellite`, `fallback: Satellite`
- `def decide_source(cloud_cover_pct: float) -> tuple[Satellite, ImageQuality]`
  - بوابة السحب (C6): يقرّر المصدر حسب الغطاء السحابي.
**`class RasterTile`** — بلاطة مؤشر مكاني — تُعرض فوق الخريطة. metadata في SQLite،
  - الحقول: `tenant_id: str`, `field_id: str`, `index_name: str`, `capture_date: str`, `satellite: str`, `quality: str`, `cloud_cover_pct: float`, `geotiff_path: str`, `png_overlay_path: str`, `thumbnail_path: str`, `mean_value: float | None`, `min_value: float | None`, `max_value: float | None`
- `def compute_ndvi_from_bands(nir, red)`
  - NDVI = (NIR - Red)/(NIR + Red). يعمل على numpy arrays.
**`class TimelineEntry`** — مدخل في شريط الزمن أسفل الخريطة — تاريخ + صورة مصغّرة.
  - الحقول: `capture_date: str`, `index_name: str`, `thumbnail_path: str`, `mean_value: float | None`, `quality: str`
- `def build_timeline(tiles: list[RasterTile]) -> list[TimelineEntry]`
  - يبني شريط الزمن للمقارنة (الأحدث أولاً).
- `def detect_temporal_change(timeline: list[TimelineEntry], index_name: str) -> dict`
  - كشف التغيّر الزمني (إنذار مبكر): هل المؤشر يتدهور؟
- `def polygon_area_ha(coords: list[tuple[float, float]]) -> float`
  - مساحة مضلّع بالهكتار من إحداثيات (lon, lat) بالدرجات.
- `def compute_bsi_from_bands(swir1, red, nir, blue)`
  - مؤشر التربة العارية (Bare Soil Index) من نطاقات Sentinel-2.
- `def estimate_soil_texture(bsi: float, ndvi: float) -> dict`
  - يقدّر نسيج التربة التقريبي (S8) من BSI + السطوع.
- `def clay_minerals_ratio(swir1, swir2)`
  - نسبة المعادن الطينية = SWIR1/SWIR2 (نطاقا Sentinel-2 B11/B12).
- `def iron_oxide_ratio(red, blue)`
  - نسبة أكاسيد الحديد = Red/Blue. مرتفع = تربة غنية بالحديد (حمراء).
- `def refine_soil_texture(bsi: float, ndvi: float, clay_ratio: float = None, iron_ratio: float = None) -> dict`
  - يدقّق تقدير النسيج بدمج BSI مع مؤشّري الطين/الحديد (إن توفّرا).
- `def detect_growth_stage_from_ndvi(ndvi_series: 'list[tuple[int, float]]') -> dict`
  - يستنتج مرحلة النمو من شكل منحنى NDVI الزمني (يوم السنة, NDVI).
- `def crop_type_consistency_check(observed_ndvi_peak: float, expected_crop: str, expected_peak_range: 'tuple[float, float]') -> dict`
  - يتحقّق أن منحنى NDVI يطابق المحصول المُدخَل (يكشف الشذوذ).
- `def estimate_lai_from_ndvi(ndvi: float) -> dict`
  - يقدّر LAI (مساحة الورقة) من NDVI عبر علاقة لوغاريتمية تجريبية.

---

## الطبقة 3: الموصّلات (`core/connectors/`)

### `core/connectors/base.py` (84 أسطر)

**`class FetchStatus`**
**`class ConnectorResult`** — نتيجة موحّدة من أي موصّل — تحمل نسبها (provenance).
  - الحقول: `source: str`, `status: FetchStatus`, `data: dict[str, Any]`, `error_margin: float`, `fetched_at: str`, `note_ar: str`
**`class BaseConnector`** — الأساس المشترك. كل موصّل خارجي يرثه.
  - الحقول: `source_name: str`, `requires_key: bool`, `key_env_var: str`

### `core/connectors/copernicus.py` (118 أسطر)

**`class ImageryRequest`** — طلب صورة لحقل (AOI) في فترة زمنية.
  - الحقول: `field_polygon: list`, `date_from: str`, `date_to: str`, `index: str`, `max_cloud_pct: float`
**`class CopernicusConnector`**

### `core/connectors/farmonaut.py` (158 أسطر)

**`class ImageType`**
- `def validate_field_polygon(points: dict) -> tuple[bool, str]`
  - التحقق من صحة حدود الحقل قبل الإرسال (درس من الدليل).
**`class CreditEstimate`** — تقدير تكلفة الـ Credits قبل الاستدعاء (شفافية التكلفة).
  - الحقول: `satellite_units: int`, `weather_units: float`, `api_units: float`, `total_units: float`, `cost_usd: float`
- `def estimate_monthly_credits(hectares: float, fields_count: int, weather_calls_per_day: int = 4) -> CreditEstimate`
  - تقدير التكلفة الشهرية (يطابق حاسبة الدليل).
**`class SenseDay`** — يوم تصوير قمر.
  - الحقول: `date: str`, `is_cloudy: bool`, `crop_red_zone: float | None`, `irrigation_red_zone: float | None`
**`class FarmonautConnector`**

### `core/connectors/weather_openmeteo.py` (93 أسطر)

**`class WeatherInputs`** — مدخلات FAO-56 الجوية — جاهزة لـ fao56.WeatherDay.
  - الحقول: `temp_max_c: float`, `temp_min_c: float`, `humidity_pct: float`, `wind_speed_ms: float`, `solar_radiation_mj: float`, `rainfall_mm: float`, `latitude: float`, `elevation_m: float`
**`class OpenMeteoConnector`**

---

## الطبقة 4: التعلّم والمعايرة (`core/learning/`)

### `core/learning/calibration_loop.py` (186 أسطر)

**`class CalibrationResult`**
  - الحقول: `district_id: str`, `status: str`, `zone_factor: float | None`, `n_seasons: int`, `n_farms: int`, `farms_required: int`, `method: str`, `confidence: str`, `note_ar: str`
- `def read_yield_history(tenant_dir: Path) -> list[dict]`
  - Read actual weighed-harvest records (ground truth G1).
- `def calibrate_zone_factor(actual_yields: list[float], model_predicted: list[float]) -> float | None`
  - Calibrate zone_factor, choosing method by data character.
- `def calibration_method_used(actual_yields: list[float], model_predicted: list[float]) -> str`
  - Report which method was applied + honest data-sufficiency note.
- `def run_calibration(district_dir: Path, tenant_dirs: list[Path], model_predict_fn) -> CalibrationResult`
  - Calibrate a region from its tenant farms' actual harvests.
- `def write_calibration(district_dir: Path, result: CalibrationResult) -> None`
  - Persist calibration OUTPUT to districts/<region>/climate.yaml.

### `core/learning/model_selector.py` (102 أسطر)

**`class ModelTier`**
**`class ModelDecision`**
  - الحقول: `allowed_model: ModelTier`, `raw_points: int`, `effective_points: int`, `n_independent_units: int`, `expected_r2_range: str`, `confidence: str`, `rationale_ar: str`
- `def effective_sample_size(n_records: int, n_farms: int, n_seasons: int) -> int`
  - Honest effective N, accounting for pseudoreplication.
- `def select_model(n_records: int, n_farms: int, n_seasons: int) -> ModelDecision`
  - Return the most complex model the data HONESTLY supports.

### `core/learning/recommendation_log.py` (129 أسطر)

**`class RecommendationRecord`**
  - الحقول: `rec_id: str`, `tenant_id: str`, `district_id: str`, `zone_id: str`, `crop: str`, `issued_date: str`, `recommendation_ar: str`, `quality_grade: str`, `predicted_yield_t_ha: float | None`, `confidence: str`, `actual_yield_t_ha: float | None`, `outcome_date: str | None`, `error_pct: float | None`
- `def log_recommendation(log_path: Path, rec: RecommendationRecord) -> None`
  - Append a recommendation (outcome fields empty until harvest).
- `def record_outcome(log_path: Path, rec_id: str, actual_yield: float, outcome_date: str) -> bool`
  - Bind an actual harvest result to a prior recommendation.
- `def compute_mape(log_path: Path) -> dict`
  - MAPE over records that have BOTH prediction and outcome.
- `def load_log(log_path: Path) -> list[RecommendationRecord]`

---

## الطبقة 5: الاستدلال والقرار

### `core/evidence_class.py` (215 أسطر)

**`class EvidenceClass`**
**`class EvidenceRuling`** — حكم على مشاهدة: أقرينة هي أم دليل، وما يجوز بناؤه عليها.
  - الحقول: `observable_id: str`, `observation_type: str`, `evidence_class: EvidenceClass`, `can_govern_decision: bool`, `can_lift_blocked: bool`, `max_confidence: str`, `note_ar: str`
- `def classify_evidence(observable_id: str, observation_type: str) -> EvidenceRuling`
  - يصنّف مشاهدة كقرينة أو دليل، ويحدّد ما يجوز بناؤه عليها.
- `def enforce_indication_ceiling(observable_id: str, observation_type: str, proposed_confidence: str) -> dict`
  - يفرض سقف ثقة القرينة: حتى لو اقترح النظام ثقة عالية لقرينة، تُخفَّض.
- `def explain_evidence_principle_ar() -> str`
  - شرح المبدأ للعرض في الواجهة/التوثيق.
**`class Corroboration`** — نتيجة تضافر عدّة قرائن حول نفس الاستنتاج.
  - الحقول: `target_ar: str`, `n_indications: int`, `n_independent_sources: int`, `agree: bool`, `elevated_confidence: str`, `can_govern: bool`, `lifts_blocked: bool`, `note_ar: str`
- `def corroborate_indications(target_ar: str, indications: 'list[tuple[str, bool]]') -> Corroboration`
  - يقيّم تضافر عدّة قرائن. ترقى الثقة مع الاتفاق والاستقلال —

### `core/field_lifecycle.py` (126 أسطر)

**`class FieldQualityState`**
**`class SoilTestChoice`** — قرار المزارع بشأن فحوصات التربة.
- `def resolve_state(soil_choice: SoilTestChoice, provided_governors: set[str], lab_request_pending: bool = False) -> tuple[FieldQualityState, list[str]]`
  - يحدّد حالة الحقل + التوصيات المتاحة.
- `def can_recommend(state: FieldQualityState, recommendation_type: str) -> tuple[bool, str]`
  - هل يُسمح بنوع توصية معيّن في هذه الحالة؟
- `def state_explanation_ar(state: FieldQualityState) -> dict`
  - شرح الحالة للمزارع (شفافية).

### `core/provenance.py` (135 أسطر)

**`class Stage`**
**`class Status`**
**`class Confidence`**
- `def confidence_from_error(relative_error: float) -> Confidence`
  - Map a relative error to a confidence category (never a fake %).
**`class Provenance`** — The lineage record attached to every information value.
  - الحقول: `name: str`, `value: Any`, `unit: str`, `stage: Stage`, `status: Status`, `source: str`, `ground_truth: str`, `error: float`, `verification: str`, `inputs: list['Provenance']`, `citation: str`
- `def propagate_multiply(a: Provenance, b: Provenance) -> float`
  - Relative errors add in quadrature for z = a*b.
- `def propagate_add(values_errors: list[tuple[float, float]]) -> float`
  - Absolute errors add in quadrature for z = x+y+...; returns abs error.
- `def pending(name: str, unit: str, ground_truth: str, verification: str = '') -> Provenance`

### `core/recommendation_engine.py` (241 أسطر)

**`class RecommendationStatus`**
**`class FarmerSignal`** — إشارة بصرية بسيطة للمزارع — لا أرقام معقّدة.
**`class BackendDetail`** — كل المؤشرات الخام والوسيطة. للمهندس/المطوّر/التدقيق فقط.
  - الحقول: `et0_mm: float | None`, `etc_mm: float | None`, `kc: float | None`, `salinity_ks: float | None`, `irrigation_m3_ha: float | None`, `irrigation_error_pct: float | None`, `suitability_class: str | None`, `governing_failures: list[str]`, `quality_grade: str`, `missing_observables: list[str]`, `zone_factor: float | None`, `zone_factor_status: str`, `local_knowledge_applied: list[dict]`, `provenance_chain: list[dict]`
**`class FarmerView`** — ما يراه المزارع. لا معادلات، لا نسب خطأ — قرار قابل للتنفيذ.
  - الحقول: `signal: FarmerSignal`, `headline_ar: str`, `reason_ar: str`, `confidence_ar: str`, `alerts_ar: list[str]`, `next_action_ar: str`
**`class Recommendation`**
  - الحقول: `status: RecommendationStatus`, `farmer_view: FarmerView`, `backend: BackendDetail`, `predicted_yield_t_ha: float | None`, `confidence: str`
- `def generate_recommendation(validation: dict, irrigation = None, suitability = None, zone_factor: float | None = None, zone_factor_status: str = 'pending', local_knowledge: list | None = None, field_state: str | None = None) -> Recommendation`
  - يولّف كل المخرجات في توصية واحدة، مع فصل backend عن المزارع.

---

## الطبقة 6: سياق المزارع

### `core/anwa_calendar.py` (113 أسطر)

**`class StarSeason`** — نجم زراعي (نوء) ودلالته الموسمية.
  - الحقول: `name_ar: str`, `approx_start_ar: str`, `duration_days: int`, `agricultural_meaning_ar: str`
- `def get_star_season(star_id: str) -> StarSeason | None`
**`class TimingContext`** — سياق توقيت من العرف النجمي — قرينة محترمة لا حاكمة.
  - الحقول: `star_ar: str`, `traditional_advice_ar: str`, `weight: float`, `is_governing: bool`, `agrees_with_weather: bool | None`, `note_ar: str`
- `def anwa_timing_context(star_id: str) -> TimingContext | None`
  - يعطي سياق توقيت من العرف النجمي، ويتقاطع مع الطقس الفعلي.
- `def explain_anwa_principle_ar() -> str`
  - شرح مكانة الأنواء للعرض.

### `core/data_completeness.py` (130 أسطر)

**`class CompletenessResult`**
  - الحقول: `score: int`, `provided: list[str]`, `missing: list[str]`, `next_value: str`, `headline_ar: str`, `is_precise: bool`
- `def compute_completeness(provided_fields: set[str]) -> CompletenessResult`
  - يحسب درجة الاكتمال + الرسالة التحفيزية.
**`class NotificationTrigger`** — أنواع الإشعارات التحفيزية اللاحقة.
- `def build_notification(trigger: str, field_name: str, completeness: CompletenessResult | None = None) -> dict`
  - يبني إشعاراً تحفيزياً (للإرسال عبر التطبيق/WhatsApp لاحقاً).

### `core/day_zero_advisory.py` (142 أسطر)

**`class AdvisoryItem`** — بند توصية استرشادي — يحمل ثقته وما يرفع دقّته.
  - الحقول: `topic_ar: str`, `advice_ar: str`, `confidence: str`, `source_ar: str`, `upgrade_ar: str`
**`class DayZeroAdvisory`** — التوصية الاسترشادية الكاملة لحظة الإنشاء.
  - الحقول: `field_id: str`, `items: list[AdvisoryItem]`, `headline_ar: str`, `disclaimer_ar: str`, `next_steps_ar: list[str]`, `missing_for_precision_ar: list[str]`
- `def build_day_zero_advisory(field_id: str) -> DayZeroAdvisory`
  - يبني توصية استرشادية من كل المتاح لحظة الإنشاء.

### `core/district_baseline.py` (103 أسطر)

**`class DistrictBaseline`** — خط أساسي لمديرية من المزارعين الواعين — سياق لا حقيقة فردية.
  - الحقول: `district_id: str`, `observable_id: str`, `n_farms: int`, `median_value: float | None`, `mean_value: float | None`, `spread: float | None`, `confidence: str`, `is_usable: bool`, `note_ar: str`
- `def compute_district_baseline(district_id: str, observable_id: str, analyzed_values: list[float]) -> DistrictBaseline`
  - يبني خطاً أساسياً من قيم المزارع المُحلَّلة فعلياً في المديرية.
**`class FarmerContext`** — ما يُعرض للمزارع البسيط: سياق مديريته، لا قيمة حقله.
  - الحقول: `headline_ar: str`, `context_ar: str`, `is_field_specific: bool`, `motivation_ar: str`, `blocks_precise: bool`
- `def context_for_low_data_farmer(baseline: DistrictBaseline, observable_name_ar: str) -> FarmerContext`
  - يحوّل خط أساس المديرية لسياق محفّز للمزارع البسيط.

### `core/farmer_agency.py` (98 أسطر)

**`class FarmerResponse`**
**`class AdvisoryDecision`** — توصية مع احتفاظ المزارع بقراره النهائي.
  - الحقول: `recommendation_ar: str`, `confidence: str`, `response: FarmerResponse`, `why_rejected_ar: str | None`, `farmer_modification_ar: str | None`, `framed_as_advice: bool`
- `def record_farmer_response(decision: AdvisoryDecision, response: FarmerResponse, why_rejected_ar: str | None = None, modification_ar: str | None = None) -> AdvisoryDecision`
  - يسجّل ردّ المزارع. الرفض يتطلّب سبباً (تغذية راجعة للتعلّم).
**`class RejectionPattern`** — نمط رفض متكرّر = إشارة أن الخوارزمية قد تخطئ محلياً.
  - الحقول: `recommendation_type_ar: str`, `total: int`, `rejected: int`, `rejection_rate: float`, `signal_ar: str`
- `def analyze_rejection_pattern(recommendation_type_ar: str, decisions: list[AdvisoryDecision]) -> RejectionPattern`
  - يحلّل رفض المزارعين لنمط توصية. الرفض المتكرّر إشارة تعلّم:

### `core/soil_recommendations.py` (145 أسطر)

**`class FertilizerHint`**
  - الحقول: `soil_ph: float | None`, `ph_class: str`, `hints_ar: list[str]`, `requires_lab: bool`, `note_ar: str`
- `def fertilizer_hint_from_ph(soil_ph: float | None) -> FertilizerHint`
  - يحوّل pH التربة لإرشادات تسميد. pH حاكم صارم → null بلا مختبر.
**`class IrrigationHint`**
  - الحقول: `texture: str`, `pattern_ar: str`, `rationale_ar: str`
- `def irrigation_hint_from_texture(texture: str) -> IrrigationHint | None`
  - يربط نسيج التربة بنمط الري. يكمّل fao56 (الذي يحسب الكمّية الدقيقة).
**`class CropBias`**
  - الحقول: `texture: str`, `favored_ar: list[str]`, `cautioned_ar: list[str]`, `warning_ar: str`
- `def crop_bias_from_texture(texture: str) -> CropBias | None`
  - يُنتج *ترجيحاً* للمحاصيل من النسيج — لا قراراً نهائياً.
- `def soil_to_recommendations(texture: str | None, soil_ph: float | None) -> dict`
  - يجمع التوصيات الثلاث من خصائص التربة (فكرة المستخدم المتكاملة).

---

## الطبقة 7: بطاقات المحاصيل (`core/crop_cards/`)

### `core/crop_cards/loader.py` (133 أسطر)

- `def load_crop_card(crop_id: str) -> dict | None`
  - يحمّل بطاقة محصول بمعرّفها (مع حماية من path traversal).
- `def list_crop_cards() -> list[str]`
  - يُرجع معرّفات كل البطاقات المتاحة (عدا القالب).
- `def validate_crop_card(card: dict) -> dict`
  - يتحقّق أن البطاقة تتبع القالب المعياري وتحترم حياد الموقع.
- `def load_variety_card(variety_id: str) -> dict | None`
  - يحمّل بطاقة صنف بمعرّفها (مع حماية من path traversal).
- `def list_variety_cards() -> list[str]`
  - يُرجع معرّفات كل الأصناف المتاحة.
- `def varieties_of_crop(crop_id: str) -> list[str]`
  - يُرجع أصناف محصول معيّن (ربط الصنف بمحصوله الأمّ).
- `def validate_variety_card(card: dict) -> dict`
  - يتحقّق أن بطاقة الصنف تتبع UPOV/Bioversity وتربط بمحصول موجود.

---

## جدول الاختبارات الفعلي (240 اختباراً، 24 ملفاً)

> توزيع حقيقي مُستخرَج من القرص. لا ملفات وهمية.

| ملف الاختبار | العدد | يحرس |
|------------|------|------|
| `test_soil_remote.py` | 26 | BSI، تقدير النسيج، خريطة تنوّع التربة، كشف مرحلة النمو |
| `test_engines.py` | 25 | FAO-56, fuzzy, fusion, market, provenance — لا أرقام وهمية |
| `test_crop_cards.py` | 20 | بطاقات المحاصيل + حماية path-traversal + cranberry المضادّ |
| `test_evidence_class.py` | 17 | تقنين القرينة/الدليل + التضافر + فرض السقف |
| `test_remaining_engines.py` | 13 | الخصوبة، تكلفة المياه، مجال الإنتاج (Conformal) |
| `test_soil_recommendations.py` | 12 | سلاسل التربة→الري/التسميد/المحصول |
| `test_learning.py` | 12 | سُلّم النماذج، المعايرة |
| `test_farmer_knowledge.py` | 10 | الوزن المحافظ، صفر على الحاكمات |
| `test_district_baseline.py` | 9 | التعلّم الجماعي المتدرّج (سياق المديرية) |
| `test_day_zero.py` | 8 | توصية استرشادية فورية عند الإنشاء |
| `test_completeness.py` | 8 | الاكتمال، الرسائل التحفيزية |
| `test_recommendation_log.py` | 7 | سجلّ التوصيات (أساس قياس الدقّة) |
| `test_index_scheduler.py` | 7 | المؤشّر عند الطلب (تقنين التكلفة) |
| `test_gaps_v91.py` | 7 | فجوات: الري، GDD، المساحة |
| `test_farmonaut.py` | 7 | SAR fallback، التحقّق، لا اختراع |
| `test_farmer_agency.py` | 7 | استقلالية المزارع (لا أمر) |
| `test_anwa_calendar.py` | 7 | الأنواء النجمية (قرينة توقيت) |
| `test_improvements_v91.py` | 6 | CHECK، تحقّق المصفوفة |
| `test_field_lifecycle.py` | 6 | الحالات الأربع، قاعدة السلامة |
| `test_connectors.py` | 6 | الموصّلات، لا مفاتيح بالكود |
| `test_security_v91.py` | 5 | foreign_keys، busy_timeout، sanitize_id |
| `test_recommendation_engine.py` | 5 | المايسترو، فصل FarmerView/Backend |
| `test_maestro_bridge.py` | 5 | ربط field_lifecycle بالمايسترو |
| `test_field_state.py` | 5 | تخزين الحالة، دورة المعمل |
| **المجموع** | **240** | 24 ملف |

---

## بطاقات المحاصيل والمصفوفة (قيم حقيقية)

### بطاقات المحاصيل (`core/crop_cards/*.yaml`) — محايدة الموقع، فيزياء وفسيولوجيا فقط

| البطاقة | عتبة الملوحة (dS/m) | ملاحظة |
|--------|-------------------|--------|
| `wheat` | 6.0 (انحدار 7.1) | OM الأمثل 1.3% (Nature Geoscience 2023، 13,662 تجربة) |
| `barley` | 8.0 | الأعلى تحمّلاً بين الحبوب |
| `millet` | 6.5 | — |
| `sorghum` | 6.8 | — |
| `cranberry` | 1.0 | **مثال مضادّ مقصود** — يجب أن يُرفَض لظروف اليمن (مُختبَر) |

**الأصناف** (`varieties/`، تتبع UPOV DUS + Bioversity passport، ترث حاكمات محصولها): `wheat_local_highland`، `sorghum_local_qairaa`.

### بنية القالب `_TEMPLATE.yaml`
```yaml
crop_id: string          # [A-Za-z0-9_] فقط
name_ar / name_en / crop_family: string
kc: { initial, mid, end: float, stage_days: [int,int,int,int], source }
salinity: { threshold_ece_ds_m, slope_pct_per_ds_m, sar_max, germination_ece_max, source }
thermal: { gdd_base_c, gdd_to_maturity, ... }
governing: { ph: {min,max}, ... }      # حاكمات صارمة
modifying: { organic_matter_pct: {...}, nitrogen/phosphorus/potassium_kg_ha }
```

### مصفوفة المشاهدات `observation_matrix.yaml`
تعرّف كل مشاهدة: `type` (`governing` حاكم / `modifying` مُرجِّح / `diagnostic` قرينة)، `source`, `error`, `criticality`.

| المعرّف | النوع | الوصف | المصدر |
|--------|------|------|--------|
| `C1–C7` | governing | البيانات المناخية | Open-Meteo |
| `S3` | governing | ملوحة التربة EC | مختبر |
| `S4/S5` | governing/modifying | pH / SAR | مختبر |
| `I3` | governing | جودة مياه الري EC | مختبر |
| `R5` | diagnostic | SI مؤشّر ملوحة | Sentinel (قرينة) |
| `R6` | diagnostic | SAR رادار | Sentinel-1 (قرينة) |

**القاعدة:** الحاكمات تتطلّب مختبراً؛ القرائن تقديرية بثقة منخفضة.

---

## الاختبارات الحرجة (تحرس المبادئ)

> أمثلة توضيحية لنمط الاختبارات التي تحرس كل مبدأ. الأسماء أدناه مبسّطة للتوضيح؛ في الكود الفعلي قد تختلف قليلاً (مثلاً `test_cranberry_extreme_salt_sensitivity`, `test_indication_capped_at_low_confidence`). المهمّ هو **ما تحرسه** لا اسمها الحرفي.

```python
# test_evidence_class.py — القرينة لا تتجاوز سقفها
def test_indication_ceiling_caps_not_rejects():
    """enforce_indication_ceiling يخفض الثقة (لا يرفض القرار)."""
    r = enforce_indication_ceiling("R5", "satellite", "high")
    assert r["allowed_confidence"] in ("low","medium")  # لا high
    assert r["was_capped"] is True

# test_evidence_class.py — الحاكم لا يُرفَع بالتضافر
def test_governing_blocked_never_lifted():
    """تضافر القرائن لا يرفع BLOCKED للحاكم الصارم."""
    # قرائن طيفية متضافرة لا تستبدل تحليل EC المخبري الغائب

# test_crop_cards.py — حماية path-traversal
def test_safe_id_rejects_traversal():
    assert _safe_id("../../etc/passwd") is None
    assert _safe_id("wheat_local") == "wheat_local"

# test_crop_cards.py — المثال المضادّ
def test_cranberry_extreme_sensitivity():
    """cranberry قيمه الحاكمة تجعله غير ملائم لليمن."""
    card = load_crop_card("cranberry")
    assert card["salinity"]["threshold_ece_ds_m"] <= 1.5
    assert card["thermal"]["chilling_hours_required"] >= 800

# test_day_zero.py — لا كذب في سياق المديرية
def test_district_context_never_field_value():
    adv = build_day_zero_advisory("F1", district_salinity_context=4.2)
    ctx = [i for i in adv.items if "الملوحة" in i.topic_ar][0]
    assert "ليس قيمة حقلك" in ctx.advice_ar

# test_day_zero.py — المبيدات محجوبة دائماً
def test_pesticides_always_blocked():
    adv = build_day_zero_advisory("F1", ndvi=0.5)
    assert any("محجوبة" in i.advice_ar for i in adv.items if "مبيد" in i.topic_ar)
```

---

## المتحقّق الآلي `tools_check_doc_consistency.py`

بوابة قبل كل تحزيم. يضمن ثلاثة تطابقات:

```python
# 1. عدد الاختبارات: القرص = جدول التوثيق = الرأس
disk_tests = sum(count test_* في كل tests/test_*.py)   # = 240

# 2. الواجهات العامة: القرص = التوثيق
#    (يعدّ ROOT/**/*.py بـ body، يستثني tests/ و__init__ و__pycache__)
api = sum(top-level class/def لا تبدأ بـ _)

# 3. حياد النواة
assert subprocess grep -rE "(sakha|6.17|142ha)" core/ يرجع فارغاً
```

إن اختلف أيّ عدّ → خطأ + إيقاف. هذا يمنع تناقضات التتبّع (الدرس المتكرّر: نسيان تحديث جدول عند إضافة اختبار).

---

## خريطة تدفّق القرار

```
إنشاء الحقل
  │
  ▼
day_zero_advisory ──► توصية استرشادية فورية (المتاح فقط، صريحة الحدود)
  │                    + district_baseline (سياق المديرية إن توفّر)
  ▼
connectors ──► طقس + صور (نسب موحّد) ──► provenance (كل قيمة بنسبها)
  │
  ▼
spatial/pipeline ──► NDVI/BSI/نسيج/مرحلة نمو ──┐
engines/fao56 ──► ري + ملوحة + GDD            │
                                               ▼
                                    evidence_class (قرينة؟ دليل؟ تضافر؟ سقف؟)
                                               │
                                               ▼
                          field_lifecycle (BLOCKED? LIMITED? READY?)
                                               │
                          ┌──── BLOCKED ───────┤
                          ▼                     ▼
                    لا توصية            engines/suitability
                  (القاعدة الذهبية)    (حاكم يُسقِط، مُرجِّح يوزن)
                                               │
                                               ▼
                                  recommendation_engine (المايسترو)
                                   ┌───────────┴───────────┐
                                   ▼                       ▼
                              FarmerView              BackendDetail
                           (إشارة + قرار)          (خام + نسب خطأ)
                                   │
                                   ▼
                          farmer_agency (هل توافق؟ — لا أمر)
                                   │
                          ┌────────┴────────┐
                       موافقة             رفض + سبب
                          │                  │
                          ▼                  ▼
              recommendation_log    analyze_rejection_pattern
              (بانتظار الحصاد)    (رفض متكرّر = راجع الخوارزمية)
                          │
                          ▼ (عند الحصاد الفعلي)
              learning/calibration_loop ──► zone_factor مُعايَر ──► دقّة أعلى للجميع
```

---

## سُلّم النماذج والمؤشّر عند الطلب

### سُلّم النماذج (`model_selector.select_model`)
| N الفعّال | النموذج | السبب |
|----------|--------|-------|
| <15 | قواعد + WOFOST | بيانات نادرة |
| 15–49 | TabPFN | مُدرَّب مسبقاً، بيانات صغيرة |
| 50–99 | LASSO | تنظيم، يتجنّب overfit |
| 100–199 | XGBoost | تفاعلات غير خطية |
| 200–499 | Random Forest | تنوّع أكبر |
| 500+ | BiLSTM | تسلسل زمني عميق |

`effective_sample_size` يحسب N الفعّال مراعياً الازدواج الكاذب.

### المؤشّر عند الطلب (`index_scheduler`)
| الفئة | المؤشّرات | التردد |
|------|----------|--------|
| `CONTINUOUS` | NDVI, NDMI, CWSI | كل 7-10 أيام |
| `ON_DEMAND` | BSI, نوع التربة | مرّة عند الإنشاء ثم يُوقَف |
| `EVENT` | SI ملوحة | عند الشكّ فقط |

---

## الحالات الأربع (`field_lifecycle`)

| الحالة | المعنى | المتاح | المبيدات |
|-------|--------|--------|---------|
| `BLOCKED` | حاكم غائب | لا توصية | محجوبة |
| `LIMITED` | أساسي فقط | عامّة (طقس، NDVI) | محجوبة |
| `PENDING_LAB` | بانتظار المختبر | عامّة + تنبيه | محجوبة |
| `READY` | كامل | دقيقة | متاحة |

---

## ملاحظة تنفيذية أخيرة (العائق الحقيقي)

ليس الكود هو العائق — كل الأدوات موجودة ومُختبَرة. العائق **تشغيلي**:
- صفر حصاد موزون فعلي (`zone_factor=null` في كل المديريات).
- لا تحاليل تربة مُدخَلة (S3/S4/S5 غائبة).
- حلقة المعايرة "ميّتة حية": مكتوبة ومُختبَرة، معطّلة حتى أوّل حصاد.

حتى ذلك الحين، `day_zero_advisory` و`district_baseline` هما الوضعان المُفعَّلان. النواة جاهزة لأوّل حصاد وأوّل تحليل.

### حدود معروفة (شفافية)
- **SQLite:** عزل برمجي (لا RLS) — كافٍ <50 مزرعة **مع مراجعة يدوية لكل استعلام**. عند 50+ → PostgreSQL+RLS.
- **API:** غير مبنيّة؛ المصادقة (JWT/RBAC) مؤجّلة — تُحتاج قبل الإنتاج.
- **خارج النطاق (DEFER):** audit trail، اختبار حمل، NDRE، BiLSTM (500+ نقطة).
