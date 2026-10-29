"""
cog_writer.py — كتابة Cloud-Optimized GeoTIFF محسّنة (تحسين تخزين القلب).

الممارسة العالميّة لـCOG جيّد: مبلّط داخليّاً + أهرامات (overviews) داخل
الملفّ + ضغط. هذا يقلّل الحجم بشدّة ويسرّع القراءة الجزئيّة (windowed) التي
يعتمد عليها TiTiler/MapLibre. بلا تحسين، COG "يفتح لكن يتصرّف كقرص بطيء".

إعدادات مختارة وفق توصيات COG:
  - ضغط DEFLATE (بلا فقد، جيّد للمؤشّرات float) أو ZSTD إن توفّر
  - PREDICTOR=2/3 (يحسّن الضغط للبيانات المتدرّجة)
  - بلاطات داخليّة 512×512
  - أهرامات (overviews) داخل الملفّ (2,4,8,16) بإعادة عيّنة average

تخطيط COG (ST-01): البلاطات والأهرامات وحدها لا تصنع COG. بناء الأهرامات في الموضع
على GTiff مفتوح يُلحِق IFDs الأهرامات وبياناتها بذيل الملفّ ويُزيح IFD الرئيسيّ بعيداً
عن الرأس ⇒ الملفّ يُقرأ لكنّ قارئ HTTP-range يحتاج جولات إضافيّة لبلوغ الفهرس. لذا
تُكتب كلّ التعديلات (بكسلات · قناع · أهرامات · وسوم) في ملفّ وسيط، ثمّ نسخة نهائيّة
واحدة بـ``COPY_SRC_OVERVIEWS=YES`` تضع كلّ IFDs في الرأس والأهرامات الأصغر أوّلاً
والدقّة الكاملة آخِراً، وتُنشَر بإعادة تسمية ذرّيّة. ``validate_cog`` يفحص هذا التخطيط
من مواضع IFD/الكتل (GDAL فقط، بلا rio-cogeo) لا مجرّد «مبلّط + أهرامات».

⚠ يتطلّب rasterio في بيئة التشغيل. عند غيابه، يُبلّغ بصدق.
"""

from __future__ import annotations

import os
import tempfile

# إعدادات COG محسّنة (وفق أفضل الممارسات)
COG_PROFILE = {
    "driver": "GTiff",
    "dtype": "float32",
    "compress": "DEFLATE",  # بلا فقد — مهمّ للمؤشّرات (NDVI دقيق)
    "predictor": 3,  # 3 للعائم (floating point) — يحسّن الضغط
    "tiled": True,
    "blockxsize": 512,
    "blockysize": 512,
    "BIGTIFF": "IF_SAFER",
}

OVERVIEW_LEVELS = [2, 4, 8, 16]


DEFAULT_NODATA = -9999.0

# مفاتيح البروفايل التي تصف المصفوفة لا خيارات الإنشاء — تُورَث من الملفّ الوسيط في
# النسخة النهائيّة، والباقي (ضغط · تنبّؤ · بلاطات · BIGTIFF · photometric/alpha) يُعاد تمريره.
_DATASET_KEYS = {"driver", "dtype", "height", "width", "count", "crs", "transform", "nodata"}

# حدّ موضع IFD الرئيسيّ: بعد ترويسة TIFF ومنطقة GDAL الشبحيّة (~200 بايت). نفس عتبة
# مدقّق rio-cogeo/GDAL المستقلّ («The offset of the main IFD should be < 300»).
_MAX_MAIN_IFD_OFFSET = 300


