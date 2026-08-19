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
import scene_policy
from raster_security_context import REQ_TENANT

LATEST_WINDOW_DAYS = int(os.getenv("CDSE_LATEST_WINDOW_DAYS", "365"))

# سقف الغيوم الذي يُسأل به المزوّد. كان مكتوباً حرفيّاً عند نداء ``process_index``
# وحده؛ ورُفِع ثابتاً لأنّ البحث في الكتالوج والمعالجة **يجب أن يتّفقا**: لو بحثنا
# بسقف أوسع من سقف المعالجة لربطنا النافذة بيوم مشهدٍ سترفضه المعالجة، فنعود بفراغ
# حيث كانت الصورة تُعرَض قبل الربط.
MAX_CLOUD_PCT = 40.0

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


def window_spans_multiple_days(date_from: str, date_to: str) -> bool:
    """هل تمتدّ النافذة على أكثر من يوم تقويميّ واحد بـUTC؟

    هذا **مُميِّز مشتقّ من النافذة نفسها** لا راية جديدة تُمرَّر: التاريخ الصريح يُبنى
    أصلاً كنافذة يومٍ واحد (``build_tile_context``)، و«latest» وحدها تمتدّ إلى
    ``LATEST_WINDOW_DAYS``. فاشتقاقه هنا يُبقي توقيع ``ensure_field_cog`` كما هو،
    ويظلّ صادقاً لو تغيّر مصدر النافذة لاحقاً — لأنّ الشرط الحقيقيّ للربط هو الامتداد،
    لا كون الطلب مُسمّى «latest».
    """
    return str(date_from)[:10] != str(date_to)[:10]


LATEST_PROBE_STEP_DAYS = int(os.getenv("CDSE_LATEST_PROBE_STEP_DAYS", "30"))


