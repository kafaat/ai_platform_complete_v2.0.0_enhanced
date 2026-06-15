# تتبّع مدخلات الإنتاج من البذرة للحصاد (Input Traceability)

استجابةً لسؤال الاستفادة من مشروع **warehouse** (`sunjulei/warehouse` — WareMap)
لتتبّع المدخلات (بذور/أسمدة/مبيدات…) انتهاءً بالحصاد.

## القرار: لا نقل WareMap — نركّب القائم
WareMap نظام **Java/Spring Boot 3 + Vue 3 + MySQL** عامّ للمستودعات. نقله إلى
سهول (Python‑FastAPI/PostgreSQL) غير صحيح:

| العائق | التفصيل |
|--------|---------|
| تعارض المكدّس | Java/MySQL مقابل Python/Postgres = مكدّس موازٍ + عبء تشغيلي |
| التكرار | **ERPNext (الأساسي)** فيه Stock/Batch‑Lot/Supplier/PO أنضج، موصول عبر `odoo-bridge` |
| الترخيص | MIT لكن يمنع إعادة البيع + ميزات عضويّة/عمولات صينيّة لا صلة لها |
| سوء المطابقة | الحاجة الزراعيّة = نَسَب per حقل+موسم، لا مخزون SME عامّ |

## الحاجة الصحيحة: نَسَب per حقل/موسم (يركّب الموجود)
- `activities` (v35): يسجّل بذر/تسميد/رشّ/ريّ بتفاصيل JSONB (تشمل المنتج/الكمّيّة/الكلفة) ✓
- `recommendation_outcomes` (v49): ناتج الحصاد الفعلي (t/ha) ✓
- أحداث `FERTILIZER_APPLIED` / `PESTICIDE_APPLIED` / `HARVEST_*` ✓
- **المخزون والشراء يبقيان في ERPNext** — هذا يجمع النَسَب الزراعي، لا يستبدل الـERP.

## المكوّن: `core/engines/input_traceability.py`
`build_input_ledger(applications, *, field_id, season_id, area_ha, harvest_yield_t_ha)`:
- يجمّع المدخلات حسب النوع بترتيب نَسَبي: **بذرة → سماد → مبيد → ريّ → حصاد**.
- يحسب `total_cost` (من الكلفة المعروفة فقط)، `cost_per_ha` (يتطلّب مساحة)،
  `cost_per_ton` (يتطلّب مساحة + إنتاجيّة حصاد فعليّة).
- حالات: `no_inputs` / `partial` / `complete` (بذرة+حصاد+تغطية كلفة كاملة).

## النقطة: `GET /api/v1/fields/{field_id}/input-traceability?season_id=…`
يقرأ `activities` (أنواع المدخلات) + مساحة الحقل + ناتج الحصاد من
`recommendation_outcomes` (savepoint — يتدهور بصدق إن لم يُفعَّل الجدول) → دفتر مدخلات.

## المبدأ المحفوظ
**صدق:** كلفة غائبة تُستثنى من الإجمالي وتُعلَن (`cost_coverage`) — لا تأليف رقم.
لا حصاد ⇒ كلفة/طنّ غير متاحة. مساحة مجهولة ⇒ كلفة/هكتار غير متاحة. النَسَب يُظهر
نقصه صراحةً (`gaps_ar`). (8 اختبارات offline.)