def _finalize_cog(write_intermediate, output_path: str, profile: dict) -> None:
    """يكتب ملفّاً وسيطاً ثمّ ينسخه نسخة COG نهائيّة وينشرها ذرّيّاً على ``output_path``.

    ``write_intermediate(path)`` يكتب كلّ شيء (بكسلات · قناع · أهرامات · وسوم) في ملفّ
    وسيط؛ ``COPY_SRC_OVERVIEWS=YES`` يعيد ترتيب البايتات تخطيطَ COG (IFDs في الرأس،
    الأهرام الأصغر أوّلاً) بلا إعادة حساب الأهرامات. لا تعديل بعد النسخة النهائيّة: أيّ
    كتابة في الموضع بعدها تُفسد الترتيب. الوسيط في مجلّد الناتج (نفس نظام الملفّات ⇒
    ``os.replace`` ذرّيّ، فلا يرى قارئ متزامن ملفّاً نصف مكتوب) ويُحذَف دائماً."""
    from rasterio import Env
    from rasterio.shutil import copy as rio_copy

    out_dir = os.path.dirname(output_path) or "."
    os.makedirs(out_dir, exist_ok=True)
    creation = {k: v for k, v in profile.items() if k not in _DATASET_KEYS}
    with tempfile.TemporaryDirectory(prefix=".cog-", dir=out_dir) as tmp:
        intermediate = os.path.join(tmp, "intermediate.tif")
        final = os.path.join(tmp, "final.tif")
        # The atomic artifact must include its mask, even under an external-mask environment.
        with Env(GDAL_TIFF_INTERNAL_MASK=True):
            write_intermediate(intermediate)
            rio_copy(intermediate, final, driver="GTiff", copy_src_overviews=True, **creation)
        os.replace(final, output_path)


def write_cog(
    array,
    output_path: str,
    transform,
    crs: str = "EPSG:4326",
    nodata: float = DEFAULT_NODATA,
) -> dict:
    """يكتب مصفوفة مؤشّر كـCOG محسّن (ضغط + بلاطات + أهرامات داخليّة).

    يُرجِع {written, path, size_bytes, compression, overviews}. صدق: يكتب
    فعليّاً عند توفّر rasterio؛ وإلّا يُبلّغ بأنّه غير متاح (لا يدّعي كتابة).
    """
    try:
        import rasterio
        from rasterio.enums import Resampling
    except ImportError:
        return {"written": False, "reason": "rasterio غير متوفّر — يُكتب في التشغيل"}

    try:
        import numpy as np
    except ImportError:
        return {"written": False, "reason": "numpy غير متوفّر — يُكتب في التشغيل"}

    # صدق: مدخل بلا مصفوفة ثنائيّة صالحة (None/بلا shape) ⇒ مظروف فشل صريح لا انهيار.
    # الـdocstring يعِد بـ«لا يدّعي كتابة»؛ NoneType.shape كان يكسر ذلك (تدقيق 2026-07-05).
    if array is None or not hasattr(array, "shape") or len(getattr(array, "shape", ())) != 2:
        return {"written": False, "reason": "مصفوفة غير صالحة (متوقَّع مصفوفة ثنائيّة الأبعاد)"}

    h, w = array.shape
    # Convert only one tile at a time; retain masks on caller-owned arrays.
    if not np.isfinite(nodata):
        nodata = DEFAULT_NODATA
    profile = {
        **COG_PROFILE,
        "height": h,
        "width": w,
        "count": 1,
        "crs": crs,
        "transform": transform,
        "nodata": nodata,
    }

    def _write(path: str) -> None:
        with rasterio.open(path, "w", **profile) as dst:
            for window in write_windows(h, w):
                rows, cols = window.toslices()
                tile = np.ma.asarray(array[rows, cols], dtype="float32")
                values = np.ma.getdata(tile)
                valid = ~np.ma.getmaskarray(tile) & np.isfinite(values) & (values != nodata)
                dst.write(np.where(valid, values, nodata).astype("float32"), 1, window=window)
                dst.write_mask(valid.astype("uint8") * 255, window=window)
            # أهرامات داخليّة (overviews) — قراءة سريعة عند التكبير/التصغير.
            # average للمؤشّر المتّصل؛ القناع يُهرَّم معها داخليّاً.
            dst.build_overviews(OVERVIEW_LEVELS, Resampling.average)
            # وسم المجال الافتراضيّ (اصطلاح rio-cogeo) — يُنسَخ مع البيانات إلى الناتج.
            dst.update_tags(OVR_RESAMPLING_ALG="AVERAGE")

    _finalize_cog(_write, output_path, profile)

    size = os.path.getsize(output_path)
    return {
        "written": True,
        "path": output_path,
        "size_bytes": size,
        "size_mb": round(size / 1e6, 2),
        "compression": "DEFLATE+predictor3",
        "overviews": OVERVIEW_LEVELS,
        "block_size": "512x512",
        # توحيد main↔cert: ندمج تدقيق COG في ردّ الكتابة (سلوك main) — تدقيق فوريّ بعد
        # الكتابة (مبلّط + أهرامات) دون استدعاء منفصل. يطابقه حارس test_cog_writer_internal_mask.
        "validation": validate_cog(output_path),
    }


