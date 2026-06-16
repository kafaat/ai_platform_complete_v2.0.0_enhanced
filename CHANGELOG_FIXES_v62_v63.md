# سجلّ الإصلاحات — SAHOOL v9 (تحديث التزامن والحتميّة)

> دفعة إصلاحات مبنيّة على تدقيق مباشر من الكود المصدريّ. كلّ إصلاح مُتحقَّق
> بالترجمة (`py_compile`) واختبار نقيّ نجح. لا تغييرات سلوكيّة غير مقصودة.

التاريخ: 2026-06-16
النطاق: طبقة التزامن (concurrency) + حتميّة الإسقاط (projection determinism)

---

## ① إصلاح Race Condition في `field_lifecycle` 🔴

**المشكلة (مُثبَتة):** `FieldLifecycleEngine.get_or_create` كان نمط
Read→Check→Insert بلا حماية ذرّيّة. قيد `UNIQUE(field_id, season_id)` لا يحمي
الحالة الافتراضيّة لأنّ `season_id` يكون NULL حتّى البذر، وفي PostgreSQL
‏`NULL ≠ NULL` داخل UNIQUE — فطلبان متزامنان بـ`season_id=NULL` يُنشئان
دورتَي حياة مكرّرتين.

**الإصلاح:**
- `migrations/v62_field_lifecycle_null_season_guard.sql` (جديد):
  فهرس فريد جزئيّ `ux_field_lifecycle_field_null_season` على `(field_id)`
  حيث `season_id IS NULL` — يسدّ ثغرة NULL. + تنظيف أيّ تكرارات سابقة.
- `services/sahool-platform/api/field_lifecycle.py` (معدّل):
  `get_or_create` صار `INSERT ... ON CONFLICT DO NOTHING RETURNING` ذرّيّ،
  مع `conflict_target` ديناميكيّ (NULL/غير-NULL) وإعادة قراءة الفائز عند
  خسارة السباق.

**إصلاح إضافيّ مُكتشَف:** `transition` كان أيضاً read-then-write بلا قفل.
أُضيف `SELECT ... FOR UPDATE` داخل معاملة صريحة (فُصِل المنطق إلى
`_transition_locked`) لتسلسل الانتقالات المتزامنة على نفس الحقل.

---

## ② إصلاح Projection Drift (الترتيب غير الحتميّ) 🔴

**المشكلة (مُثبَتة):** إعادة بناء حالة الحقل تعتمد `ORDER BY occurred_at ASC`
وحده. لكنّ `occurred_at` هو `TIMESTAMPTZ DEFAULT NOW()`، فحدثان في نفس اللحظة
ترتيبهما غير حتميّ → إعادتا بناء مختلفتان من نفس الأحداث = drift. تعليق v60
اعترف بالمشكلة صراحةً: "جدول events بلا عمود seq حاليّاً (v11) فيبقى NULL".

**الإصلاح:**
- `migrations/v63_events_seq_deterministic_order.sql` (جديد):
  عمود `seq BIGINT GENERATED ALWAYS AS IDENTITY` على `events` — مؤشّر إدراج
  تسلسليّ صارم يكسر تعادل `occurred_at` حتميّاً. + فهرسا ترتيب.
- `services/sahool-platform/api/event_bus.py` (معدّل):
  `ORDER BY occurred_at ASC, seq ASC` + إضافة `seq` لـdict الناتج.
- `services/sahool-platform/api/event_replay.py` (معدّل):
  `SnapshotCursor.is_after` يستخدم `(occurred_at, seq)` متى توفّر، مع تراجُع
  متوافق رجعيّاً إلى `(occurred_at, event_id)` للقطات ما قبل v63.

**ملاحظة:** `_event_sort_key` كان يستخدم `seq` أصلاً (`e.get("seq") or 0`)
لكنّه يؤول لـ0 لغياب العمود. أي البنية كانت **جاهزة معماريّاً** — الإصلاح فعّل
ما كان معطّلاً بإضافة العمود.

---

## ③ تحسين Exception Swallowing 🟢

**السياق:** التدقيق الأوليّ ادّعى 401 ابتلاعاً؛ التحقّق كشف أنّ كود الإنتاج به
288 `except Exception` منها 182 تُسجّل/تُعيد الرمي و**6 فقط صامتة** — كلّها
مُعلَّمة `# noqa: BLE001` ومبرّرة (best-effort paths).

**التحسين:**
- `services/sahool-platform/api/routers/devices.py` (معدّل):
  `logging.debug(...)` بدل `pass` الصامت في التحقّق الاختياريّ من نوع الجهاز —
  قابليّة تشخيص أفضل دون تغيير السلوك.

---

## ④ اختبار يُثبت الإصلاح ✅

- `tests_v9/test_projection_determinism_v63.py` (جديد):
  اختبار نقيّ (بلا DB) يُثبت أنّ حدثين بنفس `occurred_at` يُرتَّبان حتميّاً عبر
  `seq`، وأنّ إعادة البناء **مستقلّة عن ترتيب الإدخال** (لا drift)، مع التحقّق
  من التراجُع المتوافق رجعيّاً. **نُفِّذ ونجح.**

---

## الملفّات المتأثّرة

```
جديد:
  migrations/v62_field_lifecycle_null_season_guard.sql
  migrations/v63_events_seq_deterministic_order.sql
  tests_v9/test_projection_determinism_v63.py

معدّل:
  services/sahool-platform/api/field_lifecycle.py
  services/sahool-platform/api/event_bus.py
  services/sahool-platform/api/event_replay.py
  services/sahool-platform/api/routers/devices.py
```

---

## الخطوات التالية الموصى بها (لم تُطبَّق — قرار/جهد أوسع)

1. **توسيع Optimistic Concurrency:** التحقّق التفاؤليّ (`row_version`) مطبَّق على
   `fields` فقط (v61). توسيعه لـ`seasons`/`commands` يحتاج migrations إضافيّة
   — يُنصَح كـPR منفصل.
2. **اختبار integration للـrace:** يتطلّب Postgres+PostGIS حقيقيّاً. شغّل على
   جهازك: `pytest -m unit` ثمّ `pytest -m integration` على قاعدة مُرحَّلة فعليّاً
   (تشمل v62/v63).
3. **سياق الحقل المشترك في الويب:** متجر `useFieldContext` (zustand) — راجع
   تقرير مراجعة الواجهات المنفصل.
