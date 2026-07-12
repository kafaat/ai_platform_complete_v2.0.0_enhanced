# Water Auto → Decision → Actuator → Timeline Forensic Review

Date: 2026-07-12
Archive reviewed: `sahool_3b20e07_water_auto_actuator_timeline_verified.zip`

## Verdict

The four subsystems exist, but the end-to-end chain is not fully closed:

- Water ledger automation: present and tested.
- Decision execution feed and atomic claim: present; PostgreSQL integration tests require a real DB.
- Actuator dispatch consumer: present and unit-tested.
- Unified field timeline: present and tested.
- Automatic bridge from water deficit to governed decision candidate, execution request, actuator receipt, and timeline event: **not present**.

## Regression found and fixed

`services/actuator-service/main.py` used `from actuator_runtime import *`, which does not export single-underscore safety helpers. This broke the established compatibility surface and caused six actuator safety tests to fail. In a combined monorepo test process, the cached runtime could also leave `/command` unregistered.

The shell now:

1. Re-exports the full runtime surface, including safety helpers.
2. Preserves callable identity for FastAPI dependency overrides.
3. Re-runs idempotent router registration when loaded against a cached runtime.

Focused verification after the fix:

- 38 passed
- 3 skipped (real PostgreSQL integration tests)

## Evidence of the remaining chain gap

`run_water_ledger_once` writes/upserts `water_ledger` only. It does not:

- create a governed decision candidate,
- create a dispatch authorization,
- create an execution request,
- emit a field event for the unified timeline,
- attach the actuator delivery receipt or verified outcome to the field timeline.

Therefore the archive should not yet be certified as a complete autonomous water-to-actuation closed loop.

## Required next increment

Add a governed water-deficit bridge:

`water_ledger deficit > threshold`
→ create decision candidate with field/season/ledger lineage
→ human/explicit policy approval
→ execution plan and dispatch authorization
→ execution request
→ actuator claim and receipt
→ verified outcome
→ append canonical field event consumed by `/api/v1/fields/{field_id}/unified-timeline`

The bridge must remain default-off, tenant-isolated, idempotent by `(field_id, ledger_date, policy_version)`, and simulation-only until staging certification passes.

---

## ملحق التكامل (أُضيف عند الإنزال)

- **الانحدار (`import *` يُسقط أسماء الشرطة السفليّة): صحيح ومُتبنّى إصلاحه.** كنتُ اكتشفت
  العرض نفسه أثناء بناء المستهلك (اختبارا الجسر والسلامة فاشلان كامنَين — لا يشغّلهما CI)
  وعالجتُه ضيّقاً بتوجيه اختبار الجسر إلى `actuator_runtime.py`. إصلاح الحزمة أعمّ وأصحّ:
  إعادة تصدير كامل سطح التوافق في `main.py` (شاملاً المساعدات الخاصّة) بهويّة كائنات
  محفوظة لـ`dependency_overrides` + إعادة تسجيل idempotent للراوترات (تحقّقتُ: `_include_flat`
  يتخطّى path+methods القائمة فعلاً). **تعديل واحد على المُسلَّم:** الاستدعاء صار
  `_runtime.register_routers(_runtime.app)` — الحقن عبر `globals()` يفشل ruff F821
  (النمط المتكرّر في الحزم المُسلَّمة). التحقّق: سلامة+جسر 22/22 (كانت 6 فاشلة على HEAD).
- **فجوة السلسلة (جسر عجز الماء → قرار محكوم): تشخيص صحيح ومقصود حتّى الآن.** أتمتة
  الدفتر بُنيت عمداً كمنتِج بيانات لا كمُطلِق قرارات — القرار المحكوم يمرّ عبر مسار
  المرشّح→المراجعة→التفويض القائم. الجسر المقترح (deficit>عتبة ⇒ مرشّح بموافقة
  بشريّة/سياسة ⇒ السلسلة القائمة ⇒ حدث خطّ زمنيّ) سُجِّل زيادةً تاليةً باشتراطات
  التقرير نفسها: default-off، معزول المستأجر، idempotent على (field_id, ledger_date,
  policy_version)، محاكاة-فقط حتى شهادة staging.
- اختبارا PG المتخطّيان في بيئة المُراجِع يعملان هنا وفي CI على Postgres حقيقيّ.
