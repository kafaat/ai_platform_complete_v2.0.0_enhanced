# SAHOOL — تقرير شهادة البيئة الحيّة (Live Certification Report)

> **الغرض:** إغلاق الفجوات المُعلَنة صراحةً التي **لا يمكن للـCI التحقّق منها** (تحتاج
> Postgres+PostGIS+Redis حيّة، أو GPU/متصفّح حقيقيّ). كلّ مرحلة: هدف · أوامر · معيار نجاح ·
> صندوق نتيجة تملؤه · حكم PASS/FAIL. لا يُفعَّل `LEXICOGRAPHIC_MPC_BRIDGE_ENABLED=true`
> إنتاجيّاً إلا بعد اخضرار **كلّ** المراحل + بوّابة Go/No-Go.

## بيانات التشغيل

| الحقل | القيمة |
|---|---|
| commit المُشهَّد | `__________` (يجب أن يطابق تِلّ main الأخضر) |
| البيئة | staging / live: `__________` |
| المُنفِّذ | `__________` |
| التاريخ | `__________` |
| compose | `docker-compose.v9.yml` (أو `.v9.gpu.yml` للمرحلة 5) |

---

## المرحلة 0 — التهيئة والصحّة (شرط مسبق)

```bash
docker compose -f docker-compose.v9.yml up -d
docker compose -f docker-compose.v9.yml ps        # كلّها (healthy)
curl -fsS http://<host>/health && curl -fsS http://<host>/ready
```

**معيار النجاح:** Postgres+PostGIS · Redis · decision-service · soil · weather · raster ·
platform كلّها `healthy`/`alive`.

**النتيجة:** `_____ خدمة healthy` · **الحكم:** ☐ PASS ☐ FAIL

---

## المرحلة 1 — الهجرات وسلامة قاعدة البيانات (RLS/PostGIS)

```bash
bash scripts/production_validation_gate.sh        # تطابق MANIFEST ↔ run_migrations + 0 أخطاء
```

**معيار النجاح:** كلّ الهجرات تُطبَّق نظيفةً (0 أخطاء) · كلّ جدول جديد `ENABLE + FORCE RLS` +
سياسة `tenant_isolation` (تحقّق يدويّ عيّنة عبر `\d+ <table>`).

**النتيجة:** `_____` · **الحكم:** ☐ PASS ☐ FAIL

---

## المرحلة 2 — اختبارات التكامل (تحتاج PG+PostGIS+Redis)

```bash
pytest -m integration            # 57 اختبار — خاصّة سلسلة القرار:
#   test_decision_record_mandatory_persist · test_decision_lineage
#   test_decision_governance · test_decision_impact_integration · test_decision_policies_integration
```

**معيار النجاح:** كلّها خضراء على PG حقيقيّ (لا محاكاة). **يُثبِت:** السلسلة المحكومة تعمل فعليّاً.

**النتيجة:** `_____ / 57 passed` · **الحكم:** ☐ PASS ☐ FAIL

---

## المرحلة 3 — شهادة MPC (إغلاق فجوات P1.1c)

> **مسبق:** وصل `_source_soil_capacity`→soil-service و`_source_forecast_horizon`→weather-service
> (حاليّاً fail-closed stubs). حقل اختبار له صفوف `water_ledger` + ملفّ تربة + تنبّؤ طقس.

### 3.أ — توصية عمليّة من حقائق SoR كاملة
```bash
curl -X POST http://<host>/api/v1/fields/{FIELD}/irrigation/mpc/recommendation \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"horizon_days":7}'
```
**معيار النجاح:** `mode=operational` + `facts_provenance` ببصمات لقطات 64-hex حقيقيّة
(`ledger_snapshot_hash`/`weather_snapshot_hash`/`soil_snapshot_hash`) — **لا** `blocked`.

**النتيجة:** `_____` · **الحكم:** ☐ PASS ☐ FAIL

### 3.ب — fail-closed على نقص الحقائق (حقل بلا تربة/تنبّؤ)
**معيار النجاح:** `status=blocked` + `reason=insufficient_ground_truth` + `missing:[…]`.

**النتيجة:** `_____` · **الحكم:** ☐ PASS ☐ FAIL

### 3.ج — عزل المستأجِر (حقل لمستأجِر آخر)
**معيار النجاح:** `status=blocked` + `reason=field_not_owned`.

**النتيجة:** `_____` · **الحكم:** ☐ PASS ☐ FAIL

### 3.د — فصل المسارات (محاكاة ≠ عمليّ)
```bash
curl -X POST …/api/v1/irrigation/mpc/simulate  -d '{"field_id":"F","forecast":[{"et0_mm":10,"kc":1}],"taw_mm":100,"initial_depletion_mm":45,"submit":true}'
curl -X POST …/api/v1/irrigation/mpc/plan      -d '{"field_id":"F","forecast":[{"et0_mm":10,"kc":1}],"taw_mm":100,"initial_depletion_mm":45,"submit":true}'
```
**معيار النجاح:** `/simulate` ⇒ `mode=simulation` + `emit.status=not_applicable_simulation` ·
`/plan` بحقائق عميل + submit ⇒ `emit.status=rejected_simulation` (لا يُصدَر مرشّح من حقائق عميل).