# ملفّ RGBA (الصورة الخام truecolor): 4 نطاقات UINT8 بدل مؤشّر أحاديّ FLOAT32.
RGBA_COG_PROFILE = {
    "driver": "GTiff",
    "dtype": "uint8",
    "compress": "DEFLATE",
    "predictor": 2,  # 2 للأعداد الصحيحة (RGB) — 3 للعائم فقط
    "tiled": True,
    "blockxsize": 512,
    "blockysize": 512,
    "BIGTIFF": "IF_SAFER",
}


def write_rgba_cog(array, output_path: str, transform, crs: str = "EPSG:4326") -> dict:
    """يكتب صورة RGBA (4 نطاقات UINT8) كـCOG محسّن — للصورة الخام (truecolor).

    ``array``: ``(4,H,W)`` أو ``(H,W,4)`` (يُقبَل 3 نطاقات RGB أيضاً). النطاق الرابع
    ألفا (0=شفّاف) ويُعلَّم ColorInterp.alpha كي يقرأه GDAL/التصيير كقناع. بلاطات +
    أهرامات داخليّة (nearest — يحافظ حدّة الحواف لصورة 8-بت). صدق: يكتب فعليّاً عند
    توفّر rasterio؛ وإلّا يُبلّغ بأنّه غير متاح (لا يدّعي كتابة)."""
    try:
        import rasterio
        from rasterio.enums import ColorInterp, Resampling
    except ImportError:
        return {"written": False, "reason": "rasterio غير متوفّر — يُكتب في التشغيل"}
    try:
        import numpy as np
    except ImportError:
        return {"written": False, "reason": "numpy غير متوفّر — يُكتب في التشغيل"}

    if array is None or not hasattr(array, "shape"):
        return {"written": False, "reason": "مصفوفة غير صالحة"}
    arr = np.ma.asarray(array)
    # (H,W,C) ⇒ (C,H,W).
    if arr.ndim == 3 and arr.shape[2] in (3, 4) and arr.shape[0] not in (3, 4):
        arr = np.transpose(arr, (2, 0, 1))
    if arr.ndim != 3 or arr.shape[0] not in (3, 4):
        return {"written": False, "reason": "متوقَّع RGB/RGBA (3 أو 4 نطاقات)"}
    bands, h, w = arr.shape[0], arr.shape[1], arr.shape[2]
    profile = {
        **RGBA_COG_PROFILE,
        "height": h,
        "width": w,
        "count": bands,
        "crs": crs,
        "transform": transform,
    }
    # صرّح PHOTOMETRIC=RGB على القرص (بدل الافتراضيّ MINISBLACK). بدونه: قناة لونيّة
    # واحدة + عيّنة إضافيّة واحدة (ألفا) = 2 ≠ 4 عيّنات ⇒ GDAL يحذّر عند القراءة
    # («Sum of Photometric … and ExtraSamples doesn't match SamplesPerPixel») ويعيد
    # تعريف نطاقات RGB كـExtraSamples (فقدان تفسير اللون لأيّ مستهلِك GDAL). للنطاق
    # الرابع: ALPHA=YES يوسمه ألفا غير مرتبطة (ExtraSamples=2) ⇒ 3+1=4 متّسق، لا تحذير.
    profile["photometric"] = "RGB"
    if bands >= 4:
        profile["alpha"] = "YES"

    def _write(path: str) -> None:
        with rasterio.open(path, "w", **profile) as dst:
            for window in write_windows(h, w):
                rows, cols = window.toslices()
                tile = arr[:, rows, cols]
                values = np.ma.filled(tile, 0).astype("uint8")
                valid = ~np.ma.getmaskarray(tile).any(axis=0)
                if bands == 4:
                    valid &= values[3] > 0
                    values[3] = np.where(valid, values[3], 0)
                dst.write(values, window=window)
                dst.write_mask(valid.astype("uint8") * 255, window=window)
            interps = [ColorInterp.red, ColorInterp.green, ColorInterp.blue]
            if bands >= 4:
                interps.append(ColorInterp.alpha)  # النطاق الرابع = ألفا (قناع الخارج/الغيوم)
            dst.colorinterp = interps
            # nearest لمنتج العرض 8-بت: لا يخلط ألفا 0/255 ولا يخترع ألواناً.
            dst.build_overviews(OVERVIEW_LEVELS, Resampling.nearest)
            dst.update_tags(OVR_RESAMPLING_ALG="NEAREST")

    _finalize_cog(_write, output_path, profile)

    size = os.path.getsize(output_path)
    return {
        "written": True,
        "path": output_path,
        "size_bytes": size,
        "size_mb": round(size / 1e6, 2),
        "compression": "DEFLATE+predictor2",
        "overviews": OVERVIEW_LEVELS,
        "block_size": "512x512",
        "bands": bands,
        "validation": validate_cog(output_path),
    }


