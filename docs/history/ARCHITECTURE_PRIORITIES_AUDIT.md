# تقييم الأولويّات المعماريّة الستّ: الموجود مقابل الفجوات

فحصتُ كلّ أولويّة في الكود الفعلي. الخلاصة: **الأولويّات الستّ كلّها لها بنية
موجودة وناضجة** — لا تحتاج بناءً من الصفر، بل سدّ فجوات ملموسة. هذا التقييم
يوثّق الحالة بصدق ويحدّد ما بُني وما تبقّى.

---

## أولويّة ١: Geospatial runtime core (النواة الجيومكانيّة)

**موجود وناضج:**
- backend: عمود `geom GEOMETRY(POLYGON, 4326)` + فهرس GIST + `GEOGRAPHY(POINT)` للأسواق
- mobile: `geometry.ts` (9 دوال: polygonAreaHa, distanceMeters, pivotCircle,
  pivotSectors, pivotTowers, centroid, destinationPoint...) — حساب محلّي offline

**الفجوة التي سُدَّت هذه الجلسة:** ✅ لم يكن هناك حساب آلي لـ`area_ha` من
`geom` (كان يُملأ يدويّاً). أضفتُ `v13_geospatial_core.sql`:
- trigger `compute_field_geometry`: يحسب `area_ha` آليّاً عبر
  `ST_Area(geom::geography)/10000` (GEOGRAPHY = مساحة كرويّة دقيقة لليمن، لا
  مسطّحة مشوّهة) + يستخرج مركز الحقل (lat/lon)
- دالّة `is_valid_field_geom`: تحقّق صحّة الهندسة (polygon صالح، غير متقاطع ذاتيّاً)
- يجسّد "المساحة تُنتَج آليّاً عند تحديد الحقل" (طلب سابق للمستخدم)

**الحكم:** ناضج + سُدَّت الفجوة الأبرز. (التنفيذ الفعلي يحتاج PostGIS — offline.)

---

## أولويّة ٢: Canonical agricultural ontology (الأنطولوجيا الزراعيّة الموحّدة)

**موجود وناضج:**
- `core/canonical_schemas.py`: المخطّطات الموحّدة (UserSchema, UserRole,
  أنواع الكيانات)
- `core/schema_factory.py`: توليد المخطّطات
- mobile `src/data/yemenCrops.ts`: 8 محاصيل يمنيّة + أصناف + مراحل + أنواع
  تربة + أسمدة + أنظمة ريّ + محافظات
- backend: `GDD_CROP_PARAMS` (5 محاصيل)، `KC_BY_CROP_STAGE` (9 محاصيل FAO)،
  `CROP_TOLERANCES` (ملوحة/pH FAO-tagged)

**ملاحظة اتّساق:** الأنطولوجيا موزّعة بين mobile (yemenCrops) وbackend
(GDD/KC/tolerances). متّسقة دلاليّاً لكن ليست مصدراً واحداً (single source).
توحيدها في ملفّ canonical مشترك = تحسين مستقبلي (ليس فجوة حرجة — القيم متطابقة).

**الحكم:** ناضج. التوحيد الكامل تحسين اختياري.

---

## أولويّة ٣: Temporal execution engine (محرّك التنفيذ الزمني)

**موجود وناضج:**
- `api/gdd_tracker.py`: GDD يومي + t_base/t_upper + تنبّؤ المرحلة (5 محاصيل)
- `api/field_timeline.py`: الخطّ الزمني للحقل
- `api/crop_stages` + `wofost_seasons` (جداول): مراحل النموّ + WOFOST
- `api/astronomical_timing.py`: مرساة موسميّة + تقاطع مع GDD
- `api/water_balance.py`: FAO-56 (زمني عبر المراحل)

**الحكم:** ناضج. المحرّك الزمني مبنيّ على GDD/المراحل/FAO — فيزيائي وحتمي.

---

## أولويّة ٤: Guardrails enforcement hardening (تقوية إنفاذ الحواجز)

**موجود وناضج:**
- `core/guardrails.py` (123 سطر): الحواجز الأساسيّة
- `core/execution_control_plane.py` (354 سطر، 19 دالّة/صنف): مستوى التحكّم
  بالتنفيذ + bootstrap نقاط الدخول المعروفة
- `core/provenance.py` (135 سطر): تتبّع المصدر، "محدود بأضعف مدخل" (golden rule)
- `core/authorization.py`: التفويض
- نمط BLOCKED عبر المحرّكات (nutrient_4r, confidence_gate, data_readiness)

**تقوية هذه الجلسة (سابقاً):** ✅ إصلاح أمني — سرّ JWT الضعيف يسبّب `sys.exit(1)`
في الإنتاج (كان تحذيراً فقط = ثغرة).

**الحكم:** ناضج + قوّي. الحواجز منفذة على مستوى الكود والقرار.

---

## أولويّة ٥: Deterministic orchestration (التنسيق الحتمي)

