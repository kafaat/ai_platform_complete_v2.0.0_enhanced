# دليل تحويل خدمة القرار إلى نظام السجلّ (Decision-Service SoR Cutover)

> إجراءٌ نشريّ متعمَّد على **PostgreSQL 16 حيّ** ينقل ملكيّة جداول حلقة القرار من المنصّة إلى
> `decision-service`، فيُفعّل مسار المراجعة السلطويّ (WX‑10.7). كلّ خطوة فاشلة‑مغلقة بالتصميم:
> لا يخضرّ ما لم يُقَس على قاعدة حقيقيّة.
>
> **حدّ الصدق:** كلّ الأدوات المذكورة أدناه **مُبرهَنة على PG في CI**؛ ما يبقى هو **تشغيلها حيّاً**
> (staging→prod) — لا كود. حتّى إتمامه، مسار المراجعة يفشل مغلقاً `503` بالتصميم.

## ⛔ حواجب تسبق البدء — GATE‑01 لم تُفتح

الـcutover الحقيقيّ محجوب حتّى يُرفع حاجبان فيزيائيّان موثَّقان (evidence pack المرحلة 0:
`phase0_evidence_status: NOT_FROZEN`):

- **COMPENSATION‑BYPASSES‑KILLSWITCH‑01** — مسار التعويض `_compensate` في
  `services/actuator-service/actuator_runtime.py` يُرسِل الأمر العكسيّ بلا فحص `is_actuation_halted`.
  اختباراته `xfail(strict=True)` في `tests_v9/test_compensation_killswitch.py`.
- **MANUAL‑COMMAND‑KILLSWITCH‑SCOPE‑BLIND‑01** — `/v1/command` اليدويّ
  (`services/actuator-service/routers/commands.py:47`) يفحص المفتاح بلا `field_id`، فمفتاح إيقاف
  الحقل لا يحجبه.

**وقبل أيّ اتّصال:** السرّ (DSN/كلمة المرور) يُمرَّر متغيّرَ بيئة في بيئة التنفيذ — **لا يُكتب في
محادثة ولا في مستودع**. ودور الاتّصال مقيَّد (ليس `superuser` ولا `BYPASSRLS`).

## قبل أن تبدأ — الثوابت

### جداول SoR الستّة (`services/decision-service/cutover.py::_REQUIRED_TABLES`)

| الجدول | الغرض |
|---|---|
| `decision_record` | رأس القرار |
| `dispatch_decisions` | قرار الإرسال |
| `outcome_record` | النتيجة الميدانيّة |
| `recommendation_outcomes` | نتائج التوصيات |
| `online_learning_updates` | تحديثات التعلّم |
| `decision_outbox_events` | صندوق الأحداث الصادر |

### الرايات السبع المطلوبة (`production_promotion.py::REQUIRED_TRUE_FLAGS`)

يشترط preflight الإنتاج أن تكون جميعها `true` — ولا تُرفَع راية إلّا **بعد** تحقّقها فعلاً:

- `DECISION_SERVICE_SOR_ENABLED`
- `DECISION_SERVICE_MIGRATIONS_VERIFIED`
- `DECISION_SERVICE_BACKFILL_VERIFIED`
- `DECISION_SERVICE_TENANT_ISOLATION_VERIFIED`
- `DECISION_SERVICE_OUTBOX_VERIFIED`
- `DECISION_SERVICE_STAGING_CUTOVER_APPROVED`
- `DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED`

---

## المسار staging → prod

افتح أضعف حلقة أوّلاً على **PG16 staging**؛ كلّ مرحلة تُنتج برهاناً مرصوداً قبل التالية.

### 1) تصديق الأدوار — قراءة فقط، قبل أيّ REVOKE

إثبات أنّ دورَي المنصّة والخدمة منفصلان فعلاً على القاعدة الحيّة.

```bash
# مصفوفة الأدوار الحيّة (اتّصال/current_user/مالك الجدول/grants/rolbypassrls)
DECISION_SOR_PLATFORM_URL=postgres://sahool_app@staging/... \
DECISION_SOR_SERVICE_URL=postgres://decision_service@staging/... \
DECISION_SOR_TABLE_SCHEMA=public \
python services/decision-service/decision_sor_role_certify.py
```

