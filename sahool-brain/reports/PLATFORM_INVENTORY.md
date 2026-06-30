# جرد شامل لمنصّة SAHOOL — الخدمات والوظائف والخصائص (الواجهة + الخلفيّات)

> تقرير قابل للنسخ. مُولَّد من مسح فعليّ للمستودع (`v2.0.0_enhanced`).
> النطاق: ٢٦ خدمة خلفيّة + واجهة React 19. الأرقام مُقاسة من الشيفرة (عدد المسارات/الملفّات فعليّ).

---

## ١) نظرة عامّة على المعماريّة

- **مونوريبو** يضمّ `services/` (٢٦ خدمة)، `frontend/` (React 19 + Vite + TypeScript)، `agents/`، `bots/`، `mcp_servers/`، `shared/`، `migrations/`، `tools/`، `tests_v9/`.
- **الخدمة المحوريّة:** `sahool-platform` — مونوليث FastAPI مُفكَّك إلى **١٥٢ راوتر** تحت `api/routers/*.py` (تسجيل تلقائيّ عبر `register_routers` / pkgutil)، يخدم **٥٥٩ مساراً** على `/api/v1/*`.
- **بوّابة الواجهة → الخلفيّة:** nginx proxy (منفذ 3003 محلّيّاً) يوجّه `/api/v1/*` إلى الخدمات.
- **الرسائل/الأحداث:** NATS (مواضيع `sahool.*`)، Redis (cache/queue)، PostgreSQL + PostGIS (مكانيّ، RLS متعدّد المستأجرين)، Qdrant (متّجهات RAG).
- **CI:** Lint&Format (ruff)، Unit Tests (`pytest -m unit`)، Platform Unit Tests، Platform Structure Inspector (`tools/sahool_inspector.py`)، e2e Playwright، Security Scan (`pip-audit` + `bandit`).

---

## ٢) الخلفيّات — جرد الخدمات الـ٢٦ (الغرض + عدد المسارات)

| # | الخدمة | المسارات | الغرض |
|---|--------|:---:|-------|
| 1 | **sahool-platform** | **559** | المونوليث المحوريّ: الحقول/المزارع/المؤشّرات/الريّ/التوصيات/القرار/الطقس/التقارير/الإدارة (١٥٢ راوتر — انظر §٣) |
| 2 | **raster-service** | 62 | الصور الجوّية والراستر، بلاطات COG/TileJSON، مؤشّرات الغطاء النباتيّ، أقنعة الحقول، CDSE |
| 3 | **mcp_servers** | 32 | خوادم MCP (Model Context Protocol) لأدوات الوكلاء |
| 4 | **auth** | 27 | المصادقة/JWT، RBAC، المستأجرون، break-glass، تدقيق أمنيّ، `/readyz` |
| 5 | **odoo-bridge** | 10 | جسر ERP إلى Odoo (JSON-RPC/XML-RPC): المخزون/الشراء/المبيعات |
| 6 | **supervisor-agent** | 10 | وكيل مُشرِف هجين (Skills + توجيه هرميّ) لتنسيق المهامّ |
| 7 | **vegetation-analysis-service** | 8 | تحليل الغطاء النباتيّ (NDVI/EVI/SAVI…)، إحصاءات المنطقة |
| 8 | **video-processor** | 8 | معالجة تدفّق الفيديو (كاميرات الحقل/المراقبة) |
| 9 | **ai_agronomist** | 7 | المستشار الزراعيّ الذكيّ: توليد توصيات + حزمة سياق + شفافيّة الأدلّة (RAG/KG + مزوّدات LLM) |
| 10 | **guardrails-engine** | 7 | نظام أمان متعدّد الطبقات لمخرجات الذكاء الاصطناعيّ (حسّاس أمنيّاً) |
| 11 | **knowledge-graph** | 7 | الرسم المعرفيّ الزراعيّ (كيانات/علاقات/استعلام) |
| 12 | **tts-service** | 7 | تحويل النصّ إلى كلام (edge_tts) للإشعارات الصوتيّة |
| 13 | **actuator-service** | 6 | طبقة التفعيل IoT (صمّامات/مضخّات الريّ) |
| 14 | **soil-service** | 6 | بيانات/تحليل التربة (الملوحة/المغذّيات/القوام) |
| 15 | **agriai-engine** | 5 | محرّك استدلال زراعيّ |
| 16 | **edge-inference** | 5 | استدلال على الحافة (نماذج خفيفة) |
| 17 | **local-ai-rag** | 5 | RAG محلّيّ (Qwen3 + Ollama + Qdrant) |
| 18 | **rag-retrieval** | 5 | استرجاع المستندات للـRAG |
| 19 | **field-segmentation** | 4 | تجزئة حدود الحقول من الصور |
| 20 | **indicators-service** | 4 | نقطة دخول مؤشّرات (stub صحّيّ) |
| 21 | **sam2-inference** | 4 | استدلال SAM2 (Segment Anything) للأقنعة |
| 22 | **weather-service** | 4 | خدمة طقس رفيعة (stub صادق) |
| 23 | **qdrant-seed** | 0 | عامل تهيئة/بذر فهرس Qdrant (مهمّة، لا API) |
| 24 | **raster-tiler-service** | 0 | عامل توليد بلاطات الراستر |
| 25 | **weather-polygon-worker** | 0 | عامل شبكة الطقس على المضلّعات (NATS، خلف راية `WEATHER_GRID_PIPELINE_ENABLED`) |
| 26 | **weather-signal-engine** | 0 | محرّك إشارات الطقس (معالجة خلفيّة) |

