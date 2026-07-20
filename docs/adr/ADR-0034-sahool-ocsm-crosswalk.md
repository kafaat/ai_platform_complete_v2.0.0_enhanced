# ADR-0034 — Crosswalk: عقود SAHOOL ↔ OCSM (SEM-OCSM-01)

- **الحالة:** Proposed / Deferred (خريطة مرجعيّة — **لا تغيير عقد**)
- **التاريخ:** 2026-07-19
- **النطاق:** Field/Parcel · Season/Crop · Irrigation · Weather/Soil observation
- **الأثر الكوديّ:** صفر تغيير على `shared/contracts/*` أو نماذج pydantic. وثيقة + حارس «مرجع لا تبنٍّ» فقط.

## المرجع المُثبَّت (جُلِب لا من الذاكرة)
- **المعيار:** OpenAgri Common Semantic Model (OCSM) — قائم على AIM (sdm:) + Ploutos PCSM.
- **المصدر:** https://github.com/agstack/OpenAgri-OCSM
- **النسخة المثبَّتة:** `main @ 12863f1bff88311f2274e80e691c8888bcb8af00` (2025-10-07T16:55Z) — **بلا release موسوم** (85 commits).
- **retrieved_at:** 2026-07-19 · **الرخصة:** CC-BY-4.0 (+ EUPL-1.2 مشار إليها).
- **الفضاء:** `https://w3id.org/ocsm/` (سياق: `https://w3id.org/ocsm/main-context.jsonld`) · تنسيق JSON-LD.
- **الأصول العلوية المعاد استخدامها:** SOSA/SSN · SAREF4AGRI · FOODIE · INSPIRE · GeoSPARQL · RDF Data Cube · AGROVOC · EPPO.
- **ملاحظة صدق حاكمة:** OCSM الأساسيّ **لا يُعرّف صنفاً صريحاً لـSeason ولا لـIrrigation** — الأوّل يعيش في FOODIE/FarmCalendar،
  والثاني في خدمة OpenAgri-IrrigationManagement المنفصلة. هذا يُفسّر كثافة `absent` في هذين العنقودَين (نتيجة حقيقيّة لا نقص تعيين).

## القرار
اعتماد هذه الخريطة **مرجعاً** يوجّه تسمية مفاتيح مظروف B1 (SCOUT-INGEST) ويوثّق كلّ انحراف بقرار. **لا** اعتماد OCSM،
**لا** إعادة تسمية حقل، **لا** مُسلسِل/تبعيّة runtime. التنفيذ الفعليّ مؤجَّل خلف محفّز صريح (أسفل).

## مِسطرة التصنيف
`match` = نفس المفهوم + بنية/وحدة متوافقة · `diverge` = نفس المفهوم بشكل/وحدة/عدديّة مختلفة · `absent` = لا مقابل في OCSM الأساسيّ.
قرار كلّ `diverge`/`absent`: **(أ)** جسر عند حدّ B1 · **(ب)** إبقاء محلّيّ مبرَّر · **(ج)** اعتماد مؤجَّل بمحفّز.

---

## العنقود 1 — Field/Parcel
مصدر SAHOOL: `services/sahool-platform/api/field_models.py:24-90` · مقابل OCSM: `saref4agri:Parcel` / `foodie:Plot` / `sdm:AgriParcel`.

| حقل SAHOOL | مقابل OCSM | الحكم | القرار |
|---|---|---|---|
| `field_id` (str) | معرّف Parcel (IRI) | diverge | (أ) جسر: str→IRI عند حدّ المظروف |
| `farm_id` | `saref4agri:Farm`/`sdm:AgriFarm` | match | يُعتمَد مفهوم Farm في المفتاح |
| `geometry` (GeoJSON dict) | GeoSPARQL geometry (WKT) | diverge | (أ) جسر: GeoJSON↔WKT عند الحدّ |
| `area_ha` (float, ha) | مساحة foodie/sdm (qudt unit) | diverge | (أ) جسر وحدة صريحة (ha→qudt) |
| `crop` (str) | `foodie:CropSpecies` عبر `cropSpecies` | match | مفهوم المحصول (مشترك مع العنقود 2) |
| `soil_ph/ec/om/n/p/k` | **رصد** `sosa:Observation` (لا سمة Parcel) | diverge | (ب/أ) SAHOOL يُلحِقها بالحقل (read-model)؛ للتبادل تُصدَّر كرصد (العنقود 4) |
| `soil_type` | AGROVOC soil type (اختياريّ) | diverge | (ب) إبقاء محلّيّ + تعيين AGROVOC مؤجَّل |
| `water_source` `ownership_type` `quality_grade` `name_ar` `elevation_m` | — | absent | (ب) امتداد SAHOOL (namespace `sahool:` — لا يُخلَط بمعيار) |

