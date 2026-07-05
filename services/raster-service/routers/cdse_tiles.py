"""routers/cdse_tiles.py — بلاطات CDSE الحيّة ومعالجة CDSE (CDSE Live Tiles)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

المسارات الثلاثة هنا حسّاسة (أضافها المالك حديثاً) — نُقلت حرفيّاً مع تغيير
``@app`` إلى ``@router`` فقط؛ لا تغيير في المسار/المُدخلات/المخرجات. المساعِدات
المشتركة (الذاكرة المؤقّتة/التفويض/التصيير/النماذج) تبقى في ``main`` وتُشار إليها
عبر ``main.X``.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import main
from fastapi import APIRouter, Query
from fastapi.responses import Response

router = APIRouter()

# بادئة البوّابة العامّة في روابط TileJSON: الواجهة تصل عبر nginx ``/api/raster/`` لا
# ``/v1/`` المباشر، فمصفوفة ``tiles`` يجب أن تحمل البادئة لتُحلّ من أصل الصفحة. قابلة
# للضبط بالبيئة (``RASTER_PUBLIC_PREFIX``) بدل ترميزها صلباً — يفكّ الاقتران ببوّابة بعينها.
_PUBLIC_PREFIX = os.getenv("RASTER_PUBLIC_PREFIX", "/api/raster").rstrip("/")

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


async def _normalize_cdse_request(
    field_id: str,
    index: str,
    date: str,
    bbox: tuple[float | None, float | None, float | None, float | None],
    poly: str | None,
) -> dict | None:
    """يطبّع طلب CDSE (مؤشّر/تاريخ/هندسة/bbox) — مشترك بين البلاطة والمُصغَّرة.

    يُرجِع dict بالمعاملات المحلولة، أو ``None`` حين يتعذّر تقديم بيانات (CDSE غير
    مُهيّأ / مؤشّر غير مدعوم) — يخدم المُستدعي عندها صورة شفّافة (لا 500). لا يجلب أيّ
    شيء (نقيّ I/O خفيف: قد يقرأ هندسة الحقل من DB فقط)."""
    import cdse_client as _cdse

    if not _cdse.is_configured():
        return None
    internal = main._GRID_INDEX_ALIASES.get(index, index)
    if internal not in _cdse.INDEX_EXPR:
        return None

    _is_latest = not date or date in ("latest", "today")
    _now = datetime.now(UTC)
    today = _now.strftime("%Y-%m-%d") if _is_latest else date
    if _is_latest:
        date_from = (_now - timedelta(days=LATEST_WINDOW_DAYS)).strftime("%Y-%m-%dT00:00:00Z")
    else:
        date_from = f"{today}T00:00:00Z"
    date_to = f"{today}T23:59:59Z"

    field_geom: dict | None = _parse_poly(poly) if poly else None
    if field_geom is None:
        import db_persist as _db

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
        field_bbox = main._bbox_from_geom(field_geom)

    return {
        "internal": internal,
        "today": today,
        "date_from": date_from,
        "date_to": date_to,
        "field_geom": field_geom,
        "field_bbox": field_bbox,
        "has_poly": bool(poly),
    }


async def _ensure_field_cog(
    field_id: str,
    internal: str,
    today: str,
    date_from: str,
    date_to: str,
    field_bbox: list[float] | None,
    field_geom: dict | None,
    has_poly: bool,
) -> str | None:
    """يضمن وجود COG مقصوص للحقل/المؤشّر/التاريخ (جلب CDSE + تخبئة ساعة + قناع مضلّع).

    مصدر واحد للجلب/التخبئة/القصّ تتشاركه بلاطة cdse-tiles والمُصغَّرة (cdse-thumbnail).
    يُرجِع مسار الـCOG أو ``None`` عند تعذّر الجلب (يخدم المُستدعي صورة شفّافة)."""
    import asyncio
    import hashlib
    import json as _json
    import os
    import tempfile
    import time as _t

    import cdse_client as _cdse

    # مفتاح الكاش يجب أن يعزل المستأجرين (تفادي تسريب COG عبر المستأجرين) وأن يتبدّل
    # عند تغيّر هندسة الحقل (تفادي خدمة COG لهندسة قديمة بعد تعديل الحدود) — v3-Finding-6.
    tenant = main._REQ_TENANT.get() or "_"
    geom_sig = "none"
    if field_geom is not None:
        try:
            # بصمة كاش لا أمنيّة (تفريق مفاتيح فقط) ⇒ usedforsecurity=False يوضّح النيّة
            # ويُرضي bandit B324 (SHA1 «الضعيف» ليس استعمالاً أمنيّاً هنا) وأنظمة FIPS.
            geom_sig = hashlib.sha1(
                _json.dumps(field_geom, sort_keys=True, separators=(",", ":")).encode("utf-8"),
                usedforsecurity=False,
            ).hexdigest()[:12]
        except (TypeError, ValueError):
            geom_sig = "err"
    cache_key = f"{tenant}:{field_id}:{internal}:{today}:{'p' if has_poly else 'b'}:{geom_sig}"
    async with main._cdse_lock():
        now = _t.monotonic()
        entry = main._cdse_tile_cache.get(cache_key)
        if entry and entry[0] > now and os.path.exists(entry[1]):
            return entry[1]
        if entry and os.path.exists(entry[1]):
            try:
                os.unlink(entry[1])
            except OSError:
                pass
        try:
            client = _cdse.get_client()
            # fail-closed: بلا bbox للحقل لا نطلب صورة على bbox ثابت (كان يمن [44.9..])
            # فنخدِّم بلاطة لهندسة خاطئة صامتة. لا احتياطيّ مُضلِّل — نعيد None (بلاطة شفّافة). v3-Finding-7
            if not field_bbox:
                main.logger.warning(
                    "CDSE fetch aborted (%s/%s): لا bbox للحقل — fail-closed بلا احتياطيّ ثابت",
                    field_id,
                    internal,
                )
                return None
            bbox_for_req = list(field_bbox)
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
                suffix=".tif", delete=False, prefix=f"cdse_{field_id[:8]}_{internal}_"
            )
            tf.write(geotiff_bytes)
            tf.close()
            cog_path = tf.name
            if field_geom:
                try:
                    import tile_render as _tr

                    _tr.apply_polygon_mask(cog_path, field_geom)
                except Exception as e:  # noqa: BLE001
                    # fail-closed: فشل القناع المحلّيّ ⇒ لا نُخدِّم/نُخزِّن بلاطة قد تتجاوز
                    # حدّ الحقل. (المزوّد يقصّ على المضلّع أيضاً، لكن لا نعتمد على ذلك
                    # وحده — نطابق فلسفة fail-closed للنظام.) نتخلّص من الملفّ المؤقّت.
                    main.logger.warning(
                        "polygon mask failed (%s/%s): %s — fail-closed (بلاطة مُهمَلة)",
                        field_id,
                        internal,
                        type(e).__name__,
                    )
                    try:
                        os.unlink(cog_path)
                    except OSError:
                        pass
                    return None
            main._cdse_tile_cache[cache_key] = (now + 3600.0, cog_path)
            return cog_path
        except Exception as e:  # noqa: BLE001
            main.logger.warning("CDSE fetch failed (%s/%s): %s", field_id, internal, e)
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
    await main._require_field_tenant(field_id)

    params = await _normalize_cdse_request(
        field_id, index, date, (bbox_w, bbox_s, bbox_e, bbox_n), poly
    )
    if params is None:
        # CDSE غير مُهيّأ أو مؤشّر غير مدعوم ⇒ بلاطة شفّافة (لا 500).
        return Response(content=main._TRANSPARENT_PNG, media_type="image/png")
    internal = params["internal"]
    field_bbox = params["field_bbox"]
    field_geom = params["field_geom"]

    # تحقّق سريع من التقاطع بين البلاطة وحدود الحقل (بلا I/O) — خاصّ بالبلاطة.
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

    cog_path = await _ensure_field_cog(
        field_id,
        internal,
        params["today"],
        params["date_from"],
        params["date_to"],
        field_bbox,
        field_geom,
        params["has_poly"],
    )
    if cog_path is None:
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
            "cdse-tile شفّاف: لا بيانات صالحة في البلاطة (%s/%s z%s/%s/%s)",
            field_id,
            internal,
            z,
            x,
            y,
        )
    except Exception as e:  # noqa: BLE001
        main.logger.warning("CDSE tile render failed (%s): %s", field_id, e)

    return Response(content=main._TRANSPARENT_PNG, media_type="image/png")


@router.get("/v1/fields/{field_id}/cdse-thumbnail.png")
async def field_cdse_thumbnail(
    field_id: str,
    index: str = Query("ndvi"),
    date: str = Query("latest"),
    bbox_w: float | None = Query(None),
    bbox_s: float | None = Query(None),
    bbox_e: float | None = Query(None),
    bbox_n: float | None = Query(None),
    poly: str | None = Query(None),
    size: int = Query(160, ge=48, le=512),
):
    """مُصغَّرة كاملة لصورة الحقل (مؤشّر) لتاريخ مُعطى — لبطاقات شريط السجلّ الزمنيّ.

    يشارك بلاطةَ cdse-tiles منطقَ الجلب/التخبئة/القصّ (``_ensure_field_cog``)، لكن
    يُصيِّر امتداد الحقل كلّه إلى صورة واحدة (``render_cog_thumbnail_png``) بدل بلاطة
    XYZ. خارج المضلّع/NaN → شفّاف، فتظهر صورة شكل الحقل وحده. تعذّر CDSE/لا بيانات ⇒
    صورة شفّافة (لا 500)."""
    await main._require_field_tenant(field_id)

    params = await _normalize_cdse_request(
        field_id, index, date, (bbox_w, bbox_s, bbox_e, bbox_n), poly
    )
    if params is None:
        return Response(content=main._TRANSPARENT_PNG, media_type="image/png")

    cog_path = await _ensure_field_cog(
        field_id,
        params["internal"],
        params["today"],
        params["date_from"],
        params["date_to"],
        params["field_bbox"],
        params["field_geom"],
        params["has_poly"],
    )
    if cog_path is None:
        return Response(content=main._TRANSPARENT_PNG, media_type="image/png")

    try:
        import tile_render

        png = tile_render.render_cog_thumbnail_png(cog_path, params["internal"], max_px=size)
        if png:
            return Response(
                content=png,
                media_type="image/png",
                headers={"Cache-Control": "public, max-age=3600"},
            )
    except Exception as e:  # noqa: BLE001
        main.logger.warning("CDSE thumbnail render failed (%s): %s", field_id, e)

    return Response(content=main._TRANSPARENT_PNG, media_type="image/png")


def _tilejson_availability(configured: bool, index: str) -> tuple[bool, str | None, str | None]:
    """توافر بلاطات TileJSON بصدق: يجب أن تكون CDSE مُهيّأة **و** المؤشّر قابلاً
    للتصيير (ضمن ``INDEX_EXPR`` بعد المرادفات).

    ``truecolor`` (صورة الحقل الخام) ليس مؤشّراً مُصيَّراً في raster-service بعد —
    فبلا هذا الفحص يُبلَّغ ``available=true`` (لأنّ CDSE مُهيّأة) بينما بلاطة
    ``cdse-tiles`` تعود شفّافة، فتبدو الخريطة فارغة بلا سبب. نُبلِّغ الحقيقة بدل ذلك."""
    import cdse_client as _cdse

    if not configured:
        return (
            False,
            "cdse_not_configured",
            "صور Copernicus غير مُهيّأة: اضبط CDSE_CLIENT_ID وCDSE_CLIENT_SECRET "
            "(أو SH_CLIENT_ID/SH_CLIENT_SECRET) في بيئة خدمة الراستر ثمّ أعِد التشغيل.",
        )
    internal = main._GRID_INDEX_ALIASES.get(index, index)
    if internal not in _cdse.INDEX_EXPR:
        return (
            False,
            "index_not_rendered",
            "الصورة الخام (TrueColor) ليست مؤشّراً مُصيَّراً في raster-service بعد؛ "
            "اختر مؤشّراً تفسيريّاً (NDVI/NDMI…) أو شغّل تجهيز الصور — ريثما يُضاف تصيير RGB.",
        )
    return True, None, None


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
    # tid يجب أن يُحقَن في رابط البلاطة: البلاطات تُحمَّل كـ<img> بلا ترويسات auth،
    # فبلا tid يصل الطلب بلا مستأجِر ويرفضه _require_field_tenant (403). نفس عقد
    # field_tilejson القرصيّ. + urlencode بدل التسلسل اليدويّ (ترميز آمن). v3-Finding-8
    from urllib.parse import urlencode

    tile_params: dict[str, str] = {"index": index}
    if specific_date:
        tile_params["date"] = specific_date
    req_tenant = main._REQ_TENANT.get()
    if req_tenant:
        tile_params["tid"] = req_tenant
    qs = urlencode(tile_params)
    # المسار عبر البوّابة (nginx /api/raster/ → raster:8001/): الواجهة تحتاج
    # /api/raster/v1/… لا /v1/… المباشر كي تمرّ عبر proxy_pass في الإنتاج.
    configured = _cdse.is_configured()
    available, reason, user_message = _tilejson_availability(configured, index)
    out = {
        "tilejson": "2.2.0",
        "name": f"cdse-{field_id}-{index}",
        "scheme": "xyz",
        "tiles": [f"{_PUBLIC_PREFIX}/v1/fields/{field_id}/cdse-tiles/{{z}}/{{x}}/{{y}}.png?{qs}"],
        "minzoom": 10,
        "maxzoom": 18,
        "bounds": bounds,
        "center": [
            round((bounds[0] + bounds[2]) / 2.0, 6),
            round((bounds[1] + bounds[3]) / 2.0, 6),
            14,
        ],
        "available": available,
    }
    # تشخيص صريح للواجهة (تقرأ note/reason/user_message): لا بيانات مُلفَّقة، بل سبب
    # واضح (اعتماد غير مضبوط، أو مؤشّر غير مُصيَّر مثل truecolor).
    if reason:
        out["reason"] = reason
    if user_message:
        out["user_message"] = user_message
    return out
