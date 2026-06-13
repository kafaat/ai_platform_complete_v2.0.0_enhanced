# حدّ كتابة الحقل (Field Aggregate Root — P2)

تنفيذ **المرحلة ٣** من `POST_DEPLOYMENT_ROADMAP.md` (دَين P2 المعماريّ) — **الشريحة
الأولى التدريجيّة غير الكاسرة**.

## الهدف
مصدر حقيقة واحد لكتابة الحقل وما يتفرّع عنه، فتمرّ التغييرات عبر مسار موحّد:
```
Command → FieldAggregate (تحقّق الـinvariants) → (تغيير حالة + أحداث) ذرّيّاً
```
بدل تكرار منطق التحقّق وكتابة الجداول مباشرةً في كلّ endpoint.

## ما بُني في هذه الشريحة (`api/field_aggregate.py`)
| المكوّن | الدور |
|--------|-------|
| `FieldState` | لقطة حالة الحقل المحمّلة (موجود؟ موسم نشط؟ lifecycle) — مدخل نقيّ |
| `FieldAggregate` | النواة النقيّة (بلا I/O): `create`/`update`/`start_season`/`record_activity` تتحقّق من الـinvariants وتصف الأثر (أحداث) |
| `FieldInvariantError` | انتهاك invariant + رمز HTTP (404/409/422) لترجمته في الـendpoint |
| `build_field_handlers` / `register_field_handlers` | معالِجات تُسجَّل على `CommandDispatcher` القائم (`command_store.py`)، مُحقَّنة بمنافذ (تحميل حالة/حفظ/إصدار) |

## الـinvariants في مكان واحد (لا تُكرَّر)
- إنشاء حقل **موجود** → `409`.
- تحديث/بدء موسم/تسجيل نشاط على حقل **غير موجود** → `404`.
- بدء موسم وهناك **موسم نشط** → `409` (يذكر معرّف النشط).

## لماذا «شريحة أولى»؟
- **النواة نقيّة** → قابلة للاختبار offline بالكامل (لا قاعدة).
- **المعالِجات تُحقَن بمنافذ** → تُختبَر عبر `CommandDispatcher` الحقيقيّ بمتجر ومنافذ
  وهميّة (نجاح/فشل invariant/idempotency) — **نفس العقد** الذي ستستعمله الواجهة الحيّة.
- **لم يُغيَّر أيّ endpoint حيّ بعد** — لا كسر. توجيه أوّل endpoint فعليّاً عبر هذا
  المسار = الشريحة التالية (الخطوة ٣ في الروادماب)، وتحتاج اختبار تكامل على قاعدة
  حيّة (الذرّيّة state+outbox تُضمَن داخل `apply_change` بمعاملة واحدة).

## الاختبارات (١٣ offline)
النواة (invariants + الأحداث الصحيحة من `EventType`) + مسار الـdispatcher الكامل
(`SUCCEEDED`/`FAILED` عند الانتهاك بلا إصدار/`was_duplicate` على نفس `command_id`) +
توحيد دلالة حدث النشاط.

## توحيد دلالة حدث النشاط (شريحة ٢)
خريطة (نوع النشاط، أُنجِز؟) → حدث عمليّة محدَّد (`operation.*`) أصبحت **مصدراً واحداً**
في `activity_event_for(activity_type, status)`:
- `FieldAggregate.record_activity` يستعمله → يُصدِر حدثاً **محدَّداً** (مثلاً
  `harvest+done → HARVEST_COMPLETED`) لا `ACTIVITY_RECORDED` العامّ.
- `main._activity_event_type` **يفوّض** إليه (يُرجِع اسم العضو — توافق خلفيّ تامّ).
فيُصدِر مساراها (الـendpoint الحاليّ + مسار الأمر مستقبلاً) **الحدث نفسه** — لا تباعد.

**المتبقّي (شريحة تالية، deployment-time):** منافذ حيّة (`load_field_state`/كاتب +
`CommandDispatcher` على `conn`) وتوجيه أوّل endpoint فعليّاً عبر الأمر — يحتاج اختبار
تكامل على قاعدة حيّة (sandbox بلا Postgres).
