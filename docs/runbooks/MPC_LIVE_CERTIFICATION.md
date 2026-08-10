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

## المرحلة −1 — حاجبا مفتاح الإيقاف (بوّابة تسبق كلّ شيء)

> **لا تُستشهَد هذه الشهادة لتبرير أيّ `cutover` أو تفعيل مسارٍ فيزيائيّ ما دام البندان
> التاليان `OPEN`.** كلاهما موسوم **«حاجب لأيّ real/cutover»** في
> [`sahool-brain/gaps/registry.md`](../../sahool-brain/gaps/registry.md).

| المعرّف | الموضع | العلّة |
|---|---|---|
| `COMPENSATION-BYPASSES-KILLSWITCH-01` | `actuator_runtime.py` (`_compensate`) | حلقة التعويض تُرسِل الأمر العكسيّ بلا `is_actuation_halted` |
| `MANUAL-COMMAND-KILLSWITCH-SCOPE-BLIND-01` | `routers/commands.py` | `/v1/command` يفحص المفتاح بلا `field_id` ⇒ مفتاح الحقل لا يحجب اليدويّ |

```bash
# فحص ساكن (لا يحتاج stack): الموضع المكشوف مُسجَّل دَيناً معلَناً لا مُغطّى صامتاً
python scripts/ci/actuation_killswitch_coverage_guard.py --list

# الاختباران الواصفان: يبقيان xfail(strict=True) حتّى تُفتَح GATE-01 وتهبط الرقعتان
pytest tests_v9/test_compensation_killswitch.py tests_v9/test_manual_command_killswitch_scope.py -q
```

**معيار العبور:** GATE-01 مفتوحة (`phase0_evidence_status` مُثبَّتة بـ`frozen_commit_sha`) **و**
الرقعتان هبطتا **و**`actuation_killswitch_coverage_guard` أخضر بلا دَين مُسجَّل.
ما دامت GATE-01 مغلقة، المراحل 0–6 أدناه تُنفَّذ **للقياس والتوثيق فقط**، ولا تُقرأ إذناً
بتفعيل أيّ مسار يُطلِق أثراً فيزيائيّاً.

**النتيجة:** `_____` · **الحكم:** ☐ عبور ☐ محجوب

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

> **v167:** `content_digest` صار **عموداً أوّليّاً مفهرَساً** (لا حقلاً في `decision_value` JSONB) على
> جداول السلسلة الأربعة، يُملأ من الرأس (`decision_record`) ويُنتشَر server-side للحلقات الأدنى بالبحث
> عبر `decision_id`. لذا التتبّع أدناه استعلام عمود مباشر على الأسماء الفعليّة (لا توضيحيّة):

تتبّع **نفس `content_digest`** عبر السلسلة (استعلامات على PG لـdecision-service، بعد `SET app.current_tenant`):
```sql
-- 1) الرأس: candidate مُثبَت — content_digest مُستخرَج من decision_value إلى العمود الأوّليّ
SELECT decision_id, stage, review_state, candidate_lineage_id, content_digest
  FROM decision_record WHERE content_digest = '<DIGEST>';
-- 2) طابور المراجعة يظهر بنفس البصمة (decision_record.review_state='pending_approval')
--    (أو: curl …/api/v1/decisions/review-queue → نفس decision_id/candidate_lineage_id)
-- 3) بعد approve → dispatch: الإرسال يحمل نفس البصمة (مُنتشَرة عبر decision_id)
SELECT decision_id, recommendation_id, state, content_digest
  FROM dispatch_decisions WHERE content_digest = '<DIGEST>';
-- 4) النتيجة تحتفظ بالبصمة (مُنتشَرة عبر decision_id)
SELECT outcome_id, decision_id, success, content_digest
  FROM outcome_record WHERE content_digest = '<DIGEST>';
-- 5) نتيجة التوصية تحتفظ بالبصمة (مُنتشَرة عبر decision_id)
SELECT recommendation_id, decision_id, outcome, content_digest
  FROM recommendation_outcomes WHERE content_digest = '<DIGEST>';
```
> ملاحظة: خطوات التنفيذ الوسيطة (execution_plan/authorize/execution_request) تربط عبر `decision_id`
> إلى نفس رأس `decision_record.content_digest`؛ الفهرس `idx_*_content_digest (tenant_id, content_digest)`
> يجعل كلّ استعلام أعلاه مُفهرَساً ومُقيَّداً بالمستأجِر.

**معيار النجاح:** نفس `content_digest` يظهر في **كلّ** حلقة تحمل العمود (decision_record → dispatch →
outcome → recommendation_outcome) — نَسَب end-to-end حقيقيّ قابل للاستعلام بالبصمة الكاملة (لا 16-hex فقط).

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