**✓ المتوقّع:** `role_separation_confirmed=true`. لو `false` (دور مشترك) ⇒ أنشئ `decision_service_app`
وانقل اتّصال الخدمة إليه، ثمّ أعِد التصديق قبل المتابعة.

### 2) تطبيق الترحيلات — خطوة نشر صريحة

ترقية المخطّط فعلٌ إصداريّ متعمَّد، لا أثر جانبيّ لإقلاع. هذا الغلاف هو الطريق الوحيد المدعوم.

```bash
export DATABASE_URL=postgres://decision_service@staging/...   # دور مقيَّد، لا superuser/BYPASSRLS
export DECISION_SERVICE_ALLOW_SCHEMA_CHANGE=true              # فاشل‑مغلق بدونها
bash scripts/deploy/decision_service_migrate.sh
```

يطبع فحص ما‑قبل ثمّ `--apply` ثمّ فحص ما‑بعد، ويشغّل مدقّق المراجعة (WX‑10.7) لكشف المرشّحين
الغامضين قبل قلب الملكيّة.

**✓ المتوقّع:** `decision_service_migrate_ok` · فحص ما‑بعد نظيف · لا صفوف مُحجَّرة (quarantine).

> **ملاحظة:** السكربت **لا** يُفعّل `SOR_ENABLED` ولا يقلب الملكيّة — يبقى ذلك إجراء مالك صريحاً بعد
> اخضرار كلّ بوّابة.

### 3) النقل الخلفيّ والتحقّق

مطابقة العدّ + تكافؤ المراجعة؛ لا يُخمَّن — يُحجَّر ويُحلّ.

```bash
DECISION_DATABASE_URL=... PLATFORM_DATABASE_URL=... \
  python services/decision-service/backfill.py --verify-counts

# تكافؤ طبقة المراجعة WX‑10.7 + كشف الحجر
python services/decision-service/backfill.py --verify-review
```

**✓ المتوقّع:** تطابق العدّ بين المنصّة والخدمة، و**حلّ كلّ صفّ مُحجَّر** قبل المتابعة.

### 4) مقارنة جانب القراءة + canary

تأكيد أنّ القراءة من الخدمة تطابق المنصّة قبل تحويل الكتابة.

```bash
DECISION_SERVICE_URL=... SAHOOL_PLATFORM_URL=... \
  python services/decision-service/read_side_compare.py --live

# كتابة عيّنة canary اختياريّة (idempotent)
python services/decision-service/staging_probe.py --live --sample-write \
  --tenant-id <t> --field-id <f> --idempotency-key <k>
```

**✓ المتوقّع:** تكافؤ القراءة الحيّ (parity) · عيّنة الكتابة تُقبَل وتُعاد قراءتها متطابقة.

### 5) قرار التحويل البشريّ + preflight الإنتاج

ارفع الرايات السبع (كلٌّ بعد تحقّقها فعلاً)، ثمّ افحص جاهزيّة الإنتاج.

```bash
# لا تُرفَع راية إلّا بعد إثباتها في المراحل 1–4
export DECISION_SERVICE_MIGRATIONS_VERIFIED=true
export DECISION_SERVICE_BACKFILL_VERIFIED=true
export DECISION_SERVICE_TENANT_ISOLATION_VERIFIED=true
export DECISION_SERVICE_OUTBOX_VERIFIED=true
export DECISION_SERVICE_STAGING_CUTOVER_APPROVED=true
export DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED=true
export DECISION_SERVICE_SOR_ENABLED=true

python services/decision-service/production_promotion.py --live \
  --decision-service-url http://sahool-decision-service:8160
```

**✓ المتوقّع:** كلّ فحوص الرايات `ok` + فحص `/readyz`: `db_reachable` و`migrations_current` = true.

### 6) قلب الملكيّة وسحب كتابة المنصّة (REVOKE)

اللحظة الحاسمة — فاشلة‑مغلقة براية موافقة مزدوجة (طوبولوجيا القاعدة‑الواحدة).