def backward_probe_windows(
    date_from: str, date_to: str, *, step_days: int = LATEST_PROBE_STEP_DAYS
) -> list[tuple[str, str]]:
    """يُقسّم نافذة الاسترجاع إلى نوافذ **من الأحدث إلى الأقدم**.

    ليست تحسيناً في الكلفة فحسب — بها **يصير ادّعاء «الأحدث» قابلاً للإثبات**.
    استجواب سنةٍ كاملة دفعةً واحدة يخضع لسقف صفحات الكتالوج
    (``cdse_client._CATALOG_MAX_PAGES``)، وترتيب المزوّد **غير موثَّق**؛ فالاقتطاع قد
    يُسقِط أحدثَ مشهدٍ نفسه ولا نعلم. أمّا حين تُستجوَب أحدثُ نافذة أوّلاً، فأيّ مشهد
    مؤهَّل يُعثَر عليه فيها **أحدث بالضرورة** من كلّ ما في النوافذ الأقدم — بلا حاجة
    إلى استيفاء صفحات السنة كلّها.

    نقيّة وحتميّة: تُعيد قائمة ``(from, to)`` تُغطّي المدى الأصليّ بلا ثغرة ولا تجاوز
    لحدّه الأدنى. ``step_days <= 0`` ⇒ نافذةٌ واحدة كما جاءت (لا حلقة لانهائيّة).
    """
    if step_days <= 0:
        return [(date_from, date_to)]
    try:
        start = datetime.strptime(str(date_from)[:10], "%Y-%m-%d").replace(tzinfo=UTC)
        end = datetime.strptime(str(date_to)[:10], "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return [(date_from, date_to)]
    if end <= start:
        return [(date_from, date_to)]

    windows: list[tuple[str, str]] = []
    cursor = end
    while cursor > start:
        lower = max(start, cursor - timedelta(days=step_days))
        windows.append(
            (lower.strftime("%Y-%m-%dT00:00:00Z"), cursor.strftime("%Y-%m-%dT23:59:59Z"))
        )
        cursor = lower
    return windows


def bind_scene_day_window(
    scenes: list[dict] | None,
    date_from: str,
    date_to: str,
    *,
    max_cloud_pct: float = MAX_CLOUD_PCT,
) -> tuple[str, str, scene_policy.SelectedScene | None]:
    """يضيّق نافذة بحثٍ ممتدّة إلى **يوم أحدث اكتساب مقبول**.

    العلّة المقيسة: ``process_index`` كان يُرسَل إليه ``mosaickingOrder=leastCC`` على
    نافذة ٣٦٥ يوماً، فيُرجِع **أقلّ المشاهد غيوماً في سنة** لا الأحدث — ويُخزَّن تحت
    مفتاح ``today`` بلا شاهدٍ على تاريخه.

    **والصياغة الأولى لهذه الدالّة عالجت النافذة ولم تُعالج الدلالة:** كانت تنتقي
    بـ``rank_scenes`` وأوزانُها ٠٫٥٠ سحاب مقابل ٠٫٢٠ حداثة، فيهزم **الأقدمُ الأنظفُ
    الأحدثَ**. ذلك جوابٌ صحيح لسؤال «أفضل جودة» وخاطئ لسؤال «الأحدث». الآن تستهلك
    ``scene_policy.select_scene(LATEST_ACCEPTABLE)`` — المنتقي المركزيّ نفسه الذي
    يستهلكه مسار الإدامة، فلا تنحرف دلالتان.

    نقيّة: تأخذ المشاهد مُعطاةً فتُقاس بلا شبكة، والنداء الشبكيّ في المُستدعي.

    **تفشل مفتوحةً عمداً (دَينُ انتقال مُعلَن):** بلا مشهد مؤهَّل تُعيد النافذة كما
    جاءت. هذا يحفظ التوافريّة ويُبقي ثغرةً دلاليّة — نافذةٌ واسعة تُقدَّم باسم
    «latest» عند العطل — وهي مُسجَّلة للإغلاق في ``IMAGERY-LATEST-SELECTION-SEMANTICS-02``
    بقاعدة «تدهور توافريّة مقبول، تلفيقٌ دلاليّ غير مقبول».
    """
    selected = scene_policy.select_scene(
        scenes,
        policy=scene_policy.SceneSelectionPolicy.LATEST_ACCEPTABLE,
        max_cloud_pct=max_cloud_pct,
    )
    if selected is None:
        return date_from, date_to, None
    window = raster_date_geo.day_window(selected.acquisition_day)
    if window is None:
        return date_from, date_to, None
    return window[0], window[1], selected


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
    """Ensure a cropped field COG exists for CDSE tile/thumbnail rendering.

    C7 invariant: a multi-day ``latest`` request is first bound to one eligible
    scene.  The selected scene identity then becomes the cache/single-flight key
    *before* cache lookup.  This prevents request-day aliases from pinning stale
    bytes and avoids the broken pattern of locking one key while storing another.
    """
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

    selected: scene_policy.SelectedScene | None = None
    mosaicking_order = _cdse.MOSAIC_LEAST_CLOUD
    client = None
    latest_window = window_spans_multiple_days(date_from, date_to)

    # ``latest`` cannot use a durable cache identity until the latest eligible
    # scene has been established.  The catalogue lookup therefore deliberately
    # precedes cache lookup for multi-day windows.  Availability may degrade;
    # semantic fabrication (processing the whole window as "latest") may not.
    if latest_window:
        try:
            client = _cdse.get_client()
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "CDSE latest client unavailable (%s/%s): %s — fail-closed",
                field_id,
                internal,
                type(e).__name__,
            )
            return None
        if not field_bbox:
            logger.warning(
                "CDSE fetch aborted (%s/%s): لا bbox للحقل — fail-closed بلا احتياطيّ ثابت",
                field_id,
                internal,
            )
            return None

        for probe_from, probe_to in backward_probe_windows(date_from, date_to):
            try:
                scenes = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda pf=probe_from, pt=probe_to: client.search_scenes(
                        bbox=list(field_bbox),
                        time_from=pf,
                        time_to=pt,
                        max_cloud_pct=MAX_CLOUD_PCT,
                        limit=10,
                        geometry=field_geom,
                    ),
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "CDSE latest binding failed (%s/%s): %s — fail-closed",
                    field_id,
                    internal,
                    type(e).__name__,
                )
                return None
            bound_from, bound_to, selected = bind_scene_day_window(scenes, date_from, date_to)
            if selected is not None:
                date_from, date_to = bound_from, bound_to
                break

        if selected is None:
            logger.warning(
                "CDSE latest unavailable (%s/%s): no eligible scene — fail-closed",
                field_id,
                internal,
            )
            return None

        mosaicking_order = _cdse.MOSAIC_MOST_RECENT
        receipt = selected.as_receipt()
        logger.info(
            "CDSE latest bound (%s/%s): %s",
            field_id,
            internal,
            _json.dumps(receipt, ensure_ascii=False, sort_keys=True),
        )
        scene_identity = str(selected.scene_id or selected.acquisition_datetime)
        cache_key = (
            f"{tenant}:{field_id}:{internal}:scene:{scene_identity}:"
            f"{selected.acquisition_day}:{'p' if has_poly else 'b'}:{geom_sig}"
        )
    else:
        cache_key = (
            f"{tenant}:{field_id}:{internal}:request:{today}:{'p' if has_poly else 'b'}:{geom_sig}"
        )

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
            if client is None:
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
                    max_cloud_pct=MAX_CLOUD_PCT,
                    mosaicking_order=mosaicking_order,
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
                    # الملفّ المؤقّت (منع تسريب قرص على مسار fail-closed أمنيّ).
                    try:
                        os.unlink(cog_path)
                    except OSError as unlink_exc:
                        logger.debug(
                            "تعذّر حذف ملفّ مؤقّت (قناع المضلّع فشل ⇒ fail-closed): %s — %s",
                            cog_path,
                            type(unlink_exc).__name__,
                        )
                    return None
            # نجاح النقل ليس نجاحاً للمحتوى (IMAGERY-BLANK-THUMBNAIL-01).
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
                cdse_singleflight.cdse_tile_cache[cache_key] = (
                    _t.monotonic() + 3600.0,
                    cog_path,
                )
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
