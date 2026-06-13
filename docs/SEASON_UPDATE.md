# تحديث الموسم الصريح + `SEASON_UPDATED`

يسدّ ثغرة مذكورة في `POST_DEPLOYMENT_ROADMAP.md` (تكملة تغطية أحداث الموسم بعد
`SEASON_CREATED`/`SEASON_CLOSED` في #74).

## النقطة: `PATCH /api/v1/fields/{field_id}/seasons/{season_id}`
- **تحديث جزئيّ:** الحقول الممرَّرة فقط (`status`/`crops`/`cultivar`/`irrigation_type`/
  `seed_rate_kg_ha`/`sowing_date`/`season_end`/KPIs).
- **صلاحية** `FIELD_EDIT` · تأكيد ملكيّة الحقل (404) · الموسم يخصّ الحقل (404).
- يُصدِر **`SEASON_UPDATED`** (مع `changed_fields`)، و**`SEASON_CLOSED`** أيضاً عند
  الانتقال إلى `closed` — ضمن نفس المعاملة (نمط outbox).
- لا حقول للتحديث → `422`. نهاية الموسم قبل البذار → `422`. نوع ريّ مجهول → `422`.

## نواة الانتقال: `api/season_lifecycle.py` (نقيّة، مُختبَرة offline)
`validate_status_transition(current, target)` — مصدر واحد لقواعد الحالة:

| من \ إلى | planned | active | closed |
|---------|:-------:|:------:|:------:|
| **planned** | لا-عمل | ✅ | ✅ |
| **active** | ✋ 422 | لا-عمل | ✅ |
| **closed** | ✋ 422 | ✋ 422 | لا-عمل |

- نفس الحالة = **لا-عمل** (idempotent) لا انتقال.
- **المُغلَق نهائيّ** (لا إحياء — يحفظ التاريخ وثابت «موسم نشط واحد»).
- حالة مجهولة → `422` صريح (لا تخمين).

## الثوابت المحفوظة
- ثابت «موسم نشط واحد للحقل»: انتقال `planned→active` وهناك نشط ⇒ `409`
  (`uq_seasons_one_active`) — كما في الإنشاء.
- التحديث ذرّيّ مع إصدار الأحداث (معاملة واحدة). تعذّر القاعدة ⇒ `503` موثَّق.

(٧ اختبارات offline لنواة الانتقال.)
