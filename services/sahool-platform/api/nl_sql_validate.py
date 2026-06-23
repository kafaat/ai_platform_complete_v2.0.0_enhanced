"""api/nl_sql_validate.py — تحقّق نقيّ من SQL المُولَّد بالذكاء (read-only، اقتباس GeoLibre #4).

مفصول عن الراوتر (لا FastAPI/anthropic/api.main) ليكون قابلاً للاختبار وحدويّاً — نظير
``api/nl_gis_intent.py``. الواجهة تُنفّذ الـSQL في DuckDB العميل (sandbox في المتصفّح، نسخة
في الذاكرة لا تمسّ الخلفيّة)؛ هذا التحقّق **دفاع متعمّق** يمنع ملء المحرّر بما ليس قراءةً.
"""

from __future__ import annotations

import re

# مخطّط الجدول الوحيد المتاح (يطابق ما تبنيه الواجهة في DuckDB — frontend/src/services/duckdb.ts).
FIELDS_SCHEMA = (
    "fields(id VARCHAR, name VARCHAR, crop VARCHAR, area_ha DOUBLE, lat DOUBLE, lon DOUBLE)"
)

# تعليمات النظام لـClaude (السؤال عربيّ → SELECT واحد بلهجة DuckDB، للقراءة فقط).
SYSTEM_PROMPT = (
    "أنت مساعد يترجم سؤال المستخدم العربيّ إلى استعلام SQL واحد بلهجة DuckDB.\n"
    f"الجدول الوحيد المتاح: {FIELDS_SCHEMA}.\n"
    "قواعد صارمة:\n"
    "- أعِد عبارة SELECT واحدة للقراءة فقط (أو WITH … SELECT). يُمنع تماماً INSERT/UPDATE/"
    "DELETE/CREATE/DROP/ALTER/ATTACH/COPY/PRAGMA/INSTALL/LOAD أو أيّ تعديل.\n"
    "- لا فاصلة منقوطة، ولا تعدّد عبارات.\n"
    "- استخدم الأعمدة المذكورة أعلاه فقط؛ المساحة بالهكتار في area_ha.\n"
    "- أعِد الـSQL فقط: بلا شرح، بلا أسوار كود، بلا نصّ إضافيّ."
)

# كلمات تعديل/إدارة محظورة (دفاع متعمّق — العبارة مُلزَمة أصلاً بالبدء بـSELECT/WITH وبلا «;»).
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|create|alter|attach|copy|pragma|truncate|"
    r"grant|revoke|vacuum|install|load|export|import|call)\b",
    re.IGNORECASE,
)


def extract_sql(text: str) -> str:
    """يستخرج SQL من ردّ النموذج: يزيل أسوار ``` ```sql … ``` ``` والمسافات والفاصلة الأخيرة."""
    s = (text or "").strip()
    m = re.match(r"^```(?:sql)?\s*(.*?)\s*```$", s, re.DOTALL | re.IGNORECASE)
    if m:
        s = m.group(1).strip()
    return s.strip().rstrip(";").strip()


def validate_select(sql: str) -> str:
    """يتحقّق أنّ النصّ عبارة قراءة مفردة (SELECT/WITH). يُعيد النصّ النظيف أو يرفع ValueError.

    نقيّ (لا I/O) ⇒ قابل للاختبار. لا يُلفّق: المخالفة ترفع خطأً واضحاً بدل تمرير شيء غير آمن.
    """
    s = (sql or "").strip().rstrip(";").strip()
    if not s:
        raise ValueError("استعلام فارغ")
    if ";" in s:
        raise ValueError("تعدّد العبارات غير مسموح")
    low = s.lstrip("(").lstrip().lower()
    if not (low.startswith("select") or low.startswith("with")):
        raise ValueError("يُسمح بـSELECT (للقراءة) فقط")
    if _FORBIDDEN.search(s):
        raise ValueError("كلمة مفتاحيّة محظورة (للقراءة فقط)")
    return s
