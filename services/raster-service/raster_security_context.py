"""Tenant/security/source helpers for raster-service.

Extracted from main.py in phase 9 to keep main.py as a thin service façade while
preserving the existing private main._* compatibility API used by routers/tests.
"""

from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from dataclasses import dataclass
from urllib.parse import urlparse

from fastapi import HTTPException

from shared.security.trusted_tenant import service_token_ok

REQ_TENANT: ContextVar[str | None] = ContextVar("req_tenant", default=None)

_log = logging.getLogger("raster-service.tenant")

# ── مَن يحقّ له أن يُسمّي المستأجِر ──────────────────────────────────────────────
# العطلُ المقيس (التدقيق الحيّ 2026-09-29، أعاد المشرفُ إنتاجَه): كان المستأجِر
# ``X-Tenant-Id`` **أو** ``?tid=`` **أو** ``?tenant_id=`` بلا أيّ سؤالٍ عمّن يُنادي. وكلُّ
# حارسٍ بعده — ملكيّةُ الحقل (``require_field_tenant``)، ``app.current_tenant`` الذي تفرضه
# RLS، مفتاحُ ذاكرة البلاطات — يقارن بتلك القيمة نفسها. فمُنادٍ على الشبكة الداخليّة يكتب
# مستأجِرَ غيره فيجد الملكيّةَ «مطابقةً» وRLS «مُحترَمة» ويقرأ صورَه: tilejson بحدوده،
# البلاطات، الصور المصغّرة، السلاسل الزمنيّة. RLS لم تنكسر — أُعطيت المستأجِرَ الخطأ.
#
# القاعدة الآن: المستأجِر من الترويسة **وحدَها**، ويُصدَّق حين يرافقه توكن الخدمة
# ``X-Agent-Token``. البوّابتان تحقنانه خلف ``auth_request`` مع المستأجِر الموثَّق، وكلُّ
# مُنادٍ داخليّ مشروع يحمله. والاستعلامُ لا يُقرأ في أيّ وضع: ``?tid=`` كان للبلاطات
# ``<img>`` قبل أن تحقن البوّابةُ الترويسة، واليوم لا يصل الخدمةَ طلبُ بلاطةٍ مشروعٌ بلاها.
#
# والإنفاذ خلف راية لأنّ Railway يُنشر من main: خدمةُ الواجهة هناك بلا ``SAHOOL_AGENT_TOKEN``
# بعد، فإنفاذٌ يُدمَج مُفعَّلاً يكسر بلاطات staging. compose وhelm يُفعّلانه؛ وترتيب تفعيله
# على Railway (التوكن على الواجهة أوّلاً ثمّ الراية هنا) في RAILWAY_FRONTEND_DEPLOYMENT.md.
TENANT_CREDENTIAL_ENFORCE_ENV = "RASTER_TENANT_CREDENTIAL_ENFORCE"
_TRUTHY = frozenset({"1", "true", "yes", "on"})

# نتائج ادّعاء المستأجِر — تُعَدّ في /metrics فيُقاس شرطُ التفعيل بدل أن يُفترَض.
OUTCOME_NONE = "none"  # لا ادّعاء: لا ترويسة (ولا يهمّ ما في الاستعلام)
OUTCOME_CREDENTIALED = "credentialed"  # ترويسة + توكن صالح
OUTCOME_UNCREDENTIALED = "uncredentialed"  # ترويسة بلا توكن
OUTCOME_INVALID = "invalid_credential"  # ترويسة + توكن خاطئ
OUTCOME_UNCONFIGURED = "unconfigured"  # ترويسة والخدمة بلا SAHOOL_AGENT_TOKEN — عطلُ مشغّل
OUTCOME_QUERY_IGNORED = "query_hint_ignored"  # ?tid=/?tenant_id= بلا ترويسة: كان يكفي، الآن لا
ASSERTION_OUTCOMES = (
    OUTCOME_NONE,
    OUTCOME_CREDENTIALED,
    OUTCOME_UNCREDENTIALED,
    OUTCOME_INVALID,
    OUTCOME_UNCONFIGURED,
    OUTCOME_QUERY_IGNORED,
)
TENANT_ASSERTION_COUNTS: dict[str, int] = dict.fromkeys(ASSERTION_OUTCOMES, 0)


@dataclass(frozen=True)
class TenantAssertion:
    """قرار الوسيط: المستأجِر المقبول (أو None)، والنتيجة، ورمز الرفض إن وُجد."""

    tenant: str | None
    outcome: str
    status: int | None = None
    detail: str | None = None