**خلاصة:** محاذاة مفهوم Parcel قويّة؛ الانحراف البنيويّ الجوهريّ = **SAHOOL يُطبّع خصائص التربة على الحقل، بينما OCSM ينمذجها رصداً**.

## العنقود 2 — Season/Crop
مصدر SAHOOL: `services/sahool-platform/api/season_models.py:19-67` · مقابل OCSM: **لا صنف Season أساسيّ** (FOODIE `foodie:CropSeason`/FarmCalendar).

| حقل SAHOOL | مقابل OCSM | الحكم | القرار |
|---|---|---|---|
| `season_id` `field_id` | — (كيان Season غائب في الأساس) | absent | (ج) تعيين FOODIE `foodie:CropSeason` مؤجَّل بمحفّز |
| `crops[]` `cultivar` | `foodie:CropSpecies` + cultivar | match | مفهوم المحصول/الصنف |
| `sowing_date` `plowing_date` `land_leveling_date` | عمليّات FarmCalendar مؤرَّخة (Sowing/Tillage) | diverge | (أ) جسر: حقل تاريخ→Operation مؤرَّخ |
| `stages[]` (StageItem name/date) | مراحل نموّ (BBCH/AGROVOC phenology) | diverge/absent | (ب) إبقاء محلّيّ + BBCH مؤجَّل |
| `target_yield_kg_ha` `actual_yield_kg_ha` | رصد غلّة `sosa:Observation` | diverge | (أ) يُصدَّر كرصد لا سمة موسم |
| `irrigation_type` `seed_rate_kg_ha` `plant_density` `row_spacing_cm` `maturity` `tillage_type` | — | absent | (ب) امتداد SAHOOL |

**خلاصة:** OCSM الأساسيّ بلا كيان موسم ⇒ العنقود يعيش بين `foodie:CropSeason` (مؤجَّل) وعمليّات FarmCalendar؛ معظمه امتداد محلّيّ اليوم.

## العنقود 3 — Irrigation
مصدر SAHOOL: `services/sahool-platform/api/irrigation_models.py:22-46` · مقابل OCSM: **لا صنف Irrigation أساسيّ** (خدمة OpenAgri-IrrigationManagement + SAREF).

| حقل SAHOOL | مقابل OCSM | الحكم | القرار |
|---|---|---|---|
| `device_id` | `saref:Device` | match | مفهوم الجهاز عبر SAREF |
| `valve_type` `flow_rate_lpm` `status(open/closed)` | — (تحكّم فعليّ خارج OCSM الأساسيّ) | absent | (ج) جسر لـOpenAgri-IrrigationManagement مؤجَّل بطلب شريك |
| `water_target_mm` `volume_l/mm` `duration_min` `start_time` `days_of_week` | ريّ كعمليّة FarmCalendar (Irrigation Operation) | diverge | (أ) جسر: جدول→Irrigation Operation عند الحدّ |
| `valve_id` `enabled` `name` | — | absent | (ب) امتداد SAHOOL (تحكّم تشغيليّ) |

**خلاصة:** التحكّم بالريّ **إقليم SAREF/SAHOOL لا OCSM الأساسيّ**؛ التبادل المعياريّ يمرّ عبر OpenAgri-IrrigationManagement (مؤجَّل).

## العنقود 4 — Weather/Soil observation (أقوى محاذاة)
مصدر SAHOOL: `shared/contracts/remote_sensing/schemas/CanonicalObservationV1.schema.json` · `shared/contracts/soil/soil_observation.v1.schema.json` · `shared/contracts/indicator_observation.schema.json` · مقابل OCSM: `sosa:Observation` (SOSA/SSN).