**الإجمالي التقريبيّ: ~830 مساراً عبر الخدمات.**

---

## ٣) sahool-platform — تجميع الـ١٥٢ راوتر حسب المجال الوظيفيّ

### الحقول والمزارع والحدود
`fields` · `field_single` · `field_twin` · `field_intelligence` · `field_completeness` · `field_portfolio` · `field_ai_context` · `farms` · `boundaries` · `drawing_features` · `geo` · `geo_locate` · `districts` · `agro_zones` · `tenant` · `me` · `onboarding`

### المؤشّرات والاستشعار عن بُعد
`indicators` · `indices` · `ndvi_analysis` · `spatial` (عبر indicators) · `temporal` · `phenology` · `gdd` · `kc_timeseries`

### الريّ والمياه
`irrigation` · `irrigation_plan` · `irrigation_method` · `irrigation_network` · `irrigation_recommendation` · `water_balance` · `water_twin` · `water_ledger` · `water_sensitivity` · `water_harvesting` · `etc_dual` · `salinity`

### المحاصيل ودورة الحياة
`crops` · `crop_cards` · `crop_operations` · `crop_twin` · `crop_suitability` · `coffee` · `orchard` · `aromatic_crops` · `high_value_crops` · `niche_crops` · `fodder_alternatives` · `rotation` · `planting` · `propagation` · `seed` · `lifecycle` · `seasons` · `season_workspace` · `calendars` · `regional_calendar` · `cultural_calendar` · `astronomical_timing` · `agricultural_proverbs` · `climate_analogs`

### القرار والتوصيات والذكاء
`decision` · `decision_confidence` · `decision_dispatch` · `decision_explain` · `decision_impact` · `decision_policies` · `decision_record` · `confidence` · `confidence_gate` · `recommendations` · `prescriptions` · `agro_intelligence` · `ai_models` · `diagnose` · `simulate` · `scenario` · `outcome` · `consistency` · `policy_learning` · `learning` · `learning_summary` · `calibration`

### الأدلّة والنسب والتتبّع
`evidence` · `evidence_map` · `lineage` · `execution_lineage` · `execution_feedback` · `agronomic_replay` · `replay` · `harvest_traceability` · `data_readiness` · `readiness`

### العمليّات والمهامّ والمعدّات
`operations` · `tasks` · `activities` · `commands` · `automation` · `equipment` · `inventory` · `devices` · `device_twin` · `cameras` · `edge` · `escalation` · `pest_escalation` · `queue` · `farm_operations_ledger`

### الآفات والمغذّيات والتربة والممارسات
`ipm` · `scouting` · `observations` · `nutrients` · `soil_sampling` · `sampling` · `practices` · `chemical_safety` · `postharvest` · `trials`

### الطقس
`weather` · `weather_analytics` · `seasonal_risk`

### التحليلات والاقتصاد والـGIS
`analytics` · `economics` · `market` · `productivity` · `yield_analysis` · `yield_interval` · `field_intelligence` · `nl_gis` · `nl_sql` · `gis_kernel` · `gis_cloud_native`

### النماذج العلميّة الزراعيّة
`wofost` · `phenology` · `gdd` · `water_balance` · `kc_timeseries`

