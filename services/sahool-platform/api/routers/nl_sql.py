"""api/routers/nl_sql.py — مساعد GIS بالذكاء: لغة طبيعيّة → SQL (read-only، اقتباس GeoLibre #4)

نقطة واحدة محروسة بعلم ``FEATURE_NATURAL_LANGUAGE_GIS`` + وجود ``ANTHROPIC_API_KEY``:

  • ``POST /api/v1/nl-sql`` — يأخذ سؤالاً عربيّاً، يستدعي Claude **خادميّاً** (المفتاح لا يصل
    المتصفّح) لترجمته إلى ``SELECT`` للقراءة فقط على جدول DuckDB ``fields`` الذي تبنيه الواجهة
    في المتصفّح. يُعيد الـSQL فقط؛ الواجهة تعرضه للمراجعة ثمّ تُنفّذه في **DuckDB العميل**
    (نسخة في الذاكرة لا تمسّ قاعدة الخلفيّة).

حُرّاس (صدق + أمان):
  • **المفتاح خادميّ حصراً** — مراجعة أمنيّة: استدعاء Anthropic من الواجهة يكشف المفتاح.
  • **تحقّق خادميّ** (``nl_sql_validate``): العائد عبارة ``SELECT/WITH`` مفردة — يُرفض DML/DDL/
    PRAGMA/ATTACH/COPY/«;». read-only بالبنية: الـSQL يُنفَّذ في sandbox العميل لا الخلفيّة.
  • **tenant من JWT** + RBAC (``RECOMMENDATION_VIEW``) + حدّ معدّل لكلّ tenant.
  • **صدق:** flag مُطفأ ⇒ 404؛ flag مُفعَّل بلا مفتاح ⇒ 503 (لا تلفيق، لا SQL مُختلَق).
"""

from __future__ import annotations

import os
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.main import Permission, UserSchema, require_permission
from api.nl_sql_validate import SYSTEM_PROMPT, extract_sql, validate_select

router = APIRouter()

_TRUTHY = {"1", "true", "yes", "on"}
_DEFAULT_MODEL = "claude-opus-4-8"  # افتراضيّ (مرجع Claude API)؛ قابل للضبط بـNL_SQL_MODEL
_MAX_TOKENS = 400
_RATE_LIMIT_PER_MIN = 10
_calls: dict[str, list[float]] = defaultdict(list)


def _enabled() -> bool:
    return os.getenv("FEATURE_NATURAL_LANGUAGE_GIS", "").strip().lower() in _TRUTHY


def _api_key() -> str | None:
    return (os.getenv("ANTHROPIC_API_KEY", "").strip()) or None


def _model() -> str:
    return os.getenv("NL_SQL_MODEL", "").strip() or _DEFAULT_MODEL


def _check_rate_limit(tenant_id: str) -> bool:
    """يسمح بـ10 طلبات/دقيقة لكلّ مستأجِر (يمنع استنزاف رصيد API)."""
    now = time.time()
    window = [t for t in _calls[tenant_id] if now - t < 60]
    _calls[tenant_id] = window
    if len(window) >= _RATE_LIMIT_PER_MIN:
        return False
    _calls[tenant_id].append(now)
    return True


class NlSqlQuery(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class NlSqlResult(BaseModel):
    sql: str


@router.post("/api/v1/nl-sql", response_model=NlSqlResult)
async def nl_sql_endpoint(
    body: NlSqlQuery,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> NlSqlResult:
    if not _enabled():
        raise HTTPException(status_code=404, detail="الميزة غير مُفعَّلة")
    key = _api_key()
    if not key:  # flag مُفعَّل لكن لا مفتاح ⇒ 503 صادق (لا تلفيق)
        raise HTTPException(status_code=503, detail="مساعد الذكاء غير مُهيّأ (مفتاح مفقود)")
    if not _check_rate_limit(str(user.tenant_id)):
        raise HTTPException(status_code=429, detail="طلبات كثيرة — حاول بعد قليل")

    try:
        import anthropic  # تبعيّة المساعد (تُحمَّل عند الحاجة فقط)
    except ImportError:  # pragma: no cover
        raise HTTPException(status_code=503, detail="مكتبة الذكاء غير متاحة") from None

    try:
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model=_model(),
            max_tokens=_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": body.question}],
        )
        text = "".join(
            getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text"
        )
    except Exception:  # noqa: BLE001 — لا نُسرّب تفاصيل المزوّد للواجهة
        raise HTTPException(status_code=502, detail="تعذّر توليد الاستعلام") from None

    try:
        sql = validate_select(extract_sql(text))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"تعذّر توليد استعلام آمن: {exc}") from exc
    return NlSqlResult(sql=sql)