```bash
DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED=true \
DECISION_SOR_ALLOW_PLATFORM_REVOKE=true \
  bash scripts/deploy/decision_sor_platform_revoke.sh revoke

# طوبولوجيا قاعدتين منفصلتين ⇒ لا عمليّة (skip)
```

**✓ المتوقّع:** سحب صلاحيّة الكتابة من دور المنصّة على الجداول الستّة؛ الملكيّة صارت لـ`decision-service`.

> **حرّاس CI:** `scripts/ci/decision_sor_cutover_readiness_gate.py` +
> `scripts/ci/decision_sor_review_cutover_gate.py` يجب أن يبقيا خضراوين.

### 7) تفعيل SoR والتحقّق الحيّ

توجيه المنصّة إلى الخدمة السلطويّة؛ endpoint المراجعة يتوقّف عن الردّ `503`.

```bash
export DECISION_SERVICE_DATABASE_URL=postgres://decision_service@prod/...
export DECISION_SERVICE_URL=http://sahool-decision-service:8160
# على المنصّة: أوقف وضع المِرْآة
export SAHOOL_DECISION_WRITE_MODE=decision_sor
```

**✓ المتوقّع:** `/readyz` ⇒ `sor_enabled` · `db_reachable` · `migrations_current` = true. مسار مراجعة
WX‑10.7 صار **سلطويّاً** (بعد أن كان `503` بالتصميم).

> **P1 اختياريّ:** فعّل `DECISION_REQUIRE_AGRONOMIC_CONTEXT=true` لإلزام السياق الزراعيّ في القرارات
> القابلة للتنفيذ.

---

## خطّة التراجع (`services/decision-service/rollback.py --live`)

جهّزها **قبل** المرحلة 6 وأبقِها في المتناول. لا تنظيف هدّام: تُصان جداول الخدمة وتدقيق المراجعة
(append‑only) — لا حذف صفوف ولا عكس انتقالٍ مكتمل.

1. **تجميد الترقية** — `DECISION_SERVICE_SOR_ENABLED=false`
2. **استعادة كاتب المنصّة** — `SAHOOL_DECISION_WRITE_MODE=platform_sor`
3. **إعادة منح الكتابة (قاعدة واحدة فقط)** —
   `DECISION_SERVICE_ROLLBACK_APPROVED=true DECISION_SOR_ALLOW_PLATFORM_REVOKE=true
   scripts/deploy/decision_sor_platform_revoke.sh rollback` (عكسٌ مطابق لـREVOKE؛ skip في القاعدتين
   المنفصلتين)
4. **تعطيل التبعيّة الصارمة** — إلغاء `DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED`
5. **تأكيد كتابة المنصّة** — smoke لتكامل `decision_record`
6. **لا تنظيف هدّام** — إبقاء جداول الخدمة للمقارنة الجنائيّة
7. **صون تدقيق المراجعة WX‑10.7** — إبقاء `decision_reviews` وأعمدة `review_state`/`candidate_lineage_id`
   سليمة؛ المراجعات الجديدة تفشل مغلقة `503` في وضع المِرْآة
8. **مقارنة القراءة** — `python services/decision-service/read_side_compare.py --live`
9. **استئناف وضع الظلّ** — `SAHOOL_DECISION_WRITE_MODE=shadow` بعد نجاح smoke كتابة المنصّة فقط

---

## المصادر

- **الأدوات:** `scripts/deploy/decision_service_migrate.sh` ·
  `services/decision-service/{migration_runner,backfill,read_side_compare,staging_probe,production_promotion,rollback,cutover,decision_sor_role_certify}.py`
  · `scripts/deploy/decision_sor_platform_revoke.sh`
- **الحرّاس:** `scripts/ci/decision_sor_cutover_readiness_gate.py` ·
  `scripts/ci/decision_sor_review_cutover_gate.py`
- **الملكيّة:** `docs/architecture/db_ownership.yml` (`decision_record` status=interim-bridge)
- **السجلّ:** `sahool-brain/gaps/registry.md` — البنود `DEPLOYED-DECISION-SOR-PROMOTION` · P0‑A/P0‑B ·
  الحاجبان `COMPENSATION-BYPASSES-KILLSWITCH-01` / `MANUAL-COMMAND-KILLSWITCH-SCOPE-BLIND-01` (GATE‑01)
