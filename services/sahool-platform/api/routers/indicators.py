"""api/routers/indicators.py — المؤشّرات ولوحاتها (Indicators)
===========================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات/النماذج/المساعِدات) تبقى مُعرَّفة في ``api.main``
وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات الاختبارات.
لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط (بعد
تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

import os
from typing import Any, Literal
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from api.analytics_shapers import (
    _shape_indicator_catalog,
    _shape_indicators_dashboard,
    _shape_map_layers,
)
from api.main import (
    Permission,
    UserSchema,
    _assert_field_in_tenant,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

router = APIRouter()


@router.get("/api/v1/indicators/catalog")
async def indicators_catalog(
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """كتالوج المؤشّرات المُنفَّذة فعلاً + مصادرها (بديل indicators-service الـstub).

    ثابت (لا قاعدة) لكنّه صادق: يصف ما تحسبه المنصّة حقّاً عبر خدماتها، لا ٣٣
    مؤشّراً وهميّاً. مُقيَّد بالدور (FIELD_VIEW) للاتّساق مع بقيّة لوحات الحقل.
    """
    return _shape_indicator_catalog()


@router.get("/api/v1/indicators/map-layers")
async def indicators_map_layers(
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """كتالوج طبقات الخريطة — المؤشّرات القابلة للرسم (renderable) فقط + band_math.

    مشتقّ من كتالوج المؤشّرات نفسه (مصدر حقيقة واحد): يقود مبدّل طبقات الخريطة في
    الواجهة بدل قائمة مُبرمَجة. كلّ طبقة تخدمها raster-service كبلاطات band_math
    (تعبير Sentinel-2 قياسيّ). ثابت (لا قاعدة)، مُقيَّد بـFIELD_VIEW كبقيّة اللوحات.
    """
    return _shape_map_layers()


@router.get("/api/v1/indicators/dashboard")
async def indicators_dashboard(
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """لوحة المؤشّرات المُجمَّعة للمستأجِر — عدّادات + تنبيهات + ملخّص الحقول.

    تجميع حيّ من fields/seasons/alerts (RLS + tenant_id). لا قيم NDVI/طقس مُلفَّقة:
    المؤشّرات الطيفيّة لكلّ حقل تُجلب من vegetation/raster في شاشة الأقمار. 503 عند
    تعذّر القاعدة — لا أرقام مخترعة.
    """
    try:
        async with tenant_connection(user) as conn:
            tid = str(user.tenant_id)
            fields_rows = await conn.fetch(
                "SELECT field_id, name, crop, area_ha, geometry FROM fields "
                "WHERE tenant_id = $1::uuid ORDER BY name",
                tid,
            )
            active_season_rows = await conn.fetch(
                "SELECT DISTINCT field_id FROM seasons "
                "WHERE tenant_id = $1::uuid AND status = 'active'",
                tid,
            )
            alert_rows = await conn.fetch(
                "SELECT alert_id, field_id, alert_type, severity, title_ar, "
                "message_ar, status, created_at FROM alerts "
                "WHERE tenant_id = $1::uuid AND status = 'active' "
                "ORDER BY created_at DESC LIMIT 50",
                tid,
            )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("قراءة لوحة المؤشّرات", e) from e
    active_field_ids = {r["field_id"] for r in active_season_rows}
    return _shape_indicators_dashboard(
        fields_rows=fields_rows,
        active_field_ids=active_field_ids,
        alert_rows=alert_rows,
    )


# ── المشاهدات القانونيّة لكلّ حقل (M4، مراجعة v25) ─────────────────────────────
#
# **الفجوة:** indicators-service يُعرّف ``/v1/fields/{field_id}/observations`` و
# ``/v1/fields/{field_id}/observation-timeline`` (محوّلُ المشاهدة القانونيّة فوق
# raster-service)، والمنصّة لم تكشف منهما شيئاً — فلا تبلغهما الواجهةُ إلّا عبر خدماتٍ
# داخليّة (vegetation-analysis · remote-sensing-workspace-bff).
#
# **مسارٌ واحدٌ لا اثنان:** راتشِت ميزانية النطاق كان عند 628/629. فيُكشَف الاثنان
# خلف ``{view}`` مغلقٍ بـ``Literal`` — قيمةٌ خارجه تُرفَض 422 من التحقّق **قبل** أيّ
# نداء، فلا يصير المسارُ وكيلاً عامّاً لمسارات الخدمة.
#
# **الترتيب مقصود:** ملكيّةُ الحقل تُفحَص أوّلاً (``_assert_field_in_tenant`` داخل
# ``tenant_connection`` ⇒ 404 لحقل مستأجِرٍ آخر، كبقيّة مسارات الحقل)، ثمّ النداء.
# والمستأجِرُ يُحقَن من المستخدم الموثَّق وحده — ترويسةُ العميل لا تُمرَّر أصلاً.
IndicatorObservationView = Literal["observations", "observation-timeline"]

# مسارا الخدمة ثابتان على مستوى الوحدة — فيقرؤهما ``cross_service_path_contract_guard``
# ويقابلهما بإعلان indicators-service (انحرافُ سلسلةٍ هنا ⇒ ٤٠٤ حتميّ يحمرّ في CI).
INDICATORS_OBSERVATIONS_PATH = "/v1/fields/{field_id}/observations"
INDICATORS_OBSERVATION_TIMELINE_PATH = "/v1/fields/{field_id}/observation-timeline"
_VIEW_PATHS: dict[str, str] = {
    "observations": INDICATORS_OBSERVATIONS_PATH,
    "observation-timeline": INDICATORS_OBSERVATION_TIMELINE_PATH,
}

DEFAULT_INDICATORS_SERVICE_URL = "http://sahool-indicators-service:8000"
_INDICATORS_TIMEOUT_S = 15.0  # مطابقٌ لـ``raster_get_json`` (القارئ الذي تنادي الخدمةُ خلفه)


def indicators_service_url() -> str:
    return os.getenv("INDICATORS_SERVICE_URL", DEFAULT_INDICATORS_SERVICE_URL).rstrip("/")


def _upstream_detail(resp: httpx.Response) -> Any:
    try:
        body = resp.json()
    except ValueError:  # قد لا يكون الردّ JSON
        return resp.text or "indicators-service returned an error"
    return body.get("detail", body) if isinstance(body, dict) else body


async def _indicators_get_json(
    path: str, *, tenant_id: str, params: dict[str, str]
) -> dict[str, Any]:
    """GET من indicators-service بنمط ``raster_service_client``: ``HTTPError`` ⇒ 502،
    وردٌّ ≥400 يُمرَّر برمزه وتفصيله (424 «لا مشاهدة حقيقيّة» يبقى 424 لا يُلفَّق)."""
    url = f"{indicators_service_url()}/{path.lstrip('/')}"
    try:
        async with httpx.AsyncClient(timeout=_INDICATORS_TIMEOUT_S) as client:
            resp = await client.get(url, params=params, headers={"X-Tenant-Id": tenant_id})
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"indicators-service غير متاح: {type(exc).__name__}"
        ) from exc
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=_upstream_detail(resp))
    data = resp.json()
    return data if isinstance(data, dict) else {"value": data}


@router.get("/api/v1/fields/{field_id}/indicator-observations/{view}")
async def field_indicator_observations(
    field_id: str,
    view: IndicatorObservationView,
    season_id: str = Query(..., min_length=1),
    indicators: str = Query("ndvi"),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """المشاهدات القانونيّة للحقل (``observations``) أو خطّها الزمنيّ
    (``observation-timeline``) من indicators-service — كما هي، بلا بدائل.

    المعاملات هي ما تقبله الخدمة حرفيّاً (``season_id`` إلزاميّ، ``indicators``
    قائمةٌ مفصولةٌ بفواصل، افتراضها ``ndvi``). غيابُ مشاهدةٍ حقيقيّة ⇒ 424 الخدمة نفسه.
    """
    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — أيّ خطأ DB ⇒ 503 موثَّق لا 500
        raise _db_unavailable("التحقّق من ملكيّة الحقل للمشاهدات", e) from e
    return await _indicators_get_json(
        # الملكيّةُ فُحِصت أعلاه؛ والترميزُ يمنع مع ذلك أن يصير المعرّفُ مقطعَ مسارٍ آخر.
        _VIEW_PATHS[view].format(field_id=quote(field_id, safe="")),
        tenant_id=str(user.tenant_id),
        params={"season_id": season_id, "indicators": indicators},
    )
