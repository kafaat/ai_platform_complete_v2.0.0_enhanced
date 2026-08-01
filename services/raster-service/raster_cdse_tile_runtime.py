"""CDSE live tile request normalization/cache/render helpers.

Extracted from routers/cdse_tiles.py so the router no longer depends on main.*.
"""

from __future__ import annotations

import asyncio
import hashlib
import json as _json
import logging
import os
import tempfile
import time as _t
from datetime import UTC, datetime, timedelta

import cdse_client as _cdse
import cdse_singleflight
import db_persist as _db
import layer_lookup
import raster_date_geo
from raster_security_context import REQ_TENANT

LATEST_WINDOW_DAYS = int(os.getenv("CDSE_LATEST_WINDOW_DAYS", "365"))

logger = logging.getLogger("raster-service")


def _unlink_best_effort(path: str, reason: str) -> None:
    """يحذف ملفّاً مؤقّتاً بأفضل جهد ويُسجّل تعذّر الحذف بدل ابتلاعه.

    ثلاثة مواضع في هذا الملفّ كانت ``except OSError: pass`` صرفاً
    (SILENT-EXCEPTION-HANDLERS-11-01). الابتلاع هنا **مشروع**: صحّة المسار لا تتوقّف
    على نجاح الحذف — الإدخال يُسقَط من الذاكرة على أيّ حال، والفشل الحقيقيّ (قناع فاشل
    أو مشهد فارغ) مُسجَّل سلفاً في مُستدعي هذه الدالّة. الناقص كان **الرؤية** وحدها:
    ملفّ يتيم على القرص بلا أثر يُفسّره. فيبقى السلوك كما هو ويُضاف السبب.

    ``debug`` لا ``warning`` عمداً: التعذّر متوقّع (سباق/تنظيف متزامن) وليس عطلاً
    تشغيليّاً، ورفع مستواه يُغرِق السجلّ بضجيج يُخفي ما يهمّ.
    """
    try:
        os.unlink(path)
    except OSError as exc:
        logger.debug(
            "تعذّر حذف ملفّ مؤقّت (%s): %s — %s: %s",
            reason,
            path,
            type(exc).__name__,
            exc,
        )


def parse_poly(poly: str) -> dict | None:
    """Convert ``poly='lng,lat;lng,lat;...'`` into a closed GeoJSON Polygon."""
    try:
        pts: list[list[float]] = []
        for pair in poly.split(";"):
            pair = pair.strip()
            if not pair:
                continue
            lng_s, lat_s = pair.split(",")
            pts.append([float(lng_s), float(lat_s)])
        if len(pts) < 3:
            return None
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        return {"type": "Polygon", "coordinates": [pts]}
    except (ValueError, TypeError):
        return None


async def normalize_cdse_request(
    field_id: str,
    index: str,
    date: str,
    bbox: tuple[float | None, float | None, float | None, float | None],
    poly: str | None,
) -> dict | None:
    """Normalize CDSE tile/thumbnail request parameters without rendering.

    The satellite_cdse activation gate governs this on-demand tile surface exactly as it governs
    scene search/processing: when enforced and the gate is not effectively enabled (or unreachable),
    return None so no CDSE tile is rendered — identical fail-closed contract to the unconfigured
    branch. Default-off keeps legacy behaviour."""
    if not _cdse.is_configured():
        return None
    import imagery_source_gate

    if imagery_source_gate.enforce_enabled():
        decision = await imagery_source_gate.resolve_active_source()
        if not decision.use_cdse:
            return None
    internal = layer_lookup.GRID_INDEX_ALIASES.get(index, index)
    if not _cdse.is_truecolor(internal) and internal not in _cdse.INDEX_EXPR:
        return None

    is_latest = not date or date in ("latest", "today")
    now = datetime.now(UTC)
    today = now.strftime("%Y-%m-%d") if is_latest else date
    if is_latest:
        date_from = (now - timedelta(days=LATEST_WINDOW_DAYS)).strftime("%Y-%m-%dT00:00:00Z")
    else:
        date_from = f"{today}T00:00:00Z"
    date_to = f"{today}T23:59:59Z"

    field_geom: dict | None = parse_poly(poly) if poly else None
    if field_geom is None:
        field_geom = await _db.fetch_field_geometry(field_id)

    bbox_w, bbox_s, bbox_e, bbox_n = bbox
    if bbox_w is not None and bbox_s is not None and bbox_e is not None and bbox_n is not None:
        field_bbox: list[float] | None = [
            float(bbox_w),
            float(bbox_s),
            float(bbox_e),
            float(bbox_n),
        ]
    else:
        field_bbox = raster_date_geo.bbox_from_geom(field_geom)

    return {
        "internal": internal,
        "today": today,
        "date_from": date_from,
        "date_to": date_to,
        "field_geom": field_geom,
        "field_bbox": field_bbox,
        "has_poly": bool(poly),
    }


