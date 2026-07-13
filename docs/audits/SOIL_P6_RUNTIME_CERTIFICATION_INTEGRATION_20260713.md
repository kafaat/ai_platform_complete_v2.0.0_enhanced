# SOIL P6 — Runtime & Production Certification: Integration Note (2026-07-13)

مرحلة **P6** تُكمِل سلسلة التربة القانونيّة: التصديق التشغيليّ والإنتاجيّ (RuntimeCertificationRun)
فوق حزمة P5. دُمِجت على الشكل المُنزَّل بتصميم الحزمة القانونيّ، وشُهِّدت على PostgreSQL 16 + PostGIS
حقيقيّ. هذا الملحق يوثّق الدلتا الحقيقيّة والانحرافات والعيوب المُصلَحة — أمانةً للمنهجيّة
(integrate-on-landed-shape · fix delivered bugs · document deviations).

## المُضاف (الدلتا الحقيقيّة)

- **العقد:** `shared/contracts/soil/p6.py` — `RuntimeCertificationRun` + أدلّة مُعنونة بالمحتوى
  (content-addressed evidence). أُضيفت صادراته الصريحة إلى `shared/contracts/soil/__init__.py`
  (استمراراً لنمط الصادرات الصريحة الذي تبنّيناه بدل `import *` في الحِزَم السابقة).
- **البانِي:** `services/soil-service/p6_certification.py` (منطق نقيّ، مُختبَر وحدةً — 3/3).
- **الراوتر:** `services/soil-service/routers/p6_certification.py` (يُركَّب تلقائيّاً عبر
  `router_registry.py`/`pkgutil.iter_modules` — لا توصيل صريح لازم).
- **الهجرة:** `migrations/v166_soil_p6_runtime_certification.sql` — جدولان
  (`soil_runtime_certification_runs`, `soil_runtime_certification_evidence`) بـ`ENABLE`+`FORCE ROW LEVEL SECURITY`
  وسياسات `tenant_isolation` (qual + with_check على `app.current_tenant`). مُطبَّقة على `sahool_ci`:
  0 أخطاء، 2/2 FORCE RLS مؤكَّدة.
- **CLI:** `scripts/soil/run_production_certification.py` (يخرج بـ2 عند فشل التصديق — سلوك fail-closed مؤكَّد).
- **الحارس:** `scripts/ci/soil_p6_runtime_certification_guard.py` (ساكن) + خطوة CI في `ci.yml`.
- **التسجيلات:** `migrations/MANIFEST.txt` (v166) + `scripts_v9/run_migrations.sql` (خطوة 172) +
  `docs/architecture/db_ownership.yml` (الجدولان الجديدان: owner=soil-service).

## عيوب تسليم حقيقيّة أُصلحت (براهين PG لديهم كانت SKIPPED)

1. **NOT NULL violation في اختبار التكامل المُسلَّم** —
   `tests_v9/test_soil_p6_runtime_integration.py::test_concurrent_supersession_accepts_one_replacement`
   كان `INSERT` في `soil_observations` يُغفِل العمودين `depth_from_cm`/`depth_to_cm` (كلاهما NOT NULL).
   الاختبار كان سيفشل حتماً على PG حقيقيّ. الإصلاح: أُضيف العمودان + قيمتاهما `0,30`.
   بعد الإصلاح: الاختبار يمرّ **3/3** على PG حقيقيّ (RLS/with_check · استرجاع إيجار الإسقاط المنتهي +
   dead-letter · قبول استبدال تعاقُبيّ متزامن واحد فقط).

## انحرافات موثَّقة (لا نصف حلّ)

- **الجرود المُولَّدة (SERVICE_REGISTRY / service_inventory / route_inventory / route_mount):**
  عند دمج سلسلة P0–P5 لم يُعَد توليد الجرود المُولَّدة، فظهر **انحراف حقيقيّ أحمر على `main`@`9f24a2a`**
  في وظيفة *Service Inventory Drift* (`SERVICE_REGISTRY.md`). أُعيد التوليد الآن ضمن هذا الالتزام
  (`generate_service_inventory.py --write-registry` → 29 خدمة/997 مساراً؛ `route_mount_contract_guard.py --write`
  → 25 مدخلاً)، وأُعيد بناء حزمة الإصدار (4222 checksum). **درس مُرسَّخ:** قائمة قبل-الالتزام لأيّ عمل
  يضيف راوترات/وحدات تشمل الآن إعادة توليد الجرود المُولَّدة صراحةً، لا الحُرّاس الساكنة فقط.
- **تغطية الوحدة:** بانِي P6 النقيّ مُختبَر وحدةً؛ الراوتر مُعفى في `.coveragerc` (نمط decision-service —
  سطح DB/HTTP). التغطية الكلّيّة **45.17%** (أرضيّة 40%).

## التحقّق

- `pytest -m unit` — **2914 نجاح / 5 تخطٍّ**، تغطية **45.17%** (أرضيّة 40%).
- 66+ اختبار وحدة تربة · P6 وحدةً **3/3** · P6 تكامل PG حقيقيّ **3/3** · CLI يخرج 2 عند الفشل.
- 15/15 حارس تربة · حارس تزامن المُشغّلَين · حُرّاس المنصّة (decomposition + route budget).
- `ruff format --check` + `ruff check` نظيفان على `services/ bots/ agents/ tests_v9/`.
- الجرود المُولَّدة نظيفة (`--check` أخضر) · حزمة الإصدار **4222** checksum · `ci.yml` YAML صالح.
