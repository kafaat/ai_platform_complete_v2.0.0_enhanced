"""Resolve the canonical spectral state product for a field, server-side.

Peer of ``api/canonical_water_state.py`` and ``api/canonical_soil_state.py``: it answers
*"what does the platform actually know about this field's spectral indices right now"*
and returns either a canonical product or ``None``. It never computes a raster index and
never synthesizes a value to satisfy a contract.

**Why this module exists (P0-2, spectral half).** ``routers/internal_service.py`` composed
``canonical_field_state`` with ``spectral=None`` hard-coded, while a producer
(``core.crop_intelligence.build_canonical_spectral_state``) and a server-side resolver both
already existed — the latter living inside ``routers/crop_twin.py``, reachable only from
that router. So the composed canonical state declared ``spectral_missing`` for fields whose
indices the platform could read. The resolver moved here so both consumers share one
implementation rather than one of them owning it privately.

``ndvi`` is the master index: without it there is no server authority and the answer is
``None``. A product with every index ``None`` would be worse than absence — it would set
``availability.spectral = True`` while nothing is known, which is exactly the fabrication
``core/canonical_field_state.py`` exists to prevent.
"""

from __future__ import annotations

import asyncio
from typing import Any

from core.crop_intelligence import build_canonical_spectral_state

# المؤشّرات القانونيّة المُشتقّة خادميّاً (NDVI سيّد؛ إن غاب ⇒ لا سلطة خادميّة).
SERVER_SPECTRAL_INDICES = ("ndvi", "ndre", "ndmi", "msi")


async def _resolve_server_spectral(field_id: str, tenant_id: str | None) -> dict | None:
    """يجلب مؤشّرات الطيف القانونيّة للحقل من raster-service خادميّاً (tenant-scoped).

    NDVI سيّد: إن تعذّر جلبه أو لم يكن حقيقيّاً ⇒ ``None`` (لا سلطة خادميّة، لا خلط
    مصادر). صدق: يقرأ منتج raster المُتحقَّق فقط عبر الواجهة القانونيّة الوحيدة؛ لا
    حساب طيفيّ هنا. أيّ فشل نقل ⇒ ``None`` (fail-soft يُترجَم لتعليم غير-متحقَّق أعلى).
    """
    # الواجهة القانونيّة الوحيدة لحدود raster-service (نفس نمط etc_dual/field_ai_context):
    # المسار والنقل يبقيان داخل الواجهة؛ المُركِّب مستهلِك صرف لا يملك معرفة نقطة raster.
    from api.raster_service_client import get_indicator_grid

    async def _one(index: str) -> float | None:
        try:
            data = await get_indicator_grid(
                field_id, tenant_id=tenant_id, index=index, date="latest", timeout_s=20.0
            )
        except Exception:  # noqa: BLE001 — fail-soft: أيّ خطأ ⇒ لا قيمة خادميّة لهذا المؤشّر
            return None
        if (
            not isinstance(data, dict)
            or not data.get("real_data")
            or data.get("source") == "simulation"
        ):
            return None
        stats = data.get("stats") if isinstance(data.get("stats"), dict) else {}
        return stats.get("mean"), data.get("date"), data.get("scene_id") or data.get("asset_id")

    results = await asyncio.gather(*[_one(ix) for ix in SERVER_SPECTRAL_INDICES])
    parsed: dict = {}
    acquisition_date: str | None = None
    scene_id: str | None = None
    for ix, res in zip(SERVER_SPECTRAL_INDICES, results, strict=True):
        if isinstance(res, tuple):
            mean, date, scene = res
            parsed[ix] = mean
            if ix == "ndvi":
                acquisition_date, scene_id = date, scene
        else:
            parsed[ix] = None
    if parsed.get("ndvi") is None:
        return None  # NDVI السيّد غائب ⇒ لا سلطة خادميّة (لا خلط مع مدخلات العميل)
    return {
        "ndvi": parsed.get("ndvi"),
        "ndre": parsed.get("ndre"),
        "ndmi": parsed.get("ndmi"),
        "msi": parsed.get("msi"),
        "acquisition_date": acquisition_date,
        "scene_id": scene_id,
    }


async def resolve_canonical_spectral_state(
    *, tenant_id: str | None, field_id: str
) -> dict[str, Any] | None:
    """المنتَج الطيفيّ الكنسيّ للحقل، أو ``None`` حين لا سلطة خادميّة.

    ``None`` هنا معناها **الغياب المُعلَن**: يسمّيه المُركِّب ``spectral_missing`` في
    ``limitations`` ويضع ``availability.spectral=false``. البديل المرفوض هو إرجاع منتَج
    بمؤشّرات كلّها ``None`` — يبدو حاضراً ولا يحمل معرفة، وهو التلفيق نفسه بمخطّط صحيح.

    ``quality_status="raster_service_authoritative"`` هو المصدر لا الحكم على الجودة،
    و``temporal_compatible=None`` عمداً: التوافق الزمنيّ بين NDMI وMSI ادّعاء لا يملكه
    هذا المسار، وتمريره ``True`` كان سيرفع ``water_stress.confirmation_available`` بلا
    دليل. تركه ``None`` يجعل المنتَج يُصرّح بـ``ndmi_msi_temporal_compatibility_not_verified``.
    """
    if not field_id:
        return None
    server_spec = await _resolve_server_spectral(field_id, tenant_id)
    if server_spec is None:
        return None
    scene_id = server_spec.get("scene_id")
    return build_canonical_spectral_state(
        ndvi=server_spec.get("ndvi"),
        ndre=server_spec.get("ndre"),
        ndmi=server_spec.get("ndmi"),
        msi=server_spec.get("msi"),
        acquisition_date=server_spec.get("acquisition_date"),
        product_ids=[scene_id] if scene_id else [],
        quality_status="raster_service_authoritative",
        temporal_compatible=None,
    )
