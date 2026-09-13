# ADR-0036: قاطع دائرة لمكالمات MCP

Historical alias: `0002-circuit-breaker-mcp.md`. Renumbered on 2026-09-13 to resolve an ID collision; the decision itself is unchanged.

## الحالة
مقبول — مُطبَّق (services/supervisor-agent/circuit_breaker.py)

## السياق
المنصّة event-driven متعدّدة الخدمات. كان فيها retry + timeout لكن بلا circuit
breaker → خدمة فاشلة تُغرَق بالطلبات (cascading failure).

## القرار
قاطع دائرة بثلاث حالات (CLOSED/OPEN/HALF_OPEN) لكلّ خدمة MCP مستقلّاً، موصول
بـcall_tool. عتبة 5 إخفاقات → فتح، مهلة 30ث → اختبار، نجاحان → إغلاق.

## العواقب
- (+) fail-fast: لا إغراق لخدمة متعطّلة
- (+) تعافٍ تلقائي (HALF_OPEN)
- (+) عزل الفشل (قاطع مستقلّ لكلّ خدمة)
- (−) قد يرفض طلبات أثناء تعافٍ مؤقّت (مقبول — يحمي النظام)