def tenant_credential_enforced() -> bool:
    """يُقرأ عند كلّ طلب لا عند الاستيراد، فتراه الاختبارات والتهيئة المتأخّرة."""
    return os.getenv(TENANT_CREDENTIAL_ENFORCE_ENV, "").strip().lower() in _TRUTHY


def tenant_credential_posture() -> dict:
    """ما يحتاجه المشغّل ليقرّر التفعيل: الوضع + العدّادات منذ الإقلاع."""
    return {
        "mode": "enforce" if tenant_credential_enforced() else "observe",
        "assertions": dict(TENANT_ASSERTION_COUNTS),
    }


def tenant_from_header(value: str | None) -> str | None:
    """Backwards-compatible normalizer used by tests and older call sites."""
    if not value:
        return None
    value = value.strip()
    return value or None


def tenant_assertion_for_request(request, agent_token: str | None = None) -> TenantAssertion:
    """يقرّر مستأجِر الطلب: الترويسة وحدَها، ويُصدَّق ادّعاؤها بتوكن الخدمة.

    - لا ``X-Tenant-Id``      ⇒ لا مستأجِر (الحرّاس بعده تفشل مغلقة كما كانت)، ولو حمل
      الاستعلامُ ``tid``: ذاك لم يعد مصدراً في أيّ وضع.
    - ترويسة + توكن صالح      ⇒ مقبول.
    - ترويسة بلا توكن صالح    ⇒ enforce: 401 (أو 503 إن كانت الخدمة بلا توكن مضبوط —
      عطلُ مشغّلٍ لا رفضُ مُنادٍ، تمييزُ #1069 نفسه)؛ observe: مقبولٌ ومعدود.

    المقارنة عبر ``service_token_ok`` (مقارِنُ #1069 المشترك: ثابتُ الزمن، ويفشل مغلقاً على
    سرٍّ فارغ) لا نسخةٍ محلّيّة منه.
    """
    claimed = tenant_from_header(request.headers.get("X-Tenant-Id"))
    if claimed is None:
        query = request.query_params
        if tenant_from_header(query.get("tid")) or tenant_from_header(query.get("tenant_id")):
            return TenantAssertion(None, OUTCOME_QUERY_IGNORED)
        return TenantAssertion(None, OUTCOME_NONE)
    if agent_token is None:
        import raster_settings as _settings

        agent_token = _settings.AGENT_TOKEN
    presented = request.headers.get("X-Agent-Token")
    if service_token_ok(presented, agent_token):
        return TenantAssertion(claimed, OUTCOME_CREDENTIALED)
    if not agent_token:
        outcome, status = OUTCOME_UNCONFIGURED, 503
        detail = "SAHOOL_AGENT_TOKEN غير مضبوط — لا يمكن تصديق X-Tenant-Id"
    elif presented:
        outcome, status, detail = OUTCOME_INVALID, 401, "توكن خدمة غير صالح"
    else:
        outcome, status = OUTCOME_UNCREDENTIALED, 401
        detail = "X-Tenant-Id مقبولٌ من مُنادٍ يحمل X-Agent-Token فقط"
    if not tenant_credential_enforced():
        return TenantAssertion(claimed, outcome)
    return TenantAssertion(None, outcome, status, detail)


def record_tenant_assertion(decision: TenantAssertion, *, method: str, path: str) -> None:
    """يعدّ النتيجة، ويسجّل كلَّ ادّعاءٍ غير مُصدَّق (مقبولٍ في observe أو مرفوضٍ في enforce)."""
    count = TENANT_ASSERTION_COUNTS.get(decision.outcome, 0) + 1
    TENANT_ASSERTION_COUNTS[decision.outcome] = count
    if decision.outcome in (OUTCOME_NONE, OUTCOME_CREDENTIALED, OUTCOME_QUERY_IGNORED):
        return
    # الأوّلُ ثمّ كلُّ ألف: في observe قد يكون كلُّ بلاطةٍ ادّعاءً غير مُصدَّق، والعدّادُ هو
    # المقياس — السجلّ يكفيه أن يقول إنّ الصنف موجود وأين.
    if count == 1 or count % 1000 == 0:
        _log.warning(
            "tenant assertion %s outcome=%s count=%d method=%s path=%s",
            "rejected" if decision.status else "accepted-unverified (observe mode)",
            decision.outcome,
            count,
            method,
            path,
        )


def tenant_from_request(request) -> str | None:
    """المستأجِر المقبول لهذا الطلب وفق القاعدة أعلاه (None إن لم يُقبَل)."""
    return tenant_assertion_for_request(request).tenant


_field_owner_cache: dict[str, tuple[str | None, float]] = {}
_FIELD_OWNER_TTL_OK = 300.0
_FIELD_OWNER_TTL_MISS = 15.0


