# ADR-0004: Farm Ledger Closed Loop بدون كسر النظام

## الحالة
مقبول — مُطبّق خلف أعلام تعطيل افتراضية.

## السياق
بعد إنشاء Farm Operations Ledger ثم موازنة الموسم والانحرافات والربحية، احتاجت SAHOOL إلى إغلاق الحلقة:

Operation → Resource Consumption → Ledger → Budget → Variance → Profitability → Recommendation → ERP/Inventory Projection.

لكن يجب ألا يحدث خصم مخزون أو إرسال ERP أو كتابة في CanonicalFieldState افتراضياً.

## القرار
إضافة طبقة `farm_closed_loop` كنواة نقية، مع endpoints للمعاينة والإسقاط والحالة الاقتصادية:

- `POST /api/v1/farm-ledger/autowrite-preview`
- `GET /api/v1/farm-ledger/inventory-projection/{season_id}`
- `GET /api/v1/farm-ledger/economic-state/{season_id}`

الأعلام:

- `FEATURE_OPERATION_LEDGER_AUTOWRITE=false`
- `FEATURE_LEDGER_INVENTORY_SYNC=false`
- `FEATURE_CANONICAL_ECONOMICS=false`

## العواقب
- (+) يمكن اختبار الحلقة كاملة دون أي تغيير إنتاجي.
- (+) ERP والمخزون يستقبلان إسقاطاً فقط، وليس كتابة فعلية.
- (+) AI Cost Intelligence يبدأ بقواعد تفسيرية لا تتظاهر بأنها ML.
- (-) الواجهات و Mobile Offline ما زالت مرحلة لاحقة.
