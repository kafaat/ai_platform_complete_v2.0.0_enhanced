# v49 — تفعيل الربط الحيّ لميزات #62/#63

كانت ميزات مبنيّة تتدهور بصدق إلى «لا بيانات» لأنّ مخطّط القاعدة يفتقر عمودين/جدولاً.
هجرة **v49** تضيفهما، فتنتقل الميزات من «المخطّط غير جاهز» إلى **«حيّة، تنتظر بيانات»**.

## ما أضافته v49
| العنصر | يُفعّل |
|--------|--------|
| `fields.zone_key VARCHAR(64)` + فهرس | `GET /market/crop-gap` · `GET /market/crop-classification-readiness` (#63) |
| جدول `recommendation_outcomes` (+ RLS لكلّ مستأجِر) | `GET /learning/prediction-calibration` · `GET /learning/activation-status` (#62/#63) |

## الربط (تلقائيّ — لا تخمين)
- النقاط الأربع كانت تلتقط `UndefinedColumn/Table` وتتدهور؛ الآن **schema_ready=true**
  وتقرأ القيم الحيّة عبر RLS.
- `learning/activation-status` أصبح **حيّاً** (كان placeholder صفريّ): يحسب
  total/completed/accepted/within-lag من `recommendation_outcomes`.
- `zone_key` صار حقلاً في النموذج (settable عبر `PATCH /fields/{id}`, readable في التفاصيل).

## مسار الكتابة (الحلقة كاملة)
- `POST /api/v1/recommendations/outcomes` يسجّل نتيجة توصية (توقّع/فعليّ + قبول/نضج)
  — يغذّي المعايرة والتفعيل. tenant عبر RLS (WITH CHECK).

## ما **يبقى** (صدق — لا يُدّعى أنّه يعمل بلا بيانات)
- **تعبئة `zone_key`** لكلّ حقل (يدويّاً عبر PATCH، أو إثراء تلقائيّ لاحق من الإحداثيّات).
- **تراكم `recommendation_outcomes`**: حتى تُسجَّل نتائج كافية (≥3 أزواج، ≥2 مزرعة،
  نضج زمنيّ)، تبقى المعايرة «عيّنة غير كافية» والتفعيل «خاملة» — **بصدق**.
- لا تنبّؤ/اختراع: المعايرة حتميّة من أزواج موثّقة فقط.
