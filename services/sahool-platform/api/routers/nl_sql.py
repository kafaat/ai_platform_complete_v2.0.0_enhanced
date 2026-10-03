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

from core.ai_policy_envelope import build_ai_policy_envelope, load_tenant_ai_policy_row
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.main import Permission, UserSchema, require_permission, tenant_connection
from api.nl_sql_validate import SYSTEM_PROMPT, extract_sql, validate_select
from shared.ai.provider_contract import normalize_provider

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

    try:
        async with tenant_connection(user) as conn:
            policy_row = await load_tenant_ai_policy_row(conn, user.tenant_id)
    except Exception:  # noqa: BLE001 — لا خروجَ خارجيّاً دون إثبات سياسة المستأجر
        raise HTTPException(status_code=503, detail="تعذّر التحقّق من سياسة الذكاء") from None
    policy = build_ai_policy_envelope(user.tenant_id, policy_row)
    # السؤال خامّ؛ لا يوجد مسار تنقيح مُثبت هنا. redacted_external لا يجيز
    # تمريره كما هو، ووجود المفتاح/العلم لا يقوم مقام موافقة المستأجر.
    if policy["policy_mode"] != "full_external" or policy["external_llm_allowed"] is not True:
        raise HTTPException(status_code=403, detail="سياسة المستأجر لا تسمح بإرسال السؤال خارجياً")
    providers = policy_row.get("allowed_providers", [])
    models = policy_row.get("allowed_models", [])
    model = _model()
    if (
        not isinstance(providers, list)
        or not isinstance(models, list)
        or (providers and not any(normalize_provider(item) == "anthropic" for item in providers))
        or (models and model not in models)
    ):
        raise HTTPException(status_code=403, detail="المزوّد أو النموذج غير مسموح في سياسة المستأجر")
    if not _check_rate_limit(str(user.tenant_id)):
        raise HTTPException(status_code=429, detail="طلبات كثيرة — حاول بعد قليل")

    try:
        import anthropic  # تبعيّة المساعد (تُحمَّل عند الحاجة فقط)
    except ImportError:  # pragma: no cover
        raise HTTPException(status_code=503, detail="مكتبة الذكاء غير متاحة") from None

    try:
        async with anthropic.AsyncAnthropic(api_key=key, timeout=20.0, max_retries=0) as client:
            resp = await client.messages.create(
                model=model,
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