| حقل SAHOOL | مقابل OCSM (SOSA) | الحكم | القرار |
|---|---|---|---|
| `field_id` | `sosa:hasFeatureOfInterest` (Parcel) | match | — |
| `observed_at` / `acquired_at` / `acquisition_date` | `sosa:phenomenonTime` / `sosa:resultTime` | diverge | (أ) جسر: تمييز phenomenon vs result time |
| `indicator` / `index` / `property` | `sosa:observedProperty` (AGROVOC/EPPO) | diverge | (أ) جسر مفردات: vocab محلّيّ→AGROVOC مؤجَّل |
| `value` / `statistics` / `summary` | `sosa:hasResult` | match | — |
| `source_type` / `source_id` / `procedure_id` / `calibration_id` | `sosa:usedProcedure` / `sosa:madeBySensor` | match | مفهوم الإجراء/المستشعر |
| `lineage` / `provenance` | PROV-O (OCSM يعيد استخدامها) | match | نَسَب معياريّ |
| `observation_quality` / `quality_status` / `confidence` / `uncertainty` | جودة نتيجة SOSA / DQV | diverge | (ب) SAHOOL أغنى — إبقاء محلّيّ + DQV اختياريّ |
| `depth_from_cm` / `depth_to_cm` | أفق تربة (AGROVOC) | diverge | (أ) جسر عمق→أفق |
| `tenant_id` | — (تعدّد المستأجرين شأن منصّة) | absent | (ب) امتداد SAHOOL — **لا يُخلَط بمعيار** |
| `idempotency_key` `schema_version` `supersedes` `publication_status` `raster_asset_id` `qa_mask_version` | — (شؤون حدث/منصّة) | absent | (ب) امتداد SAHOOL |

**خلاصة:** الرصد **أقوى نقطة محاذاة** — بنية `sosa:Observation` تطابق نموذجنا؛ الانحراف الرئيس مفرداتيّ (vocab محلّيّ↔AGROVOC/EPPO) لا بنيويّ.

---

## سجلّ قرارات الانحراف (مُلخَّص)
- **جسر عند حدّ B1 (أ):** معرّفات str↔IRI · GeoJSON↔WKT · وحدات→qudt · حقول تاريخ→عمليّات FarmCalendar · phenomenon/result time · مفردات→AGROVOC · عمق→أفق.
- **إبقاء محلّيّ مبرَّر (ب):** خصائص تربة على الحقل (read-model) · جودة SAHOOL الأغنى · كلّ حقول `tenant_id`/الحدث/التحكّم التشغيليّ (امتداد `sahool:` صريح، لا يُخلَط بمعيار).
- **اعتماد مؤجَّل بمحفّز (ج):** `foodie:CropSeason` للموسم · OpenAgri-IrrigationManagement للريّ · BBCH لمراحل النموّ.

## محفّز التنفيذ المؤجَّل
هذه الخريطة **لا تُنفَّذ الآن**. التنفيذ (مُسلسِل/تعيين فعليّ) يُفعَّل عند **أوّل** من:
1. مظروف B1 (SCOUT-INGEST) يحتاج مفتاحاً معياريّاً لتشغيل بينيّ خارجيّ فعليّ، **أو**
2. أوّل متكامل/شريك يطلب تبادل OCSM (JSON-LD).
حتى ذلك: الخريطة توجّه **تسمية مفاتيح مظروف B1** فقط — العنقود 4 (`sosa:Observation`) هو المرشّح الأوّل للمحاذاة لأنّه الأقوى.

## الحُرّاس
`tests_v9/test_ocsm_crosswalk_reference_only.py` (unit): يؤكّد (١) وجود هذا الـADR بنسخة OCSM المثبَّتة + العناقيد الأربعة؛
(٢) **أنّ OCSM لم يتسرّب إلى عقود runtime** — لا `w3id.org/ocsm` ولا استيراد/مُسلسِل OCSM في `shared/contracts/` (برهان بنيويّ ضدّ «adoption جملة» متسلّل)؛ (٣) برهان سلبيّ.

## ما هذا الـADR ليس
ليس: تبنّي OCSM · إعادة تسمية حقول · إضافة تبعيّة/مُسلسِل JSON-LD · تغيير أيّ عقد · مسار runtime. **مرجع + قرار فقط.**