async def ensure_field_cog(
    field_id: str,
    internal: str,
    today: str,
    date_from: str,
    date_to: str,
    field_bbox: list[float] | None,
    field_geom: dict | None,
    has_poly: bool,
    *,
    logger,
) -> str | None:
    """Ensure a cropped field COG exists for CDSE tile/thumbnail rendering."""
    tenant = REQ_TENANT.get() or "_"
    geom_sig = "none"
    if field_geom is not None:
        try:
            geom_sig = hashlib.sha1(
                _json.dumps(field_geom, sort_keys=True, separators=(",", ":")).encode("utf-8"),
                usedforsecurity=False,
            ).hexdigest()[:12]
        except (TypeError, ValueError):
            geom_sig = "err"
    cache_key = f"{tenant}:{field_id}:{internal}:{today}:{'p' if has_poly else 'b'}:{geom_sig}"

    def _cache_hit() -> str | None:
        entry = cdse_singleflight.cdse_tile_cache.get(cache_key)
        if entry and entry[0] > _t.monotonic() and os.path.exists(entry[1]):
            return entry[1]
        return None

    async with cdse_singleflight.cdse_lock():
        hit = _cache_hit()
        if hit is not None:
            return hit
        key_lock = cdse_singleflight.cdse_key_lock(cache_key)

    async with key_lock:
        async with cdse_singleflight.cdse_lock():
            hit = _cache_hit()
            if hit is not None:
                return hit
            entry = cdse_singleflight.cdse_tile_cache.get(cache_key)
            if entry and os.path.exists(entry[1]):
                _unlink_best_effort(entry[1], "إخلاء إدخال بائت من ذاكرة البلاطات")
                cdse_singleflight.cdse_tile_cache.pop(cache_key, None)
        try:
            client = _cdse.get_client()
            if not field_bbox:
                logger.warning(
                    "CDSE fetch aborted (%s/%s): لا bbox للحقل — fail-closed بلا احتياطيّ ثابت",
                    field_id,
                    internal,
                )
                return None
            geotiff_bytes = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.process_index(
                    index=internal,
                    bbox=list(field_bbox),
                    time_from=date_from,
                    time_to=date_to,
                    geometry=field_geom,
                    max_cloud_pct=40.0,
                ),
            )
            tf = tempfile.NamedTemporaryFile(
                suffix=".tif", delete=False, prefix=f"cdse_{field_id[:8]}_{internal}_"
            )
            tf.write(geotiff_bytes)
            tf.close()
            cog_path = tf.name
            if field_geom:
                try:
                    import tile_render as _tr

                    if _cdse.is_truecolor(internal):
                        _tr.apply_polygon_mask_rgba(cog_path, field_geom)
                    else:
                        _tr.apply_polygon_mask(cog_path, field_geom)
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "polygon mask failed (%s/%s): %s — fail-closed (بلاطة مُهمَلة)",
                        field_id,
                        internal,
                        type(e).__name__,
                    )
                    # يبقى النداء حرفيّاً `os.unlink(cog_path)` هنا لا عبر المساعِد:
                    # `tests_v9/test_tile_mask_fail_closed_v29_8.py:49` حارس **مصدريّ**
                    # يفتّش النصّ عن هذه الصيغة بالذات ليُثبِت أنّ فشل القناع ينظّف
                    # الملفّ المؤقّت (منع تسريب قرص على مسار fail-closed أمنيّ). تليين
                    # الحارس ليقبل المساعِد كان سيُضعِف حارساً أمنيّاً من أجل إعادة صياغة
                    # تجميليّة — فالرؤية تُضاف هنا بلا تغيير الصيغة.
                    try:
                        os.unlink(cog_path)
                    except OSError as unlink_exc:
                        logger.debug(
                            "تعذّر حذف ملفّ مؤقّت (قناع المضلّع فشل ⇒ fail-closed): %s — %s",
                            cog_path,
                            type(unlink_exc).__name__,
                        )
                    return None
            # نجاح النقل ليس نجاحاً للمحتوى (IMAGERY-BLANK-THUMBNAIL-01): استجابة ٢٠٠
            # بـGeoTIFF سليم البنية وفارغ البكسلات تدخل الكاش ساعةً وتُجمِّد الفراغ،
            # فلا يُعيد أيّ طلب لاحق المحاولة حتّى بعد نشر إصلاح. نقيس المحتوى قبل
            # التخزين: بلا مشاهدة ⇒ لا كاش ولا ملفّ (fail-closed، والطلب التالي يعيد
            # السؤال بدل استهلاك فراغ مُخبّأ).
            try:
                import tile_render as _tr

                observable = _tr.raster_has_observable_content(cog_path)
            except Exception as e:  # noqa: BLE001 — تعذّر القياس ⇒ لا نُخزّن المجهول
                logger.warning(
                    "content check failed (%s/%s): %s — fail-closed",
                    field_id,
                    internal,
                    type(e).__name__,
                )
                observable = False
            if not observable:
                logger.info(
                    "CDSE returned an empty raster (%s/%s) — not cached: %s",
                    field_id,
                    internal,
                    date_from,
                )
                _unlink_best_effort(cog_path, "راستر فارغ من CDSE ⇒ لا يُخزَّن")
                return None
            async with cdse_singleflight.cdse_lock():
                cdse_singleflight.cdse_tile_cache[cache_key] = (_t.monotonic() + 3600.0, cog_path)
                cdse_singleflight.cdse_prune_key_locks_locked()
            return cog_path
        except Exception as e:  # noqa: BLE001
            logger.warning("CDSE fetch failed (%s/%s): %s", field_id, internal, e)
            return None


def tilejson_availability(configured: bool, index: str) -> tuple[bool, str | None, str | None]:
    """Truthful availability for a CDSE TileJSON request."""
    if not configured:
        return (
            False,
            "cdse_not_configured",
            "صور Copernicus غير مُهيّأة: اضبط CDSE_CLIENT_ID وCDSE_CLIENT_SECRET "
            "(أو SH_CLIENT_ID/SH_CLIENT_SECRET) في بيئة خدمة الراستر ثمّ أعِد التشغيل.",
        )
    internal = layer_lookup.GRID_INDEX_ALIASES.get(index, index)
    if _cdse.is_truecolor(internal):
        return True, None, None
    if internal not in _cdse.INDEX_EXPR:
        return (
            False,
            "index_not_rendered",
            "هذا المؤشّر ليس مُصيَّراً في raster-service؛ اختر مؤشّراً تفسيريّاً "
            "(NDVI/NDMI…) أو الصورة الخام (TrueColor).",
        )
    return True, None, None
