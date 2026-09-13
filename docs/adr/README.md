# سجلّات قرارات المعماريّة (ADR)

استجابةً لتوصية المراجعة (#1): توثيق القرارات المعماريّة المهمّة.
كلّ ADR يوثّق: السياق، القرار، العواقب.

- ADR-0001: تجريد مزوّد ERP
- ADR-0036: قاطع دائرة MCP
- ADR-0037: سلسلة تفسير القرار (explainability)
- ADR-0032: متحكّم الريّ التنبّؤيّ الهرميّ المعجميّ (Lexicographic MPC) — سلّم أولويّات غير قابل للمقايضة الماليّة (حماية المحصول≻ماء/طاقة≻حدّ إنتاج≻هامش)، توصية-فقط، الطاقة `not_modelled` حتى المرحلة 2.
- ADR-0035: معايرة المحرّك الفيزيائيّ بالذكاء الاصطناعيّ (PHYSICS-AI-CALIBRATION-01) — قرار مرجعيّ معتمد؛ **البناء محجوب** حتى تحقّق `build_unlock` حرفيًّا (دفتر المياه + SIM-GOLDEN + أهليّة المواسم + البرهان السلبيّ).

(تُضاف ADRs للقرارات المستقبليّة: schema registry، K8s migration، Vault، إلخ)


## Identifier reconciliation — 2026-09-13

| Historical filename | Canonical identifier and file | Reason |
|---|---|---|
| `0002-circuit-breaker-mcp.md` | [ADR-0036](ADR-0036-circuit-breaker-mcp.md) | ADR-0002 already identifies the farm operations ledger |
| `0003-explainability-lineage.md` | [ADR-0037](ADR-0037-explainability-lineage.md) | ADR-0003 already identifies ledger budget/cost intelligence |

Historical brain entries retain their original references; this table resolves
them without rewriting decision history. ADR-0033 now records the existing
signed-assertion and production Redis nonce implementation.