def write_windows(height: int, width: int):
    """Bound Python pixel buffers to the output COG tile size, including edge tiles."""
    from rasterio.windows import Window

    for row in range(0, height, 512):
        for col in range(0, width, 512):
            yield Window(col, row, min(512, width - col), min(512, height - row))


def source_valid_mask(src, window):
    """Dataset validity and alpha jointly define valid display pixels."""
    valid = src.dataset_mask(window=window) > 0
    if src.count == 4:
        valid &= src.read(4, window=window) > 0
    return valid


def write_rgba_cog_source(src, output_path: str) -> dict:
    """Copy an open RGB/RGBA uint8 raster with bounded pixel buffers.

    The caller owns the source handle and admission budget. GDAL block/cache and
    overview allocations remain separate from these Python window buffers.
    """
    import numpy as np
    import rasterio
    from rasterio.enums import ColorInterp, Resampling

    if src.count not in (3, 4) or any(dtype != "uint8" for dtype in src.dtypes):
        raise ValueError("truecolor source requires 3 or 4 uint8 bands")
    if src.crs is None:
        raise ValueError("truecolor source requires a CRS")
    profile = {
        **RGBA_COG_PROFILE,
        "height": src.height,
        "width": src.width,
        "count": src.count,
        "crs": src.crs,
        "transform": src.transform,
        "photometric": "RGB",
    }
    if src.count == 4:
        profile["alpha"] = "YES"

    def _write(path):
        with rasterio.open(path, "w", **profile) as dst:
            for window in write_windows(src.height, src.width):
                values = src.read(window=window)
                valid = source_valid_mask(src, window)
                if src.count == 4:
                    values[3] = np.where(valid, values[3], 0)
                dst.write(values, window=window)
                dst.write_mask(valid.astype("uint8") * 255, window=window)
            dst.colorinterp = (ColorInterp.red, ColorInterp.green, ColorInterp.blue) + (
                (ColorInterp.alpha,) if src.count == 4 else ()
            )
            dst.build_overviews(OVERVIEW_LEVELS, Resampling.nearest)
            dst.update_tags(OVR_RESAMPLING_ALG="NEAREST")

    _finalize_cog(_write, output_path, profile)
    size = os.path.getsize(output_path)
    return {
        "written": True,
        "path": output_path,
        "size_bytes": size,
        "size_mb": round(size / 1e6, 2),
        "compression": "DEFLATE+predictor2",
        "overviews": OVERVIEW_LEVELS,
        "block_size": "512x512",
        "bands": src.count,
        "validation": validate_cog(output_path),
    }


