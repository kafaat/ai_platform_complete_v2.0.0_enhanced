# ADR-0003: موازنة الموسم والتكاليف والانحرافات فوق Farm Operations Ledger

## الحالة
مقبول — مُطبّق خلف `FEATURE_FARM_OPERATIONS_LEDGER`.

## السياق
بعد تنفيذ Farm Operations Ledger كسجل رقابي للأعمال اليومية والمياه والطاقة والمعدات والعمالة والمدخلات، احتاجت SAHOOL إلى تحويل هذه السجلات إلى موازنة موسم، انحرافات، ربحية، وتوصيات تخفيض تكلفة بدون بناء ERP كامل أو كسر المسارات القائمة.

## القرار
إضافة طبقة Costing نقية داخل `core/farm_costing.py`:

- `SeasonBudgetLine` لبنود الموازنة حسب المرحلة والتصنيف.
- `ActualCostLine` مستمدة من Farm Operations Ledger.
- `compute_variances` لمقارنة المخطط بالفعلي.
- `allocate_indirect_costs` للتكاليف غير المباشرة.
- `compute_profitability` لربحية الموسم.
- `generate_cost_recommendations` توصيات rule-based قابلة للشرح ولا تدّعي تنبؤاً.
- `project_to_erp_lines` إسقاط مالي اختياري، لا يكتب إلى ERP.

الجداول الجديدة في `v101_farm_budget_costing.sql`، وكلها RLS ومربوطة بالمستأجر.

## العواقب
- (+) يمكن للمزارع الصغير استخدام SAHOOL كسجل رقابي وتكاليف مبسط بدون ERP.
- (+) يمكن للشركات مزامنة الإسقاط المالي لاحقاً عبر ERPProvider دون فقد التفاصيل التشغيلية.
- (+) توصيات خفض التكلفة تصبح مبنية على بيانات مسجلة لا افتراضات.
- (−) ليست محاسبة مزدوجة ولا تغني عن ERP كامل للشركات التي تحتاج General Ledger.
