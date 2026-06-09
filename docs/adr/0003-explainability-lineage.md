# ADR-0003: سلسلة تفسير القرار (Explainability Lineage)

## الحالة
مقبول — مُطبَّق (CanonicalFieldState.explain_decision)

## السياق
المراجعة طلبت "explainable decision system / conflict audit lineage". التحقّق
كشف أنّ العناصر موجودة لكن مبعثرة: provenance (لكلّ حقيقة)، arbitration reason
(لماذا فاز الوضع)، conflict resolution (التعارضات المحلولة)، confidence reason.

## القرار
**لم نبنِ policy DSL ثقيلاً** (تحذير المراجعة من over-engineering/complexity
trap). بدلاً من ذلك: دالّة `explain_decision()` تُصدّر ما يحسبه المايسترو
أصلاً في سلسلة موحّدة:
- القرار: effective_status + reason_ar + winning_rule
- الثقة: level + reason (رياضي)
- سلسلة الأدلّة: provenance (كلّ حقيقة ← مصدر + وزن)
- التعارضات المحلولة: conflict audit lineage (ما تجاوز ماذا + القاعدة)

## العواقب
- (+) شفافيّة كاملة: كلّ قرار قابل للتفسير والتدقيق
- (+) بلا تعقيد جديد (تصدير الموجود لا طبقة جديدة)
- (−) ليس policy DSL قابلاً للتهيئة من المستأجر (مؤجّل — يحتاج طلباً فعليّاً)

## ما لم نبنِه (صدق — أهداف مستقبليّة)
- tenant-configurable policy weights (يحتاج حالة استخدام فعليّة)
- temporal economic optimization (seasonal cash-flow, risk-adjusted ROI)
- uncertainty propagation / probabilistic reasoning
هذه أُجّلت عمداً: المراجعة نفسها حذّرت من بناء طبقات قبل الحاجة.