def _tiff_offset(src, item: str, ovr: int | None = None) -> int | None:
    """موضع بايت من مجال TIFF في GDAL (``IFD_OFFSET``/``BLOCK_OFFSET_0_0``)؛ None إن غاب."""
    value = src.get_tag_item(item, "TIFF", bidx=1, ovr=ovr)
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _cog_layout_errors(src) -> list[str]:
    """قواعد تخطيط COG من مواضع IFD/الكتل كما يقيسها GDAL — نفس قواعد مدقّق GDAL
    ``validate_cloud_optimized_geotiff`` وrio-cogeo strict، بلا تبعيّة جديدة:
    IFD الرئيسيّ في الرأس، IFDs الأهرامات بعده تصاعديّاً، وبيانات الأهرامات قبل
    بيانات الدقّة الكاملة من الأصغر إلى الأكبر."""
    if src.driver != "GTiff":
        return [f"المشغّل {src.driver} ليس GTiff"]
    main_ifd = _tiff_offset(src, "IFD_OFFSET")
    if main_ifd is None:
        return ["تعذّر قراءة مواضع IFD من GDAL"]
    errors: list[str] = []
    if main_ifd >= _MAX_MAIN_IFD_OFFSET:
        errors.append(f"IFD الرئيسيّ عند البايت {main_ifd} لا في الرأس (< {_MAX_MAIN_IFD_OFFSET})")
    levels = range(len(src.overviews(1)))
    prev_ifd = main_ifd
    for i in levels:
        ifd = _tiff_offset(src, "IFD_OFFSET", ovr=i)
        if ifd is None or ifd <= prev_ifd:
            errors.append(f"IFD الهرم {i} عند {ifd} ليس بعد IFD السابق عند {prev_ifd}")
        prev_ifd = ifd if ifd is not None else prev_ifd
    # الكتلة الأولى لكلّ مستوى: الأصغر أوّلاً في الملفّ، والدقّة الكاملة آخِراً.
    # 0/None = كتلة فارغة (sparse) ⇒ لا مقارنة.
    blocks = [_tiff_offset(src, "BLOCK_OFFSET_0_0")]
    blocks += [_tiff_offset(src, "BLOCK_OFFSET_0_0", ovr=i) for i in levels]
    names = ["الدقّة الكاملة"] + [f"الهرم {i}" for i in levels]
    for larger in range(len(blocks) - 1):
        a, b = blocks[larger], blocks[larger + 1]
        if a and b and a < b:
            errors.append(f"بيانات {names[larger]} ({a}) قبل بيانات {names[larger + 1]} ({b})")
    return errors


def validate_cog(path: str) -> dict:
    """يتحقّق أنّ ملفّاً COG صالح: مبلّط + أهرامات داخليّة + **تخطيط COG** (IFDs في الرأس،
    الأهرامات قبل الدقّة الكاملة). «مبلّط + أهرامات» وحدهما كانا يشهدان valid لملفّ
    يرفضه مدقّق COG المستقلّ (ST-01). للتدقيق بعد الكتابة."""
    try:
        import rasterio
    except ImportError:
        return {"valid": None, "reason": "rasterio غير متوفّر"}
    if not os.path.exists(path):
        return {"valid": False, "reason": "الملفّ غير موجود"}
    with rasterio.open(path) as src:
        is_tiled = src.profile.get("tiled", False)
        has_overviews = len(src.overviews(1)) > 0
        errors = _cog_layout_errors(src)
        return {
            "valid": bool(is_tiled and has_overviews and not errors),
            "tiled": is_tiled,
            "overviews": src.overviews(1),
            "compression": str(src.profile.get("compress", "none")),
            "layout": src.tags(ns="IMAGE_STRUCTURE").get("LAYOUT"),
            "errors": errors,
            "note": "COG جيّد = مبلّط + أهرامات داخليّة + IFDs في الرأس والأهرامات قبل الدقّة الكاملة",
        }
