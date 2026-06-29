"""routers/cdse_tiles.py — بلاطات CDSE الحيّة ومعالجة CDSE (CDSE Live Tiles)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

المسارات الثلاثة هنا حسّاسة (أضافها المالك حديثاً) — نُقلت حرفيّاً مع تغيير
``@app`` إلى ``@router`` فقط؛ لا تغيير في المسار/المُدخلات/المخرجات. المساعِدات
المشتركة (الذاكرة المؤقّتة/التفويض/التصيير/النماذج) تبقى في ``main`` وتُشار إليها
عبر ``main.X``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import main
from fastapi import APIRouter, Query
from fastapi.responses import Response

router = APIRouter()

# «أحدث» = أصفى مشهد ضمن آخر هذا العدد من الأيّام (بدل كامل السنة) — حالة راهنة فعلاً.
LATEST_WINDOW_DAYS = 60


def _parse_poly(poly: str) -> dict | None:
    """يحوّل عقد الواجهة الموحَّد ``poly="lng,lat;lng,lat;..."`` (ترتيب lng,lat لا
    lat,lng) إلى GeoJSON Polygon مغلق الحلقة. يُرجِع None إن فسَد (≥3 رؤوس مطلوبة).

    هذا **مصدر الحقيقة للقصّ**: تُستخدَم الهندسة لطلب CDSE **و** لقناع rasterio البكسليّ.
    """
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
            pts.append(pts[0])  # أغلق الحلقة (GeoJSON يتطلّب حلقة مغلقة)
        return {"type": "Polygon", "coordinates": [pts]}
    except (ValueError, TypeError):
        return None


# ملاحظة توحيد main↔cert: مسار process-cdse تملكه cert في main.py (نسخة مصلّبة بنفس
# _run_cdse_processing)، فأُزيل من هذا الراوتر تفادياً للتسجيل المزدوج. هذا الراوتر يضيف
# فقط ما تفتقده cert: خدمة بلاطات cdse-tiles وcdse-tilejson (قصّ poly + قناع rasterio).
@router.get("/v1/fields/{field_id}/cdse-tiles/{z}/{x}/{y}.png")
async def field_cdse_tile(
    field_id: str,
    z: int,
    x: int,
    y: int,
    index: str = Query("ndvi"),
    date: str = Query("latest"),
    bbox_w: float | None = Query(None),
    bbox_s: float | None = Query(None),
    bbox_e: float | None = Query(None),
    bbox_n: float | None = Query(None),
    poly: str | None = Query(None),
):
    """بلاطة Sentinel Hub حيّة: تجلب الصورة الكاملة للحقل مرّة واحدة (مُخبّأة ساعة)
    وتُصيِّر منها كلّ بلاطة XYZ بنفس منطق COG (tile_render). البكسلات خارج حدود
    الحقل/NaN → شفّافة. تعذّر CDSE → بلاطة شفّافة (لا 500).

    عقد القصّ الموحَّد: ``poly="lng,lat;lng,lat;..."`` (رؤوس مضلّع الحقل من الواجهة).
    تُستخدَم الهندسة لطلب CDSE **و** لقناع rasterio البكسليّ محليّاً (قصّ دقيق على
    حافّة الحقل مستقلّ عن قصّ المزوّد). إن غابت ``poly`` تُجلَب الهندسة من DB."""
    import asyncio
    import os
    import tempfile
    import time as _t

    import cdse_client as _cdse

    await main._require_field_tenant(field_id)

    if not _cdse.is_configured():
        # تشخيص: بلاطة شفّافة لأنّ CDSE غير مُهيّأ (لا CDSE_CLIENT_ID/SECRET) — كلّ
        # المؤشّرات ستكون فارغة. (تُسجَّل مرّة لكلّ z/x/y فاحرص على مستوى DEBUG.)
        main.logger.debug("cdse-tile شفّاف: CDSE غير مُهيّأ (%s/%s)", field_id, index)
        return Response(content=main._TRANSPARENT_PNG, media_type="image/png")

    internal = main._GRID_INDEX_ALIASES.get(index, index)
    if internal not in _cdse.INDEX_EXPR:
        # تشخيص: المؤشّر غير مدعوم في CDSE (مثل ndbi/bsi/mndwi/osavi/evi2/nbr) ⇒ شفّاف.
        main.logger.info(
            "cdse-tile شفّاف: مؤشّر غير مدعوم في CDSE: %s→%s (المتاح: %s)",
            index,
            internal,
            sorted(_cdse.INDEX_EXPR),
        )
        return Response(content=main._TRANSPARENT_PNG, media_type="image/png")

    # تطبيع التاريخ + نافذة الاستعلام:
    #  • فارغ/"latest"/"today" ⇒ «أحدث»: نافذة آخر LATEST_WINDOW_DAYS يوماً ينتهي اليوم،
    #    و leastCC يختار أصفاها — حالةٌ راهنة فعلاً. (سابقاً: كامل السنة من 1 يناير،
    #    فقد يعرض مشهداً قديماً/ما بعد الحصاد لحقل القمح بلا تحذير.)
    #  • تاريخ محدَّد (YYYY-MM-DD) ⇒ نافذة اليوم نفسه فقط (دقّة، لا مشهد قديم من السنة).
    # الواجهة قد تُرسل ``date=""`` فارغاً؛ بلا التطبيع يصير ``date_from`` فاسداً.
    _is_latest = not date or date in ("latest", "today")
    _now = datetime.now(UTC)
    today = _now.strftime("%Y-%m-%d") if _is_latest else date
    if _is_latest:
        date_from = (_now - timedelta(days=LATEST_WINDOW_DAYS)).strftime("%Y-%m-%dT00:00:00Z")
    else:
        date_from = f"{today}T00:00:00Z"
    date_to = f"{today}T23:59:59Z"
    # نُميّز المخبّأ بحسب وجود القصّ: COG المقصوص على المضلّع يختلف عن غير المقصوص.
    cache_key = f"{field_id}:{internal}:{today}:{'p' if poly else 'b'}"

    # هندسة الحقل (مصدر الحقيقة للقصّ): من ``poly`` (عقد الواجهة الموحَّد) أوّلاً، وإلّا
    # من DB (الآن بعد إصلاح RLS تُرجِع الهندسة فعلاً بدل None). تُستخدَم لطلب CDSE
    # **و** لقناع rasterio البكسليّ الدقيق لاحقاً.
    field_geom: dict | None = _parse_poly(poly) if poly else None
    if field_geom is None:
        import db_persist as _db

        field_geom = await _db.fetch_field_geometry(field_id)

    # bbox الحقل: من params الطلب أوّلاً (أسرع)، وإلّا يُشتقّ من المضلّع.
    if bbox_w is not None and bbox_s is not None and bbox_e is not None and bbox_n is not None:
        field_bbox: list[float] | None = [
            float(bbox_w),
            float(bbox_s),
            float(bbox_e),
            float(bbox_n),
        ]
    else:
        field_bbox = main._bbox_from_geom(field_geom)

    # تحقّق سريع من التقاطع بين البلاطة وحدود الحقل (بلا I/O)
    if field_bbox:
        try:
            from rasterio.warp import transform_bounds as _tb
            from tile_render import tile_bounds_3857

            b3857 = tile_bounds_3857(z, x, y)
            tw, ts, te, tn = _tb("EPSG:3857", "EPSG:4326", *b3857)
            fw, fs, fe, fn = field_bbox
            if te < fw or tw > fe or tn < fs or ts > fn:
                return Response(content=main._TRANSPARENT_PNG, media_type="image/png")
        except Exception:  # noqa: BLE001 — تخطَّ فحص التقاطع إن لم يتوفّر rasterio
            pass

    async with main._cdse_lock():
        now = _t.monotonic()
        entry = main._cdse_tile_cache.get(cache_key)
        if entry and entry[0] > now and os.path.exists(entry[1]):
            cog_path = entry[1]
        else:
            # تنظيف الإدخال المنتهي الصلاحيّة (ملفّ مؤقّت)
            if entry and os.path.exists(entry[1]):
                try:
                    os.unlink(entry[1])
                except OSError:
                    pass
            try:
                client = _cdse.get_client()
                bbox_for_req = field_bbox or [44.9, 16.0, 45.1, 16.1]
                geotiff_bytes = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: client.process_index(
                        index=internal,
                        bbox=list(bbox_for_req),
                        time_from=date_from,
                        time_to=date_to,
                        geometry=field_geom,
                        max_cloud_pct=40.0,
                    ),
                )
                tf = tempfile.NamedTemporaryFile(
                    suffix=".tif",
                    delete=False,
                    prefix=f"cdse_{field_id[:8]}_{internal}_",
                )
                tf.write(geotiff_bytes)
                tf.close()
                cog_path = tf.name
                # حزام-وأمان: قناع rasterio بكسليّ دقيق على نفس المضلّع — يضمن شفّافيّة
                # خارج حدّ الحقل مهما كانت دقّة قصّ Sentinel Hub (شبكة بكسله). يُطبَّق مرّة
                # لكلّ COG (مُخبّأ) لا لكلّ بلاطة. فشله لا يكسر البلاطة (قصّ المزوّد يبقى).
                if field_geom:
                    try:
                        import tile_render as _tr

                        _tr.apply_polygon_mask(cog_path, field_geom)
                    except Exception as e:  # noqa: BLE001
                        main.logger.warning(
                            "polygon mask failed (%s/%s): %s", field_id, internal, type(e).__name__
                        )
                main._cdse_tile_cache[cache_key] = (now + 3600.0, cog_path)
            except Exception as e:  # noqa: BLE001
                main.logger.warning("CDSE fetch failed (%s/%s): %s", field_id, internal, e)
                return Response(content=main._TRANSPARENT_PNG, media_type="image/png")

    try:
        import tile_render

        png = tile_render.render_tile_png(cog_path, z, x, y, internal)
        if png:
            return Response(
                content=png,
                media_type="image/png",
                headers={"Cache-Control": "public, max-age=3600"},
            )
        # تشخيص: التصيير أعاد None = لا بكسلات صالحة (finite) داخل البلاطة — المشهد
        # مُقنَّع بالكامل (غيوم SCL/خارج المضلّع) أو لا مشهد ضمن النافذة الزمنيّة. هذا
        # سبب «المؤشّر لا يُعرَض داخل الحقل» رغم نجاح الجلب والقصّ. (القصّ سليم؛ المشكلة بيانات.)
        main.logger.info(
            "cdse-tile شفّاف: لا بيانات صالحة في البلاطة (%s/%s z%s/%s/%s) — "
            "مشهد مُقنَّع كلّيّاً (غيوم) أو لا مشهد ضمن النافذة [%s..%s]",
            field_id,
            internal,
            z,
            x,
            y,
            date_from,
            date_to,
        )
    except Exception as e:  # noqa: BLE001
        main.logger.warning("CDSE tile render failed (%s): %s", field_id, e)

    return Response(content=main._TRANSPARENT_PNG, media_type="image/png")


@router.get("/v1/fields/{field_id}/cdse-tilejson")
async def field_cdse_tilejson(
    field_id: str,
    index: str = Query("ndvi"),
    date: str = Query("latest"),
    bbox_w: float | None = Query(None),
    bbox_s: float | None = Query(None),
    bbox_e: float | None = Query(None),
    bbox_n: float | None = Query(None),
):
    """TileJSON 2.2.0 لبلاطات CDSE الحيّة — يُستخدَم لضبط إطار الخريطة."""
    import cdse_client as _cdse
    import db_persist as _db

    await main._require_field_tenant(field_id)

    if bbox_w is not None and bbox_s is not None and bbox_e is not None and bbox_n is not None:
        bounds = [float(bbox_w), float(bbox_s), float(bbox_e), float(bbox_n)]
    else:
        field_geom = await _db.fetch_field_geometry(field_id)
        bounds = main._bbox_from_geom(field_geom) or [-180.0, -85.0, 180.0, 85.0]
    # حين لا يُطلَب تاريخ محدَّد (فارغ/"latest"/"today") نُسقط ``date`` من رابط
    # البلاطة كي يبقى الرابط بلا تاريخ ويُحلّ «الأحدث» في كلّ طلب؛ وإلّا نُثبّته.
    specific_date = date if (date and date not in ("latest", "today")) else None
    qs = f"index={index}" + (f"&date={specific_date}" if specific_date else "")
    configured = _cdse.is_configured()
    out = {
        "tilejson": "2.2.0",
        "name": f"cdse-{field_id}-{index}",
        "scheme": "xyz",
        "tiles": [f"/v1/fields/{field_id}/cdse-tiles/{{z}}/{{x}}/{{y}}.png?{qs}"],
        "minzoom": 10,
        "maxzoom": 18,
        "bounds": bounds,
        "center": [
            round((bounds[0] + bounds[2]) / 2.0, 6),
            round((bounds[1] + bounds[3]) / 2.0, 6),
            14,
        ],
        "available": configured,
    }
    if not configured:
        # تشخيص صريح للواجهة (تقرأ note/reason/user_message): الصور معطّلة لأنّ اعتماد
        # Copernicus غير مضبوط — لا بيانات مُلفَّقة، بل سبب واضح للمشغّل.
        out["reason"] = "cdse_not_configured"
        out["user_message"] = (
            "صور Copernicus غير مُهيّأة: اضبط CDSE_CLIENT_ID وCDSE_CLIENT_SECRET "
            "(أو SH_CLIENT_ID/SH_CLIENT_SECRET) في بيئة خدمة الراستر ثمّ أعِد التشغيل."
        )
    return out