async def field_owner(field_id: str) -> str | None:
    """Trusted field owner lookup with short TTL caching."""
    import time as _t

    now = _t.monotonic()
    hit = _field_owner_cache.get(field_id)
    if hit is not None and hit[1] > now:
        return hit[0]
    import db_persist

    owner = await db_persist.field_owner_tenant(field_id)
    ttl = _FIELD_OWNER_TTL_OK if owner else _FIELD_OWNER_TTL_MISS
    _field_owner_cache[field_id] = (owner, now + ttl)
    return owner


async def require_field_tenant(
    field_id: str,
    *,
    hide_existence: bool = False,
    layers: dict[str, dict],
    field_layers: dict[str, list[str]],
    logger,
    owner_lookup=None,
) -> None:
    """Authorize field ownership using DB as source of truth when available."""
    req_tenant = REQ_TENANT.get()
    import db_persist

    try:
        owner = await (owner_lookup or field_owner)(field_id)
    except db_persist.OwnerLookupUnavailable as e:
        raise HTTPException(503, "تعذّر إثبات ملكيّة الحقل — أعد المحاولة لاحقاً") from e

    if owner:
        if not req_tenant or owner != req_tenant:
            raise HTTPException(
                404 if hide_existence else 403,
                "الحقل غير موجود" if hide_existence else "الحقل لا يخصّ مستأجِرك",
            )
        kept: list[str] = []
        for lid in field_layers.get(field_id, []):
            lyr = layers.get(lid)
            cached_owner = lyr.get("tenant_id") if lyr else None
            if cached_owner and cached_owner != req_tenant:
                logger.warning(
                    "pruning stale field layer tenant cache field=%s layer=%s cached=%s request=%s",
                    field_id,
                    lid,
                    cached_owner,
                    req_tenant,
                )
                continue
            kept.append(lid)
        if kept != field_layers.get(field_id, []):
            field_layers[field_id] = kept
        return

    # DB-less/field not known: fall back to in-memory defense only.
    for lid in field_layers.get(field_id, []):
        lyr = layers.get(lid)
        cached_owner = lyr.get("tenant_id") if lyr else None
        if cached_owner and cached_owner != req_tenant:
            raise HTTPException(
                404 if hide_existence else 403,
                "الحقل غير موجود" if hide_existence else "الحقل لا يخصّ مستأجِرك",
            )


def require_layer_tenant(layer_id: str, *, layers: dict[str, dict]) -> None:
    """Fast in-memory authorization for layer ownership."""
    req_tenant = REQ_TENANT.get()
    lyr = layers.get(layer_id)
    owner = lyr.get("tenant_id") if lyr else None
    if owner and owner != req_tenant:
        raise HTTPException(403, "الطبقة لا تخصّ مستأجِرك")


async def require_layer_tenant_authorized(
    layer_id: str, *, layers: dict[str, dict], logger
) -> None:
    """Authorize layer ownership with DB as source of truth when available."""
    req_tenant = REQ_TENANT.get()
    try:
        import db_persist

        db_owner = await db_persist.layer_owner_tenant(layer_id)
    except db_persist.OwnerLookupUnavailable as e:
        raise HTTPException(503, "تعذّر إثبات ملكيّة الطبقة — أعد المحاولة لاحقاً") from e

    if db_owner:
        if not req_tenant:
            raise HTTPException(403, "مستأجر الطلب مطلوب لقراءة الطبقة")
        if db_owner != req_tenant:
            raise HTTPException(403, "الطبقة لا تخصّ مستأجِرك")
        lyr = layers.get(layer_id)
        if lyr and lyr.get("tenant_id") and lyr.get("tenant_id") != req_tenant:
            logger.warning(
                "correcting stale layer tenant cache layer=%s cached=%s db=%s",
                layer_id,
                lyr.get("tenant_id"),
                db_owner,
            )
            lyr["tenant_id"] = db_owner
        return

    require_layer_tenant(layer_id, layers=layers)
    lyr = layers.get(layer_id)
    owner = lyr.get("tenant_id") if lyr else None
    if owner and not req_tenant:
        raise HTTPException(403, "مستأجر الطلب مطلوب لقراءة الطبقة")
    if not owner and not req_tenant:
        raise HTTPException(403, "مستأجر الطلب مطلوب لقراءة الطبقة")


