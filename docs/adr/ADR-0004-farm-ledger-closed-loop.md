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

### ملحق F-D10 / F-D11 (2026-11-22)

- `autowrite-preview` حدُّ معاينةٍ مقصود: لا مستهلِك في المنصّة يطبّق `ledger_payload`، فيبقى
  `would_persist=false` و`persisted=false` حتّى مع العلم، ويُعلن `write_path` (إنسانٌ يرسل
  الحمولة إلى `POST /api/v1/farm-ledger/operations` بمفتاح `Idempotency-Key`).
- `inventory-projection` إسقاطٌ لا يكتب أبداً (`inventory_write=false`)؛ مع
  `FEATURE_LEDGER_INVENTORY_SYNC` تبقى الأسطر `disabled_reason=projection_only`.
- الكتابة الوحيدة في `inventory_batches` (مالكها المنصّة): خطوةٌ صريحة في
  `POST /api/v1/farm-ledger/operations` خلف `FEATURE_LEDGER_INVENTORY_DEDUCTION=false` —
  مُدخَلٌ يسمّي `inventory_batch_id`، عمليّةٌ `completed`، و`Idempotency-Key` إلزاميّ؛ يُقفَل صفّ
  الدفعة ويُخصَم في معاملة السجلّ نفسها، ويُرفَض (لا كتابة) على دفعة مستأجرٍ آخر أو صنفٍ/وحدةٍ
  مختلفة أو رصيدٍ ناقص. الإيصال هو الناتج المخزَّن تحت المفتاح. لا ترحيل (migration).

## العواقب
- (+) يمكن اختبار الحلقة كاملة دون أي تغيير إنتاجي.
- (+) ERP والمخزون يستقبلان إسقاطاً فقط، وليس كتابة فعلية.
- (+) AI Cost Intelligence يبدأ بقواعد تفسيرية لا تتظاهر بأنها ML.
- (-) الواجهات و Mobile Offline ما زالت مرحلة لاحقة.