**النتيجة:** `_____` · **الحكم:** ☐ PASS ☐ FAIL

---

## المرحلة 4 — نَسَب PostgreSQL من candidate إلى outcome (الفجوة الكبرى)

```bash
export LEXICOGRAPHIC_MPC_BRIDGE_ENABLED=true      # staging فقط
curl -X POST …/api/v1/fields/{FIELD}/irrigation/mpc/recommendation -d '{"horizon_days":7,"submit":true}'
#   خُذ content_digest من الاستجابة → DIGEST
```

تتبّع **نفس `content_digest`** عبر السلسلة (استعلامات على PG لـdecision-service):
```sql
-- 1) candidate مُثبَت وموثوق
SELECT decision_id, stage, content_digest FROM decisions WHERE content_digest = '<DIGEST>';
-- 2) في طابور المراجعة بنفس البصمة
--    (أو: curl …/api/v1/decisions/review-queue → يظهر بنفس digest)
-- 3) بعد approve: خطّة التنفيذ تحمل نفس البصمة
SELECT execution_plan_id, content_digest FROM execution_plans WHERE content_digest = '<DIGEST>';
-- 4) authorize → execution_request → MQTT dispatch
SELECT execution_request_id, content_digest FROM execution_requests WHERE content_digest = '<DIGEST>';
-- 5) receipt → verify → outcome → learning تحتفظ بالبصمة
SELECT * FROM outcomes WHERE content_digest = '<DIGEST>';
```
> ملاحظة: أسماء الجداول/الأعمدة أعلاه توضيحيّة — طابِقها بمخطّط decision-service الفعليّ.

**معيار النجاح:** نفس `content_digest` يظهر في **كلّ** حلقة من candidate حتى outcome (نَسَب
end-to-end حقيقيّ).

**idempotency:** أعِد نفس الطلب ⇒ نفس `idempotency_key` ⇒ **لا صفّ مكرَّر** (قيد PG الفريد
يمنع الكتابة الثانية).

**النتيجة:** `_____` · **الحكم:** ☐ PASS ☐ FAIL

---

## المرحلة 5 — الاختبارات البصريّة (GPU/متصفّح حقيقيّ)

```bash
cd frontend
PW_ALL_BROWSERS=1 npx playwright test maphub-webgl        # على runner بـGPU (لا SwiftShader headless)
#   انزع test.fixme عن اختبارَي الرسم (maphub-webgl.spec.ts:110,139)
```
**معيار النجاح:** رسم مضلّع/خطّ فعليّ بالنقر ⇒ `measure-area` بـ«م²» و`measure-length` بـ«كم»
بقيم حقيقيّة. (WebKit/iOS إن أمكن.) **يُثبِت:** تفاعل Canvas/WebGL الحقيقيّ.

**النتيجة:** `_____` · **الحكم:** ☐ PASS ☐ FAIL

---

## المرحلة 6 — دخان التشغيل والأمن

```bash
bash scripts/ci/runtime_real_smoke.sh             # عقود weather/edge حيّة
```
**معيار النجاح:** `runtime_real_smoke_ok` · الحاويات non-root · healthchecks · لا منافذ إدارة
مكشوفة (fastbee/zlmediakit loopback).

**النتيجة:** `_____` · **الحكم:** ☐ PASS ☐ FAIL

---

## بوّابة Go/No-Go — تفعيل الجسر إنتاجيّاً

☐ 3.أ operational + بصمات لقطات حقيقيّة
☐ 3.ب/ج/د fail-closed + ownership + فصل المسارات
☐ 4 نَسَب PostgreSQL end-to-end (نفس digest candidate→outcome)
☐ 4 idempotency PG (لا تكرار)
☐ 2 integration suite أخضر على PG
☐ 5 الاختباران البصريّان خضراوان على GPU
☐ 6 دخان التشغيل والأمن أخضر
☐ **الموافقة البشريّة** على المرشّحات تبقى فعّالة أوّل موسم (recommendation-only بنيويّاً)

**القرار:** ☐ GO (فعِّل `LEXICOGRAPHIC_MPC_BRIDGE_ENABLED=true`) ☐ NO-GO (أبقِه default-off)

---

## حدّ الصدق

حتى اخضرار كلّ ما سبق على بيئة حيّة، يبقى الجسر **default-off وغير جاهز للتفعيل الإنتاجيّ**.
هذا حدّ بيئيّ حقيقيّ (لا نقص في الكود): النَّسَب عبر PostgreSQL والوصل الحيّ لـsoil/weather
والاختبارات البصريّة على GPU لا تُشهَّد إلا هنا.