### التقارير والمشاركة والوثائق
`reports` · `sharing` · `documents` · `introduction`

### الإدارة والأمان والحوكمة
`admin` · `master_data` · `rbac` · `auth` · `settings` · `security_audit` · `break_glass` · `capabilities` · `registry` · `policy_learning` · `decision_policies`

### النواة والبنية التحتيّة
`events` · `notifications` · `sync` · `service_proxy` · `compat_gateway` · `failures` · `portfolio` · `portfolio_command`

---

## ٤) خصائص خلفيّة شاملة (Cross-cutting)

- **مزوّدات LLM متعدّدة قابلة للاختيار من الواجهة:** OpenRouter (DeepSeek/Claude Sonnet/Gemini) عبر `ai_provider_config` + `routers/ai_models.py`؛ خلف feature flag + سياسة المستأجر؛ المفاتيح من البيئة فقط؛ سقوط آمن إلى RAG/KG.
- **شفافيّة الأدلّة (AI Evidence Transparency):** كلّ توصية تحمل عناصر دليل (SATELLITE/WEATHER) + عدّ المصادر + حزمة سياق `GET /api/v1/fields/{id}/ai-context-pack`.
- **صور CDSE (Copernicus):** مؤشّرات `ndvi/evi/savi/msavi/ndwi/ndmi/moisture/gndvi/ndre/msi/ndsi`؛ بلاطات COG + مصغّرات (`cdse-thumbnail`)؛ نطاقات لونيّة `_INDEX_DOMAIN`.
- **اتّجاه الرياح مفتوح المصدر:** Open-Meteo (CC-BY) أساسيّ + MET Norway (`api.met.no`, CC-BY) احتياطيّ لاتّجاه الرياح؛ `nvl()` null-coalescing (لا يُسقِط 0°)؛ نقطة فحص حيّ `GET /api/v1/weather/wind-source-selftest`.
- **متعدّد المستأجرين + RLS:** عزل صفوف PostgreSQL؛ حارس دور قاعدة البيانات (`assert_db_role_rls_safe`)؛ تدقيق استعلامات المستأجر.
- **الأمان:** guardrails-engine متعدّد الطبقات؛ `pip-audit`+`bandit` بوّابة CI؛ JWT ≥32 حرفاً؛ RBAC + break-glass + تدقيق.
- **التحقّق البنيويّ:** `sahool_inspector` (فحص تفويض النقاط، مواضيع NATS، تفكيك الراوترات)؛ حُرّاس تفكيك ساكنة.
- **العلوم الزراعيّة:** WOFOST، GDD، توازن المياه، ETc مزدوج، سلاسل Kc الزمنيّة، أطوار النموّ.

---

## ٥) الواجهة — جرد الـ٦٧ مساراً (تجميع حسب المجال)

### اللوحات الرئيسة والتشغيل
`dashboard/` · `ops-wall` (جدار مركز العمليّات) · `alerts` (نظام التنبيهات) · `assistant` (المساعد الذكيّ)

### الحقول والخرائط
`fields` (حقولي) · `farm-map` · `field-workspace` · `map-center` · `satellite` · `indices` · `spatial` (المؤشّرات المكانيّة) · `phenology`

### الكشف والآفات والوصفات
`scouting` · `pest` · `prescriptions` · `lab-sampling`

### الريّ (مجموعة كاملة)
`maestro` · `irrigation` + `plan` · `water-twin` · `etc-dual` · `ops` · `network` · `portfolio` · `portfolio-command`

### المحاصيل والطقس
`crop/state` · `crop/weather`

### التحليلات
`analysis` + `economics` · `yield` · `field-ranking` · `problem-fields` · `nl-gis` · `sql-workspace` · `gis-tools` · `scenario-compare`

### التقارير
`reports` + `advisory` · `recommendations`

### المتقدّم (Advanced)
`decision-studio` · `decision-confidence` · `execution-feedback` · `agronomic-timeline` · `learning` · `calibration` · `calibration-workbench` · `lineage` · `evidence-map` · `replay-map`

### العمليّات والأصول
`ops/tasks` · `activities` · `inventory` · `equipment` · `devices` · `device-twin`

### المعاينة (Preview)
`preview/*`: `unified` · `command` · `tasks` · `rec-flow` · `hybrid-monitor` · `analyze` · `setup` · `field-app`

### الإدارة والإعدادات
`admin` · `master-data` · `documents` · `governance` · `settings`

---