**موجود وناضج:**
- `core/internal_orchestrator.py` (196 سطر): التنسيق الداخلي
- `api/command_store.py` (271 سطر، 18 دالّة): مخزن الأوامر (CQRS-style)
- `api/event_bus.py` (308 سطر): ناقل الأحداث
- `api/event_replay.py` (302 سطر): إعادة تشغيل الأحداث (حتميّة)
- `core/skills_registry.py`: سجلّ المهارات

**ملاحظة:** الحتميّة مدعومة عبر event sourcing (command_store + event_bus +
replay) — إعادة التشغيل تنتج نفس الحالة. هذا نمط حتمي سليم.

**الحكم:** ناضج. البنية الحتميّة (event sourcing) موجودة.

---

## أولويّة ٦: Offline spatial sync architecture (مزامنة مكانيّة offline)

**موجود وناضج:**
- backend: `OfflineQueue` (max_per_tenant=1000) + `/api/v1/sync` + `/api/v1/queue/status`
- mobile: قاعدة SQLite محلّيّة (10 مستودعات) + `syncEngine` + `offline_queue`
  + `tileCache` (تخزين البلاطات المكانيّة offline عبر prefetchArea)
- الموبايل offline-first: كلّ العمليّات محلّيّة ثمّ تُزامَن

**الحكم:** ناضج. المزامنة offline-first مبنيّة على الموبايل والـbackend معاً،
والبُعد المكاني مغطّى بـtileCache (بلاطات) + geometry محلّي.

---

## الخلاصة

| الأولويّة | الحالة | الفجوة |
|----------|--------|--------|
| ١ جيومكانيّة | ناضج | ✅ سُدَّت: trigger حساب area_ha |
| ٢ أنطولوجيا | ناضج | توحيد المصدر (تحسين اختياري) |
| ٣ زمني | ناضج | — |
| ٤ حواجز | ناضج+ | ✅ سُدَّت سابقاً: JWT hard-fail |
| ٥ تنسيق حتمي | ناضج | — |
| ٦ مزامنة offline | ناضج | — |

**ما بُني هذه الجلسة:** `v13_geospatial_core.sql` (حساب آلي للمساحة والمركز +
تحقّق الهندسة) — تقوية ملموسة لأولويّة ١.

**ما لا يُبنى (وهذا صواب):** لا إعادة بناء للبنى الناضجة. الأولويّات الستّ ليست
"مفقودة" بل "موجودة وتُقوّى عند اكتشاف فجوة ملموسة". إعادة بنائها من الصفر =
إهدار وتكرار. المنهج: فحص → سدّ فجوة حقيقيّة → تحقّق.

⚠ القيود offline: تنفيذ trigger المساحة يحتاج PostGIS حيّاً؛ الصيغة مُتحقَّقة
منطقيّاً (مربّع 100م = 1 هكتار ✓) لكن لم تُنفَّذ على قاعدة حيّة.

---

## تحديث: مرحلة Convergence (الإثبات لا البناء)

بعد التقييم المصحّح (الأنظمة موجودة، تحتاج إثباتاً لا توسّعاً)، أُضيف:

### ١. طبقة التماسك الزمني (`api/temporal_coherence.py`)
مرجع زمني موحّد يربط تمثيلات الزمن الثلاثة (ISO ↔ day_of_year ↔ يوم نسبي)،
ويكشف الانحراف الدلالي (Semantic Drift) بين المحرّكات. Endpoint
POST /api/v1/temporal/coherence. **أوّل لبنة convergence قابلة للإثبات offline.**

### ٢. Platform Qualification Suite (`tests_v9/test_qualification_suite.py`)
بوّابة certification موحّدة:
- **invariants ثابتة** (تعمل offline): التماسك الزمني، اكتمال provenance،
  اشتقاق المساحة → 6/6 CERTIFIED
- **invariants تشغيليّة** (تحتاج قاعدة حيّة، تتخطّى offline بوضوح):
  no cross-tenant leak (RLS)، idempotency (قيد commands الفريد)،
  اشتقاق area_ha الحيّ من geom
- الفلسفة: invariant واحد ينكسر = فشل certification

### القيد الصادق
بنود الإثبات التي تحتاج تشغيلاً حيّاً (Chaos: broker outage, replay storms,
race conditions تحت quotas) **لا تُنفَّذ offline**. الـSuite يكتب الإطار
ويتخطّى بوضوح؛ التنفيذ الكامل على قاعدة حيّة عبر:
  export DATABASE_URL=... && python3 tests_v9/test_qualification_suite.py

ما أُنجِز offline: التماسك الزمني (مُثبَت)، إطار الـinvariants الحيّة (جاهز
للتشغيل)، اشتقاق المساحة (مُثبَت ثابتاً). ما يبقى للبيئة الحيّة: الإثبات
التشغيلي الكامل تحت الفوضى.
