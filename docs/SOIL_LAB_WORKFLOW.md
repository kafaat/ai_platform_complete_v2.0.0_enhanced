# Workflow مخبري للتربة (Soil Lab Workflow)

ينفّذ بند «Workflow مخبري للتربة» من `POST_DEPLOYMENT_ROADMAP.md` — دورة حياة
موثَّقة لفحص التربة بدل أعمدة `soil_*` الثابتة.

## دورة الحياة
```
requested → sampled → in_lab → result_received → approved → published
                ↘ cancelled        ↘ cancelled        ↘ rejected → in_lab / cancelled
```
- **المنشور والملغى نهائيّان** (لا إحياء — يحفظ المرجعيّة والتاريخ).
- **invariant الصدق:** لا انتقال إلى `result_received`/`approved`/`published` **بلا
  نتيجة مختبر فعليّة** (لا تأليف قياسات تربة) → `422`.
- نفس الحالة = لا-عمل (idempotent). حالة مجهولة → `422`.

## النواة: `core/engines/soil_lab_workflow.py` (نقيّة، مُختبَرة offline)
`validate_soil_transition(current, target, *, has_result)` — مصدر واحد لقواعد
الانتقال + invariant النتيجة. (١٠ اختبارات offline.)

## الجدول: `migrations/v50_soil_lab_tests.sql`
`soil_lab_tests` (test_id PK، tenant_id UUID، field_id، status، lab_name،
sampled_on، result JSONB، notes_ar، approved_by، published_at) + RLS (ENABLE+FORCE+
tenant_isolation) + فهارس + trigger `updated_at`. idempotent.

## النقاط
| الطريقة | المسار | الدور |
|--------|--------|-------|
| `POST` | `/api/v1/fields/{id}/soil-lab-tests` | إنشاء فحص (حالة `requested`) → `SOIL_SAMPLE_RECORDED` |
| `GET` | `/api/v1/fields/{id}/soil-lab-tests` | قائمة فحوص الحقل (الأحدث أولاً) |
| `PATCH` | `/api/v1/fields/{id}/soil-lab-tests/{test_id}` | انتقال حالة محقَّق + بيانات؛ النشر → `SOIL_LAB_RESULT_PUBLISHED` |

- صلاحيّات: `FIELD_EDIT` للإنشاء/التحديث، `FIELD_VIEW` للقائمة. ملكيّة الحقل (404)؛
  الفحص يخصّ الحقل (404). الاعتماد يسجّل `approved_by`؛ النشر يسجّل `published_at`.
- تعذّر القاعدة ⇒ `503` موثَّق. تحديث ذرّيّ مع إصدار الأحداث.