## ٦) الواجهة — الأقسام (Sections) الـ٩٠

DashboardPage · OperationCenterWallPage · AlertSystemPage · ChatbotPage · NotificationCenter · NotificationSettingsPage ·
MyFieldsPage · FarmMapOverview · FieldWorkspaceMapCard · FieldMapCenter · SatellitePage · SpatialIndicatorsPage · PhenologyView ·
MapHub · FieldIntelligencePage · FieldManagementPage · FarmCreatePage · FieldEntryWizard · FieldSetupWizard ·
ScoutingView · PestEscalationPage · PrescriptionBuilderPage · LabSamplingPage ·
IrrigationPlanPage · IrrigationOpsPage · IrrigationNetworkPage · IrrigationWaterPage · WaterTwinPage · EtcDualPage · PortfolioPage · PortfolioCommandPage ·
CropStatePage · WeatherAdvicePage ·
AnalyticsPage · EconomicsDashboard · YieldAnalysisPage · FieldRanking · ProblemFields · NlGisPage · SQLWorkspacePage · GisToolsPage · ScenarioComparePage ·
ReportsPage · FarmAdvisoryReport · RecommendationPage · RecommendationFlow ·
DecisionStudioPage · DecisionConfidencePage · ExecutionFeedbackPage · AgronomicTimelinePage · LearningDashboardPage · CalibrationPage · CalibrationWorkbenchPage · LineagePage · EvidenceMapPage · ReplayMapPage ·
ActivitiesPage · TasksPage · FieldTasksCabin · InventoryPage · EquipmentPage · DevicesPage · DeviceTwinPage ·
UnifiedCabin · OperationCommand · AnalyzeCabin · SetupCabin · HybridMonitor · HybridIndexPage · FieldAppPreview ·
MasterDataPage · DocumentsPage · GovernancePage · SettingsPage

*(يشمل أيضاً ملفّات اختبار `*.test.tsx` المرافقة لبعض الأقسام.)*

---

## ٧) الواجهة — البنية التقنيّة

- **مجموعات المكوّنات (`components/`):** `ds` (نظام التصميم) · `fieldhealth` · `fieldsetup` · `insights` · `maphub` (HubMap/HubMapGL/MapIndicatorLegend/DateScrubber) · `sharing` · `shell` (الهيكل/التنقّل) · `sql`
- **الخرائط:** Leaflet + MapLibre GL؛ `FieldIndicatorMap` (TileJSON legend) · `MapHub` (HubMap/HubMapGL) · `MapIndicatorLegend` العموديّة الموحَّدة (تظهر عند تفعيل مؤشّر فقط).
- **الحالة والبيانات:** zustand (stores) · react-query (`useApi`) · react-router · `useDuckDB` (تحليلات في المتصفّح) · WebSocket (`websocket.ts`).
- **الخطّافات (`hooks/`):** `useApi` · `useAuth` · `useDuckDB` · `useFieldContext` · `useFieldOptions` · `useIndicators` · `useScouting` · `useSelectedField` · `useTenantConfig` · `useTheme`
- **الخدمات (`services/`):** `api.ts` (عميل REST + `fieldCdseThumbnailUrl`) · `duckdb.ts` · `websocket.ts`
- **الواجهة الافتراضيّة للحقل (قرار مؤكَّد):** فتح حقل من «حقولي» ⇒ **صورة القمر الصناعيّ الخام** (`activeIndicator=null`)، لا طبقة NDVI؛ الأسطورة العموديّة الموحَّدة تظهر فقط عند تفعيل مؤشّر.
- **الاختبار:** vitest (وحدة + حُرّاس ساكنة) + Playwright (e2e، مع وسوم `@visual`/`@gating`).
- **التحريك/الأيقونات:** framer-motion · lucide-react.

---

## ٨) ملخّص الأرقام

| المقياس | القيمة |
|---------|:---:|
| خدمات خلفيّة | 26 |
| مسارات الخلفيّة (إجمالاً) | ~830 |
| راوترات sahool-platform | 152 |
| مسارات sahool-platform | 559 |
| مسارات الواجهة (التنقّل) | 67 |
| أقسام الواجهة (`sections/*.tsx`) | 90 |
| مجموعات المكوّنات | 8 |
| الخطّافات (hooks) | 11 |
| مؤشّرات CDSE | 11 |

---

*انتهى التقرير — مُولَّد من مسح الشيفرة الفعليّ.*
