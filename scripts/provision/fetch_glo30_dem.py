#!/usr/bin/env python3
"""
fetch_glo30_dem.py — تجهيز Copernicus DEM GLO-30 كـCOG واحد لمنطقة الحقول.

يُنزّل بلاطات GLO-30 (1°×1°) المُغطّية لـbbox من AWS Open Data (وصول مجهول عبر HTTPS،
بلا اعتماد/boto3)، ثمّ يدمجها في COG واحد يُضبَط في ``FIELD_DEM_PATH`` فتعمل طبقات
التضاريس (hillshade/slope/contours) فوراً بلا تغيير كود.

المصدر: s3://copernicus-dem-30m (Registry of Open Data on AWS) — بلاطات COG جاهزة،
EPSG:4326، ارتفاع EGM2008. مجّانيّ مع إلزاميّة ذكر المصدر (© Copernicus DEM / ESA).

الاستعمال:
    python3 scripts/provision/fetch_glo30_dem.py \
        --bbox 43.5 15.5 46.0 17.5 \
        --out /data/dem/aljawf_glo30_cog.tif
    export FIELD_DEM_PATH=/data/dem/aljawf_glo30_cog.tif   # ثمّ أعِد تشغيل raster-service

صدق: لا يخترع تضاريس — يُنزّل بيانات ESA الحقيقيّة. البلاطات فوق البحر/غير الموجودة
(404) تُتخطّى بوضوح. لا يُشغَّل في CI (شبكة/بيانات) — أداة تشغيل للمشغّل.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import tempfile

# مضيف AWS العامّ للبلاطات (وصول مجهول — لا توقيع/اعتماد).
_BASE = "https://copernicus-dem-30m.s3.eu-central-1.amazonaws.com"

# نطاقات جاهزة (bbox = minLon,minLat,maxLon,maxLat). اليمن مُغطّى بالكامل في GLO-30.
_PRESETS: dict[str, list[float]] = {
    "yemen": [42.0, 12.0, 54.0, 19.0],  # كامل اليمن — تنبيه: كثير البلاطات (~84) وعدّة GB.
    "aljawf": [43.5, 15.5, 46.0, 17.5],  # منطقة الجوف/السنيدار — كافٍ للمزرعة.
}


def tile_name(lat_sw: int, lon_sw: int) -> str:
    """اسم بلاطة GLO-30 من ركن الجنوب-الغرب الصحيح (درجات).

    مثال: (15, 44) → ``Copernicus_DSM_COG_10_N15_00_E044_00_DEM``.
    """
    ns = "N" if lat_sw >= 0 else "S"
    ew = "E" if lon_sw >= 0 else "W"
    return f"Copernicus_DSM_COG_10_{ns}{abs(lat_sw):02d}_00_{ew}{abs(lon_sw):03d}_00_DEM"


def tiles_for_bbox(bbox: list[float]) -> list[tuple[int, int]]:
    """أركان (lat_sw, lon_sw) الصحيحة لكلّ بلاطة 1°×1° تُغطّي bbox."""
    min_lon, min_lat, max_lon, max_lat = bbox
    lats = range(math.floor(min_lat), math.floor(max_lat) + 1)
    lons = range(math.floor(min_lon), math.floor(max_lon) + 1)
    return [(la, lo) for la in lats for lo in lons]


def tile_url(lat_sw: int, lon_sw: int) -> str:
    name = tile_name(lat_sw, lon_sw)
    return f"{_BASE}/{name}/{name}.tif"


def _download(url: str, dest: str) -> bool:
    """يُنزّل بلاطة؛ True عند النجاح، False عند 404 (بحر/غير موجودة) — بلا تلفيق."""
    import httpx

    try:
        with httpx.stream("GET", url, timeout=120.0, follow_redirects=True) as r:
            if r.status_code == 404:
                return False
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        return True
    except httpx.HTTPError as e:
        print(f"  ✗ فشل تنزيل {url}: {type(e).__name__}", file=sys.stderr)
        return False


def build_cog(tif_paths: list[str], out_path: str) -> None:
    """يدمج البلاطات في COG واحد (DEFLATE + overviews) عبر rasterio."""
    import rasterio
    from rasterio.merge import merge

    srcs = [rasterio.open(p) for p in tif_paths]
    try:
        mosaic, transform = merge(srcs)
        profile = srcs[0].profile.copy()
    finally:
        for s in srcs:
            s.close()
    profile.update(
        driver="COG",
        height=mosaic.shape[1],
        width=mosaic.shape[2],
        transform=transform,
        compress="DEFLATE",
        count=mosaic.shape[0],
    )
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(mosaic)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="تجهيز Copernicus GLO-30 DEM كـCOG لـbbox.")
    ap.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"),
    )
    ap.add_argument(
        "--country", choices=sorted(_PRESETS), help="نطاق جاهز بدل --bbox (مثل yemen/aljawf)."
    )
    ap.add_argument("--out", required=True, help="مسار COG الناتج (FIELD_DEM_PATH).")
    args = ap.parse_args(argv)

    bbox = args.bbox or (_PRESETS.get(args.country) if args.country else None)
    if not bbox:
        ap.error("مطلوب --bbox أو --country (مثل --country yemen).")

    tiles = tiles_for_bbox(bbox)
    print(f"بلاطات مطلوبة لـbbox {bbox}: {len(tiles)}")
    if len(tiles) > 20:
        print(
            f"  ⚠ {len(tiles)} بلاطة — قد يبلغ الحجم عدّة GB ويطول التنزيل. "
            "لمزرعة واحدة استعمل bbox أضيق (مثل --country aljawf).",
            file=sys.stderr,
        )
    with tempfile.TemporaryDirectory() as td:
        got: list[str] = []
        for la, lo in tiles:
            name = tile_name(la, lo)
            dest = os.path.join(td, f"{name}.tif")
            print(f"  ⬇ {name} …")
            if _download(tile_url(la, lo), dest):
                got.append(dest)
            else:
                print(f"  · تخطٍّ {name} (غير موجودة/بحر)")
        if not got:
            print("لا بلاطات مُنزَّلة — تحقّق من bbox/الشبكة. لا COG (بلا تلفيق).", file=sys.stderr)
            return 2
        print(f"دمج {len(got)} بلاطة → {args.out}")
        build_cog(got, args.out)
    print(f"✅ تمّ. اضبط: FIELD_DEM_PATH={args.out}  ثمّ أعِد تشغيل raster-service.")
    print("© Copernicus DEM / ESA — ذكر المصدر إلزاميّ.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