def public_cog_url(cog_url: str | None) -> str | None:
    """Return cog_url only when a tile can actually be served from it.

    **The accept-set must stay inside the transport's accept-set.** This predicate
    decides whether a tile template is *advertised*; `fetch_registered_cog_tile`
    decides whether that same source may be *fetched*, and it requires `https`
    on the default port with no embedded credentials or fragment. When this
    function was the looser of the two — it accepted `http://` and any port — a
    layer carrying such a source passed here, TileJSON advertised its tiles, and
    every tile then returned `422 cog_tile_source_not_allowed`: an advertised
    template that cannot produce one pixel. Widening either side alone restores
    that split, so the agreement is measured, not restated
    (`test_every_advertised_source_is_one_the_transport_will_fetch`).
    """
    if not cog_url:
        return None
    low = cog_url.strip().lower()
    if not low.startswith("https://"):
        return None
    if any(h in low for h in ("sahool-", "minio", "localhost", "127.0.0.1", ":9000", ".internal")):
        return None
    try:
        parsed = urlparse(cog_url.strip())
    except ValueError:
        return None
    if parsed.username or parsed.password or parsed.fragment:
        return None
    try:
        if parsed.port not in (None, 443):
            return None
    except ValueError:  # malformed port — not a servable source
        return None
    return cog_url


def safe_raster_source(url: str | None, upload_dir: str, blocked_hosts: set[str]) -> str:
    """Validate a raster source before rasterio.open; blocks path traversal and SSRF."""
    if not url or not isinstance(url, str):
        raise HTTPException(400, "مصدر راستر غير صالح")
    if url.startswith("file://") or url.startswith("/"):
        raw = url[len("file://") :] if url.startswith("file://") else url
        path = os.path.realpath(raw)
        base = os.path.realpath(upload_dir)
        if path != base and not path.startswith(base + os.sep):
            raise HTTPException(400, "مسار ملفّ خارج المجلّد المسموح (traversal مرفوض)")
        return path
    if url.startswith(("http://", "https://")):
        host = (urlparse(url).hostname or "").lower()
        if host in blocked_hosts:
            raise HTTPException(400, "مضيف محجوب (SSRF)")
        return url
    raise HTTPException(400, "مخطّط URL غير مدعوم لمصدر الراستر")


def assert_readable_size(src, *, what: str, ceiling: int) -> int:
    """يرفض راستراً أكبر من السقف **قبل** تخصيص أيّ مصفوفة. يُرجِع عدد بكسلات-النطاق.

    ``UNBOUNDED-RASTER-READ-ON-ARBITRARY-URL-01``. ``rasterio.open`` يعطي الأبعاد بلا
    قراءة بكسل واحد، فالفحص هنا مجّانيّ — بينما ``src.read()`` يخصّص
    ``width × height × count`` بايتاً دفعةً واحدة. و``safe_raster_source`` أعلاه يقبل
    **أيّ** رابط ``http(s)`` غير محجوب، فحجم المصدر ليس تحت سيطرة الخدمة.

    **الرفض المُعلَن أصدق من OOM صامت:** حاويةٌ تُقتَل بـSIGKILL لا تترك سبباً في أيّ
    سجلّ ولا في أيّ صفّ، بينما هذا يُسمّي الأبعاد والسقف ويقول ماذا يفعل المُستدعي.
    """
    band_pixels = int(src.width) * int(src.height) * int(src.count)
    if band_pixels > int(ceiling):
        raise HTTPException(
            413,
            f"راستر أكبر من سقف القراءة ({what}): "
            f"{src.width}×{src.height}×{src.count} = {band_pixels:,} بكسل-نطاق "
            f"> {int(ceiling):,}. قُصّ المصدر، أو ارفع RASTER_MAX_READ_BAND_PIXELS بوعي.",
        )
    return band_pixels


def require_service_token(x_agent_token: str | None, agent_token: str | None = None) -> None:
    """Service-to-service authentication for write/storage endpoints.

    ``agent_token`` اختياريّ: غيابُه يعني «التوكن المضبوط للخدمة» (`raster_settings.AGENT_TOKEN`
    يُقرأ عند النداء لا عند الاستيراد، فتراه الاختبارات والتهيئة المتأخّرة). كان الوسيط
    إلزاميّاً بينما 14 نداءً في خمسة راوترات تمرّر الترويسة وحدَها — فكان كلُّ طلب على تلك
    النقاط يسقط بـTypeError (500) قبل أيّ تحقّق (التدقيق الموحَّد 2026-09-13، P0).
    """
    if agent_token is None:
        import raster_settings as _settings

        agent_token = _settings.AGENT_TOKEN
    if not agent_token:
        raise HTTPException(503, "SAHOOL_AGENT_TOKEN غير مضبوط — الرفع معطّل بأمان")
    if not service_token_ok(x_agent_token, agent_token):
        raise HTTPException(401, "توكن خدمة غير صالح")
