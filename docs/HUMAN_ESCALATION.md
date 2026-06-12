# تصعيد الشكّ لإنسان (AI↔human escalation)

استلهام صادق من مراجعة AI-CS («تبديل AI↔بشري عند نقص الثقة»)، **متّسق مع
`confidence_gate` القائم** — لا يكرّره بل يعمّمه ويجعله actionable.

## ما كان موجوداً (لم يُكرَّر)
- `api/confidence_gate.py` + `POST /api/v1/confidence-gate`: يقرّر للمحرّكات
  CONFIDENT/REVIEW/BLOCKED («الشكّ يُحوّل لإنسان لا يُبتّ آليّاً»). ✓

## الفجوة المسدودة
1. لا **طلب تصعيد actionable** (لِمن؟ بأيّ أولويّة؟ ما المجهول؟) — فقط قرار + نصّ.
2. لا تغطية لمسار **RAG/سؤال المعرفة** (قد يُجيب بلا سند كافٍ → هلوسة).

## المكوّن: `core/engines/human_escalation.py`
| الدالّة | الوظيفة |
|--------|---------|
| `assess_escalation(confidence, *, source, has_answer, uncertain_points)` | من **أيّ** ثقة (محرّك/RAG): ≥0.80 لا تصعيد · [0.50,0.80) مراجعة مرشد · <0.50 أو بلا سند → **BLOCKED** (لا تأليف) |
| `escalation_from_gate(gate_result)` | يجسّر مخرَج `confidence_gate` إلى طلب تصعيد (مستلِم/أولويّة/نقاط مجهول من فجوات المحرّكات) |

**المخرَج:** `needs_escalation` · `level` · `recipient_role_ar` (مرشد زراعي / + بيانات ناقصة) · `priority` (medium/high) · `uncertain_points_ar` · `reason_ar`.

## النقطة: `POST /api/v1/escalation/assess`
يقبل `confidence` (أو null) + `source` + `has_answer` + `uncertain_points` → طلب التصعيد. يعمّم المبدأ لأيّ مصدر — خصوصاً **RAG**: `has_answer=false`/`confidence=null` ⇒ **BLOCKED** (تصعيد لمرشد، لا إجابة مولّدة).

## المبدأ المحفوظ
**human-in-the-loop**: الشكّ يُحوّل لإنسان لا يُبتّ آليّاً. **بلا سند/ثقة كافية: لا
توصية/إجابة مولّدة — تصعيد شفّاف يُظهر المجهول.** (8 اختبارات offline.)
