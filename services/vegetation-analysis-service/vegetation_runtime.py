"""Runtime implementation for vegetation analysis.

Extracted from ``main.py`` as a behavior-preserving P1 decomposition step. The
FastAPI entrypoint re-exports these names so existing routers and tests that
refer to ``main.X`` keep working while computation/provider logic lives here.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import httpx
import jwt as _jwt
from fastapi import HTTPException
from fastapi.security import HTTPBearer
from prometheus_client import (
    CONTENT_TYPE_LATEST,  # noqa: F401 — إعادة تصدير للواجهة/الحُرّاس (نمط main.X)
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,  # noqa: F401 — إعادة تصدير للواجهة/الحُرّاس (نمط main.X)
)
from vegetation_contracts import build_snapshot, derive_lai_from_ndvi, quality_gate

try:
    from shared.logging_config import setup_logging

    logger = setup_logging("vegetation-analysis-service")
except ImportError:
    logging.basicConfig(
        level=logging.INFO, format='{"time":"%(asctime)s","svc":"vegetation","msg":"%(message)s"}'
    )
    logger = logging.getLogger("vegetation-analysis-service")

# ── Config ─────────────────────────────────────────────────────
NATS_URL = os.getenv("NATS_URL", "nats://sahool-nats:4222")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

# تفضيل NDVI الحقيقيّ من raster-service (بكسليّ، Sentinel-2) على التقدير التركيبيّ.
# مُفعَّل افتراضيّاً؛ يبقى مفتاح إيقاف (=0) لأغراض التشغيل. fail-safe بالكامل:
# أيّ تعذّر/مهلة/غياب طبقة ⇒ ارتداد للتقدير المُعلَّم الحاليّ (السلوك لا يسوء أبداً).
RASTER_SERVICE_URL = os.getenv("RASTER_SERVICE_URL", "http://sahool-raster-service:8001").rstrip(
    "/"
)
VEGETATION_PREFER_RASTER = os.getenv("VEGETATION_PREFER_RASTER", "1") not in (
    "0",
    "false",
    "False",
    "",
)
VEGETATION_REAL_ONLY = os.getenv(
    "VEGETATION_REAL_ONLY",
    "1" if os.getenv("SAHOOL_ENV", "development").lower() == "production" else "0",
) not in ("0", "false", "False", "")
VEGETATION_MIN_QUALITY = float(os.getenv("VEGETATION_MIN_QUALITY", "0.55"))

# خريطة مؤشّر vegetation → اسم المؤشّر الحقيقيّ في raster band_math (يُحسب per-pixel
# من Sentinel-2 الحقيقيّ عبر STAC العامّ المجّانيّ — بلا اعتمادات). ما ليس هنا يبقى
# تقديريّاً بصدق: lai (يحتاج نموذجاً)، cwsi (يحتاج نطاقاً حراريّاً LST)، ndwi/gndvi/
# recl (نطاقات/صيَغ خارج band_math). SAVI ⇐ MSAVI2 (نسخة محسّنة، تصحيح تربة ذاتيّ).
_RASTER_REAL_INDEX = {"evi": "evi", "savi": "msavi", "ndmi": "moisture"}

RASTER_SERVICE_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN", "")


# ── مصدر الحقول (Field source) — إغلاق مرن نحو القاعدة ──────────────
# هذه الخدمة لا تملك pool قاعدة (لا asyncpg ولا DATABASE_URL — راجع رأس الملفّ
# واللايف‌سايكل). لذلك «القاعدة» تُقرأ عبر **platform API** (sahool-platform يملك
# جدول fields + RLS + PostGIS؛ راجع GET /api/v1/fields/{id} الذي يُرجِع هندسة
# GeoJSON). نحوّل الهندسة إلى bbox محليّاً (مكافئ ST_Envelope) بصدق — لا نلفّق
# هندسة. كلّ المسار fail-soft خلف علم مُطفأ افتراضيّاً ⇒ السلوك الحاليّ تماماً.
#
# FEATURE_SENTINEL_DB_FIELDS: علم تفعيل قراءة الحقول من القاعدة/المنصّة. off ⇒
#   السجلّ التركيبيّ القديم حصراً (لا تغيير سلوكيّ).
# ALLOW_LEGACY_FIELD_REGISTRY: عند false، فشلُ مصدر القاعدة لا يرتدّ للسجلّ القديم
#   (يُعيد None). الافتراض true ⇒ ارتداد مرن موسوم `legacy_field_registry_used`.
# PLATFORM_API_URL: قاعدة عنوان sahool-platform لقراءة الحقل (إن غاب ⇒ لا منفذ
#   قاعدة، فيرتدّ للسجلّ بحسب ALLOW_LEGACY_FIELD_REGISTRY).
def _flag_enabled(value: str | None, *, default: bool) -> bool:
    """تطبيع علم بيئة منطقيّ (منطق نقيّ قابل للعزل — يُختبَر في الوحدة).

    قيم الإطفاء المتعارَفة: "0"/"false"/"False"/"" ⇒ False. أيّ شيء آخر ⇒ True.
    None (المتغيّر غير مضبوط) ⇒ القيمة الافتراضيّة.
    """
    if value is None:
        return default
    return value not in ("0", "false", "False", "")


PLATFORM_API_URL = os.getenv("PLATFORM_API_URL", "").rstrip("/")
# Runtime field truth is platform-owned. Legacy synthetic field fixtures are disabled
# in every environment; tests must inject fixtures explicitly.
FEATURE_SENTINEL_DB_FIELDS = _flag_enabled(
    os.getenv("FEATURE_SENTINEL_DB_FIELDS"), default=bool(PLATFORM_API_URL)
)
ALLOW_LEGACY_FIELD_REGISTRY = _flag_enabled(os.getenv("ALLOW_LEGACY_FIELD_REGISTRY"), default=False)
# AC-6 evidence producer: push content-addressed vegetation snapshots to the
# decision-service immutable evidence store. Opt-in (default off) and fail-soft:
# the analysis response always reports the push outcome honestly, never hides it.
VEGETATION_EVIDENCE_PUSH_ENABLED = _flag_enabled(
    os.getenv("VEGETATION_EVIDENCE_PUSH_ENABLED"), default=False
)
DECISION_SERVICE_URL = os.getenv(
    # الافتراض يطابق خدمة compose الفعليّة (sahool-decision-service على المنفذ 8160) لا اسماً
    # أو منفذاً وهميّاً — الافتراض الخاطئ سابقاً كان يجعل دفع لقطات النبات يفشل صامتاً عند غياب env.
    "DECISION_SERVICE_URL",
    "http://sahool-decision-service:8160",
).rstrip("/")

security = HTTPBearer(auto_error=False)

# ── تحقّق JWT حقيقيّ (كان يُقبل أيّ Bearer غير فارغ بلا تحقّق توقيع) ──
# RS256 (غير متماثل) لإنهاء shared trust domain: auth يوقّع بمفتاحه الخاصّ والخدمة تتحقّق
# بالمفتاح العامّ (آمن للتوزيع). عند ضبط JWT_PUBLIC_KEY نتحقّق بـRS256؛ وإلّا HS256 (تطوير).
_VEG_JWT_PUBLIC = os.getenv("JWT_PUBLIC_KEY", "").strip()
_VEG_JWT_SECRET = _VEG_JWT_PUBLIC if _VEG_JWT_PUBLIC else os.getenv("JWT_SECRET", "")
_VEG_JWT_ALG = "RS256" if _VEG_JWT_PUBLIC else "HS256"
# المُصدِرون الداخليّون المسموح بهم — يُفرَض بعد فكّ التوكن (تدقيق B: iss لم يُفحَص).
_ALLOWED_ISS = {"sahool-auth", "sahool-platform"}

# تحصين الإنتاج (fail-closed، تماثُل مع auth/المنصّة): RS256 إلزاميّ — HS256 سرّ متماثل
# مشترَك لا يُنهي shared trust domain (أيّ خدمة تحمله تُزوّر توكناً). في الإنتاج بلا
# JWT_PUBLIC_KEY نرفض الإقلاع ما لم يُعطَّل صراحةً (مهرب ترحيل SAHOOL_ALLOW_HS256_IN_PROD=1).
if (
    not _VEG_JWT_PUBLIC
    and os.getenv("SAHOOL_ENV", "development").strip().lower() == "production"
    and os.getenv("SAHOOL_ALLOW_HS256_IN_PROD", "").strip().lower()
    not in {"1", "true", "yes", "on"}
):
    raise RuntimeError(
        "RS256 مطلوب في الإنتاج: اضبط JWT_PUBLIC_KEY (HS256 لا يُنهي shared trust domain). "
        "للترحيل المؤقّت فقط: SAHOOL_ALLOW_HS256_IN_PROD=1."
    )
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _verify_claims(token) -> dict:
    """يتحقّق من توقيع JWT وaudience، ويُرجِع المطالبات. fail-closed."""
    if not token or not token.credentials:
        raise HTTPException(401, "Authentication required")
    if not _VEG_JWT_SECRET or len(_VEG_JWT_SECRET) < 32:
        raise HTTPException(503, "JWT_SECRET غير مضبوط")
    try:
        payload = _jwt.decode(
            token.credentials, _VEG_JWT_SECRET, algorithms=[_VEG_JWT_ALG], audience="sahool"
        )
    except Exception:
        raise HTTPException(401, "توكن غير صالح") from None
    # تدقيق B: افرض المُصدِر بعد فكّ ناجح — مُصدِر مجهول ⇒ 401 كتوكن غير صالح.
    if payload.get("iss") not in _ALLOWED_ISS:
        raise HTTPException(401, "مُصدِر التوكن غير مسموح")
    return payload


def _tenant_from_claims(claims: dict) -> str:
    """المستأجِر من التوكن لا من العميل — يمنع حقن موضوع NATS عابر المستأجرين."""
    tid = str(claims.get("tenant_id") or "")
    if not tid:
        raise HTTPException(401, "توكن بلا مستأجِر")
    return tid


def _valid_date(s: str) -> str:
    """يتحقّق أنّ التاريخ بصيغة YYYY-MM-DD — يمنع حقن OData/الاستعلام المتسلسل."""
    if not _ISO_DATE_RE.match(s):
        raise HTTPException(400, "صيغة تاريخ غير صالحة (YYYY-MM-DD)")
    return s


# ── Prometheus (FIXED: removed field_id label to prevent cardinality explosion) ──
def _safe_metric(factory, *args, **kwargs):
    """مقياس Prometheus آمن عند إعادة الاستيراد: الاختبارات تُحمّل هذه الوحدة عبر
    exec_module أكثر من مرّة، فالتسجيل المكرّر في السجلّ الافتراضيّ العالميّ يرمي
    ValueError. عندها نُنشئ المقياس في سجلّ خاصّ معزول كي تبقى الوحدة قابلة للتحميل
    (الإنتاج يُحمّلها مرّة واحدة فتُسجَّل عادةً في السجلّ الافتراضيّ)."""
    try:
        return factory(*args, **kwargs)
    except ValueError:
        return factory(*args, registry=CollectorRegistry(), **kwargs)


ANALYSIS_COUNT = _safe_metric(
    Counter,
    "sahool_vegetation_analysis_total",
    "Vegetation analysis requests",
    ["source", "status"],
)
ANALYSIS_LATENCY = _safe_metric(
    Histogram,
    "sahool_vegetation_analysis_duration_seconds",
    "Vegetation analysis duration",
    ["source"],
)

# ── Field geometry registry ────────────────────────────────────
FIELD_REGISTRY: dict[str, dict] = {}


# ── مُحمِّل الحقول المرن (graceful field loader) ─────────────────────
def select_field_source(
    *,
    feature_db: bool,
    allow_legacy: bool,
    db_available: bool,
) -> str:
    """يختار مصدر الحقل (منطق نقيّ قابل للعزل — يُختبَر في الوحدة).

    يُرجِع أحد: "db" (اقرأ من القاعدة/المنصّة)، "legacy" (السجلّ التركيبيّ مع وسم
    صدق)، أو "none" (لا مصدر — العلم يمنع السجلّ القديم وفشل القاعدة).

    القرار لا يعتمد على I/O؛ `db_available` يُمرَّر من المتّصِل بعد محاولة القراءة.
      - العلم مُطفأ ⇒ السجلّ القديم دائماً (السلوك الحاليّ تماماً).
      - العلم مُفعَّل + قراءة قاعدة ناجحة ⇒ "db".
      - العلم مُفعَّل + فشل قاعدة + ارتداد مسموح ⇒ "legacy".
      - العلم مُفعَّل + فشل قاعدة + ارتداد ممنوع ⇒ "none".
    """
    if not feature_db:
        return "legacy"
    if db_available:
        return "db"
    return "legacy" if allow_legacy else "none"


def _geometry_to_bbox(geometry: dict | None) -> list[float] | None:
    """GeoJSON Polygon/MultiPolygon ⇒ bbox [minx, miny, maxx, maxy] (مكافئ
    ST_Envelope محليّاً). صدق: لا تلفيق — يُرجِع None لو الهندسة غائبة/غير صالحة.
    """
    if not isinstance(geometry, dict):
        return None
    coords = geometry.get("coordinates")
    if not coords:
        return None
    xs: list[float] = []
    ys: list[float] = []

    def _walk(node) -> None:
        # ورقة الإحداثيّة [x, y, ...] أو قائمة متداخلة.
        if (
            isinstance(node, (list, tuple))
            and len(node) >= 2
            and all(isinstance(v, (int, float)) for v in node[:2])
        ):
            xs.append(float(node[0]))
            ys.append(float(node[1]))
            return
        if isinstance(node, (list, tuple)):
            for child in node:
                _walk(child)

    _walk(coords)
    if not xs or not ys:
        return None
    return [min(xs), min(ys), max(xs), max(ys)]


async def _load_field_from_db(field_id: str, tenant_id: str | None = None) -> dict | None:
    """يقرأ الحقل من «القاعدة» عبر platform API (sahool-platform يملك fields + RLS
    + PostGIS). يُحوّل هندسة GeoJSON ⇒ bbox (مكافئ ST_Envelope) بصدق.

    قيد معماريّ صريح: هذه الخدمة بلا pool قاعدة خاصّ بها (لا asyncpg/DATABASE_URL)،
    فالعزل عبر المستأجِر (RLS / set app.current_tenant) يُفرَض في **المنصّة** خلف
    GET /api/v1/fields/{id} (مُرشَّح بالمستأجِر هناك). نمرّر المستأجِر ترويسةً
    إرشاديّة. لو غاب PLATFORM_API_URL ⇒ لا منفذ قاعدة (None، fail-soft).

    fail-soft مطلق: أيّ تعذّر/مهلة/هندسة غير صالحة ⇒ None (يقرّر المتّصِل الارتداد).
    """
    if not PLATFORM_API_URL or not RASTER_SERVICE_TOKEN:
        return None
    headers = {
        "Accept": "application/json",
        "X-Agent-Token": RASTER_SERVICE_TOKEN,
    }
    if tenant_id:
        headers["X-Tenant-Id"] = str(tenant_id)
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"{PLATFORM_API_URL}/api/v1/fields/{field_id}", headers=headers)
        if r.status_code != 200:
            return None
        data = r.json()
    except Exception as e:  # noqa: BLE001 — fail-soft: ارتداد، لا كسر
        logger.debug("platform field load فشل لـ%s: %s", field_id, e)
        return None
    bbox = _geometry_to_bbox(data.get("geometry"))
    if bbox is None:
        return None
    return {
        "name": data.get("name") or field_id,
        "bbox": bbox,
        "area_ha": data.get("area_ha"),
        "crop": data.get("crop") or data.get("crop_type"),
        "soil": data.get("soil") or data.get("soil_type"),
        "source": "platform-db",
    }


async def list_fields_from_platform(tenant_id: str) -> list[dict]:
    """Return the tenant-scoped field catalog from sahool-platform.

    No local enumeration fallback is permitted. The service token authenticates
    the internal caller while X-Tenant-Id scopes the platform query.
    """
    if not PLATFORM_API_URL or not RASTER_SERVICE_TOKEN:
        raise HTTPException(503, "platform field catalog is not configured")
    headers = {
        "Accept": "application/json",
        "X-Agent-Token": RASTER_SERVICE_TOKEN,
        "X-Tenant-Id": str(tenant_id),
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{PLATFORM_API_URL}/api/v1/fields", headers=headers)
    except Exception as exc:  # noqa: BLE001
        logger.warning("platform field list unavailable tenant=%s: %s", tenant_id, exc)
        raise HTTPException(503, "platform field catalog unavailable") from None
    if response.status_code != 200:
        raise HTTPException(503, f"platform field catalog returned {response.status_code}")
    payload = response.json()
    if isinstance(payload, dict):
        items = payload.get("fields") or payload.get("items") or payload.get("data") or []
    elif isinstance(payload, list):
        items = payload
    else:
        items = []
    return [item for item in items if isinstance(item, dict)]


async def load_field(field_id: str, tenant_id: str | None = None) -> dict | None:
    """مُحمِّل الحقول المرن (الإغلاق المرن — لا كسر).

    خلف FEATURE_SENTINEL_DB_FIELDS (مُطفأ افتراضيّاً) يحاول قراءة الحقل من القاعدة/
    المنصّة؛ وإلّا — أو عند الفشل المسموح بارتداده — يرتدّ للسجلّ التركيبيّ القديم
    مع وسم صدق `legacy_field_registry_used`. لا يرفع استثناءً على مسار القراءة.

    ملاحظة صدق: السجلّ القديم تقدير تركيبيّ (synthetic)، لا هندسة per-pixel حقيقيّة.
    """
    db_field: dict | None = None
    if FEATURE_SENTINEL_DB_FIELDS:
        try:
            db_field = await _load_field_from_db(field_id, tenant_id)
        except Exception as e:  # noqa: BLE001 — fail-soft شامل
            logger.warning("db_field_load_error field_id=%s err=%s", field_id, e)
            db_field = None

    source = select_field_source(
        feature_db=FEATURE_SENTINEL_DB_FIELDS,
        allow_legacy=ALLOW_LEGACY_FIELD_REGISTRY,
        db_available=db_field is not None,
    )
    if source == "db":
        return db_field
    if source == "none":
        # العلم يمنع السجلّ القديم وفشلت القاعدة ⇒ لا مصدر (لا ارتداد تركيبيّ).
        logger.warning("field_source_unavailable field_id=%s (legacy disabled)", field_id)
        return None
    # Runtime paths never return synthetic field metadata. Compatibility flag is
    # retained only so stale deployments fail visibly instead of fabricating data.
    logger.error("legacy_field_registry_forbidden field_id=%s", field_id)
    return None


# Provider credentials and direct provider access were removed by RIV ownership consolidation.
# vegetation-analysis-service consumes only validated raster-service products.


def _derive_water_stress_from_observed(indices: dict[str, float]) -> float:
    """Interpret observed NDMI/MSI without recomputing spectral indices."""
    ndmi = indices.get("ndmi")
    msi = indices.get("msi")
    components: list[float] = []
    if ndmi is not None:
        components.append(max(0.0, min(1.0, (0.4 - float(ndmi)) / 0.8)))
    if msi is not None:
        components.append(max(0.0, min(1.0, (float(msi) - 0.4) / 1.6)))
    return round(sum(components) / len(components), 3) if components else 0.5


def _health_classification(ndvi: float, cwsi: float) -> dict:
    if ndvi >= 0.72 and cwsi < 0.3:
        return {"status": "excellent", "label_ar": "ممتاز", "color": "#16a34a", "score": 95}
    elif ndvi >= 0.55 and cwsi < 0.5:
        return {"status": "good", "label_ar": "جيد", "color": "#65a30d", "score": 75}
    elif ndvi >= 0.38 and cwsi < 0.7:
        return {"status": "fair", "label_ar": "مقبول", "color": "#ca8a04", "score": 55}
    elif ndvi >= 0.20:
        return {"status": "poor", "label_ar": "منخفض", "color": "#f97316", "score": 35}
    else:
        return {"status": "critical", "label_ar": "حرج", "color": "#dc2626", "score": 10}


def _recommendations_ar(indices: dict, health: dict, crop: str) -> list[str]:
    """فرضيّات واقتراحات فحص (V4) — لا توصيات تنفيذيّة.

    صدق حدود المحرّكات: Vegetation يُنتج **فرضيّات/اقتراحات فحص** مبنيّة على مؤشّرات
    تقديريّة، لا أوامر تنفيذيّة («اروِ 30مم»/«رشّ X») — تلك لخدمة القرار (Decision).
    كانت سابقاً تقول «يُنصح بالري الفوري» مبنيّةً على CWSI **تقديريّ** ⇒ خطر مضاعف.
    نُبقي الكلمات المفتاحيّة (ريّ/آفة/مرض) كي لا نكسر مستهلكاً، لكن بصيغة فرضيّة.
    """
    recs = []
    ndvi = indices["ndvi"]
    cwsi = float(indices.get("water_stress", 0.5))
    ndwi = indices.get("ndwi")
    recl = indices.get("recl")
    if cwsi > 0.6:
        recs.append(
            f"⚠️ فرضيّة: إجهاد مائي حاد محتمل (water-stress≈{cwsi:.2f}، مشتقّ من NDMI/MSI المرصود) — "
            "يوصى بالتحقّق الميدانيّ؛ قرار الريّ لخدمة القرار."
        )
    elif cwsi > 0.35:
        recs.append(
            f"💧 فرضيّة: إجهاد مائي متوسّط محتمل (water-stress≈{cwsi:.2f}، مشتقّ من NDMI/MSI المرصود) — راقب؛ القرار التنفيذي لخدمة القرار."
        )
    if recl is not None and recl < 1.5:
        recs.append(
            f"🌱 فرضيّة: نقص كلوروفيل محتمل (RECl≈{recl:.2f}، تقديريّ) — يوصى بفحص النيتروجين."
        )
    if ndvi < 0.40:
        recs.append(f"📉 فرضيّة: انخفاض NDVI ({ndvi}) — احتمال آفة أو مرض؛ يوصى بالفحص الميدانيّ.")
    if ndwi is not None and ndwi < -0.1:
        recs.append(f"🏜️ فرضيّة: جفاف محتمل (NDWI≈{ndwi:.2f}، مرصود) — يوصى بالتحقّق قبل قرار الريّ.")
    if not recs:
        recs.append("✅ لا إشارات إجهاد واضحة في التقديرات الحاليّة — يوصى بالمتابعة الاعتياديّة.")
    return recs


_nc = None


async def _publish_analysis(field_id: str, tenant_id: str, indices: dict, source: str):
    global _nc
    try:
        if _nc is None:
            import nats

            _nc = await nats.connect(NATS_URL)
        subject = f"sahool.tenant.{tenant_id}.satellite.{field_id}.computed"
        payload = json.dumps(
            {
                "field_id": field_id,
                "tenant_id": tenant_id,
                "source": source,
                "timestamp": datetime.now(UTC).isoformat(),
                "event_type": "satellite",
                # عنوان عرضيّ فقط — يبقى على اسم السجلّ التركيبيّ (لا حِمل قراءة
                # قاعدة إضافيّ على مسار النشر؛ غير حسّاس وموثَّق).
                "title": f"🛰️ صورة جديدة — {field_id}",
                "message": f"NDVI={indices.get('ndvi')} | EVI={indices.get('evi')}",
                **indices,
            },
            ensure_ascii=False,
        ).encode()
        js = _nc.jetstream()
        await js.publish(subject, payload)
        logger.info(f"NATS published: {subject}")
    except Exception as e:
        logger.warning(f"NATS publish failed: {e}")


async def _real_observation_bundle_from_raster(
    field_id: str, tenant_id: str, raster_indices: list[str]
) -> dict | None:
    """Read one validated, tenant-scoped observation bundle from raster-service."""
    if not VEGETATION_PREFER_RASTER or not RASTER_SERVICE_TOKEN:
        return None
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.get(
                f"{RASTER_SERVICE_URL}/v1/fields/{field_id}/indicator-observation-bundle",
                params={"indices": ",".join(raster_indices), "date": "latest", "grid": 16},
                headers={
                    "X-Tenant-Id": str(tenant_id),
                    "X-Agent-Token": RASTER_SERVICE_TOKEN,
                },
            )
        if r.status_code != 200:
            return None
        data = r.json()
        if (
            not data.get("real_data")
            or data.get("mixed_scene")
            or not data.get("bundle_consistency")
        ):
            return None
        return data
    except Exception as exc:  # noqa: BLE001 - fail closed to unavailable observation
        logger.debug("raster observation bundle unavailable field=%s: %s", field_id, exc)
        return None


async def _push_vegetation_evidence(snapshot: dict, tenant_id: str) -> dict:
    """Push one immutable snapshot to decision-service /v1/evidence/vegetation-snapshots.

    The snapshot_hash IS the idempotency key (content-addressed on the decision side:
    a replay returns the canonical existing snapshot). Fail-soft by design — an
    unreachable/mirror-mode (503) decision-service must never break the analysis —
    but the outcome is always reported, never silent.
    """
    tenant = str(tenant_id or "").strip()
    try:
        UUID(tenant)
    except (ValueError, TypeError):
        # the decision evidence store is tenant-uuid scoped; enumeration/dev tenants
        # ("default", ...) are honestly skipped rather than coerced.
        return {"pushed": False, "reason": "tenant_not_uuid"}
    acq = snapshot.get("acquisition_date")
    body = {
        "field_id": snapshot["field_id"],
        "season_id": snapshot.get("season_id"),
        "contract_version": snapshot.get("contract_version", "vegetation-snapshot.v2"),
        "snapshot_hash": snapshot["snapshot_hash"],
        "acquisition_at": f"{acq}T00:00:00Z" if acq and "T" not in str(acq) else acq,
        "data_available_at": snapshot["data_available_at"],
        "quality_gate": snapshot["quality_gate"],
        "feature_manifest": snapshot.get("feature_manifest", {}),
        "payload": {"indices": snapshot["indices"], "source": snapshot["source"]},
    }
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{DECISION_SERVICE_URL}/v1/evidence/vegetation-snapshots",
                json=body,
                headers={"X-Tenant-Id": tenant},
            )
        if r.status_code == 200:
            data = r.json()
            return {
                "pushed": True,
                "snapshot_id": data.get("snapshot_id"),
                "created": data.get("created"),
            }
        return {"pushed": False, "reason": f"http_{r.status_code}"}
    except Exception as exc:  # noqa: BLE001 - fail-soft: الدليل يُدفَع لاحقاً، التحليل لا يُكسَر
        logger.warning("vegetation evidence push failed for %s: %s", snapshot["field_id"], exc)
        return {"pushed": False, "reason": f"unreachable:{type(exc).__name__}"}


async def run_analysis(
    field_id: str, tenant_id: str, date_from: str, date_to: str, season_id: str | None = None
) -> dict:
    field = await load_field(field_id, tenant_id)
    if not field:
        raise HTTPException(404, f"field_id {field_id!r} غير موجود")
    with ANALYSIS_LATENCY.labels(source="total").time():
        # RIV: Vegetation consumes only validated products from raster-service.
        # No provider access, synthetic bands, or spectral formulas live here.
        source = "raster-service"
        provider_reachable = False
        cloud_pct = None
        indices: dict[str, float] = {}
        index_sources: dict[str, str] = {}
        index_quality: dict[str, dict] = {}
        requested = ["ndvi", "evi", "savi", "ndmi", "msi", "ndwi", "gndvi"]
        raster_names = ["ndvi", "evi", "msavi", "moisture", "msi", "ndwi", "gndvi"]
        bundle = await _real_observation_bundle_from_raster(field_id, tenant_id, raster_names)
        if bundle is None:
            raise HTTPException(424, "consistent validated raster observation bundle is required")
        acquisition_dates: list[str] = list(bundle.get("acquisition_dates") or [])
        bundle_observations = bundle.get("observations") or {}
        for public_name, raster_name in zip(requested, raster_names, strict=True):
            raw = bundle_observations.get(raster_name)
            if not raw:
                continue
            product = raw.get("indicator_product") or {}
            mean = (raw.get("stats") or {}).get("mean")
            if not isinstance(mean, (int, float)):
                continue
            indices[public_name] = round(float(mean), 3)
            index_sources[public_name] = "raster-service"
            valid = product.get("valid_pixel_ratio")
            provenance = product.get("provenance") or {}
            index_quality[public_name] = {
                "quality_score": product.get("quality_score"),
                "valid_pixel_ratio": valid,
                "valid_pixel_pct": round(float(valid) * 100.0, 3) if valid is not None else None,
                "provenance": provenance,
                "data_available_at": product.get("data_available_at") or product.get("created_at"),
            }
        if "ndvi" not in indices:
            raise HTTPException(424, "validated real NDVI is required from raster-service")
        acq_date = max(acquisition_dates) if acquisition_dates else date_to
        lai = derive_lai_from_ndvi(indices["ndvi"])
        indices["lai"] = lai["value"]
        index_sources["lai"] = "vegetation-model"
        index_quality["lai"] = {
            "quality_score": index_quality.get("ndvi", {}).get("quality_score"),
            "provenance": {"algorithm": lai["algorithm"], "input": "ndvi"},
            "uncertainty": lai["uncertainty"],
        }
        indices["water_stress"] = _derive_water_stress_from_observed(indices)
        index_sources["water_stress"] = "vegetation-interpretation"
        index_quality["water_stress"] = {
            "quality_score": min(
                [
                    q.get("quality_score")
                    for k, q in index_quality.items()
                    if k in {"ndmi", "msi"} and q.get("quality_score") is not None
                ]
                or [index_quality.get("ndvi", {}).get("quality_score")]
            ),
            "provenance": {
                "algorithm": "observed-water-stress.v1",
                "inputs": [k for k in ("ndmi", "msi") if k in indices],
            },
        }
        health = _health_classification(indices["ndvi"], indices["water_stress"])
        recs = _recommendations_ar(indices, health, field.get("crop") or "wheat")
    await _publish_analysis(field_id, tenant_id, indices, source)
    ANALYSIS_COUNT.labels(source=source, status="success").inc()
    # وسم مصدر كلّ مؤشّر بصدق من index_sources: الحقيقيّ (raster) عند توفّره، وإلّا تقدير.
    index_contract = {
        k: {
            "value": v,
            "unit": "dimensionless" if k != "lai" else "m2/m2",
            "source": index_sources.get(k, "estimate"),
            "estimated": index_sources.get(k, "estimate") != "raster-service",
            **(
                {
                    "quality_score": index_quality[k].get("quality_score"),
                    "valid_pixel_pct": index_quality[k].get("valid_pixel_pct"),
                    "provenance": index_quality[k].get("provenance"),
                    "data_available_at": index_quality[k].get("data_available_at"),
                    **(
                        {"uncertainty": index_quality[k].get("uncertainty")}
                        if index_quality[k].get("uncertainty") is not None
                        else {}
                    ),
                }
                if k in index_quality
                else {}
            ),
        }
        for k, v in indices.items()
    }
    gate = quality_gate(index_contract, min_quality=VEGETATION_MIN_QUALITY)
    if VEGETATION_REAL_ONLY and not gate["executable"]:
        raise HTTPException(424, "validated real NDVI is required in production vegetation mode")
    snapshot = build_snapshot(
        field_id=field_id,
        tenant_id=tenant_id,
        season_id=season_id,
        acquisition_date=acq_date,
        indices=index_contract,
        source="raster-service",
        quality=gate,
        data_available_at=(index_quality.get("ndvi") or {}).get("data_available_at"),
    )
    evidence_push = (
        await _push_vegetation_evidence(snapshot, tenant_id)
        if VEGETATION_EVIDENCE_PUSH_ENABLED
        else {"pushed": False, "reason": "disabled"}
    )
    return {
        "field_id": field_id,
        "field_name": field.get("name") or field_id,
        "crop": field.get("crop"),
        "area_ha": field.get("area_ha"),
        "tenant_id": tenant_id,
        # V5: سياق الموسم يُمرَّر ويُصدَّر للنَّسَب (تفسير المؤشّر حسب المرحلة/الموسم
        # يتمّ في المنصّة؛ هنا نحمله كي لا يُفقَد ويربط النتيجة بالموسم الصحيح).
        "season_id": season_id,
        "acquisition_date": acq_date,
        "cloud_coverage_pct": cloud_pct,
        # data_source يعكس مصدر NDVI (الرقم الرئيسيّ): raster الحقيقيّ أو التقدير.
        "data_source": "raster-service",
        # real_data يعكس NDVI تحديداً (بطاقة الصحّة تُبنى عليه): حقيقيّ من raster؟
        "real_data": True,
        "provider_reachable": provider_reachable,
        # نصّ آليّ موحّد اللغة (إنجليزيّ) في الحالتين — لا تتغيّر لغته بتغيّر المصدر
        # (تفادياً لكسر مستهلكين يطابقون النصّ، كما نبّهت مراجعة Copilot).
        "estimate_note": (
            "Validated per-pixel means from raster-service. LAI and water_stress are interpretation products with explicit provenance."
        ),
        "indices": index_contract,
        "quality_gate": gate,
        "vegetation_snapshot": snapshot,
        "evidence_push": evidence_push,
        "raw_bands": None,
        "health": health,
        "recommendations_ar": recs,
        # V4: هذه فرضيّات/اقتراحات فحص لا أوامر تنفيذيّة — القرارات (ريّ/رشّ/تسميد)
        # لخدمة القرار. مبنيّة على مؤشّرات تقديريّة ما لم يُوسَم مصدرها raster-service.
        "advisory_role": "hypothesis",
        "advisory_note_ar": (
            "فرضيّات واقتراحات فحص مبنيّة على مؤشّرات تقديريّة؛ القرارات التنفيذيّة لخدمة القرار."
        ),
        "analyzed_at": datetime.now(UTC).isoformat(),
        "satellite": "Sentinel-2 L2A",
        "resolution_m": 10,
    }


async def _real_timeseries_from_raster(field_id: str, index: str, days: int) -> dict | None:
    """Read the authoritative per-field series from raster-service; never invent points."""
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                f"{RASTER_SERVICE_URL}/v1/fields/{field_id}/timeseries", params={"index": index}
            )
        if r.status_code != 200:
            return None
        data = r.json()
        if not data.get("available") or not data.get("real_data"):
            return None
        points = list(data.get("points") or [])
        cutoff = date.today() - timedelta(days=days)
        points = [p for p in points if str(p.get("datetime", ""))[:10] >= cutoff.isoformat()]
        return {**data, "points": points}
    except Exception as exc:  # noqa: BLE001
        logger.warning("real vegetation timeseries unavailable for %s: %s", field_id, exc)
        return None


async def _current_ndvi_from_raster(field_id: str, days: int = 45) -> dict | None:
    """أحدث مشاهدة NDVI موثّقة من raster-service — أو None بصدق.

    المشاهدة يجب أن تحمل نَسَب بيانات حقيقيّة (مشهد + زمن). لا تُبنى أيّ قيمة
    تركيبيّة/تقديريّة عند غياب بيانات raster (استُبدل بها المولِّد التركيبيّ المحذوف).
    """
    data = await _real_timeseries_from_raster(field_id, "ndvi", days)
    if not data:
        return None
    points = [p for p in (data.get("points") or []) if isinstance(p, dict)]
    if not points:
        return None
    points.sort(key=lambda p: str(p.get("datetime") or p.get("date") or ""))
    point = points[-1]
    value = point.get("value", point.get("ndvi"))
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    observed_at = point.get("datetime") or point.get("date")
    scene_id = point.get("scene_id") or point.get("asset_id")
    if not observed_at or not scene_id:
        return None
    return {
        "value": value,
        "observed_at": observed_at,
        "scene_id": scene_id,
        "data_available_at": point.get("data_available_at") or data.get("generated_at"),
        "quality_score": point.get("quality_score"),
        "valid_pixel_pct": point.get("valid_pixel_pct"),
        "algorithm_version": point.get("algorithm_version") or data.get("algorithm_version"),
        "qa_mask_version": point.get("qa_mask_version") or data.get("qa_mask_version"),
        "source": "raster-service",
        "real_data": True,
    }


def _current_ndvi_payload(field_id: str, field: dict, analysis: dict) -> dict:
    """يشكّل ردّ NDVI الحالي من ناتج التحليل — دالّة نقيّة (لا قاعدة/شبكة).

    الواجهة (useCurrentNDVI) تتوقّع `ndvi.current` + تصنيف صحّي. نستخرجهما من
    مؤشّرات التحليل (indices[*].value) دون تكرار منطق الحساب. real_data يُمرَّر
    كما هو من التحليل (دائماً False في هذه الخدمة — تقدير لا بكسلات حقيقيّة).
    """
    indices = analysis.get("indices", {})
    ndvi_val = indices.get("ndvi", {}).get("value")
    return {
        "field_id": field_id,
        "field_name": field.get("name"),
        "crop": field.get("crop"),
        "ndvi": {"current": ndvi_val},
        "classification": analysis.get("health", {}),
        "acquisition_date": analysis.get("acquisition_date"),
        "data_source": analysis.get("data_source"),
        "real_data": analysis.get("real_data", False),
        "provider_reachable": analysis.get("provider_reachable", False),
    }
