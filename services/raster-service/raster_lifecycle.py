"""
raster_lifecycle.py — دورة حياة الراستر (سدّ فجوة: لا سياسة تنظيف).

المراجعة محقّة: أنظمة الراستر تتضخّم بسرعة (NDVI outputs, thumbnails, temp
rasters, derived products). بلا سياسة retention، التخزين ينفجر. هذه الوحدة
تنظّف النواتج المؤقّتة/المشتقّة حسب العمر، مع حماية النواتج الدائمة.

صدق: تعمل على الملفّات الفعليّة على القرص؛ تُبلّغ بما حُذف فعلاً (لا تخمين).
"""

from __future__ import annotations

import logging
import os
import time

_log = logging.getLogger("raster_lifecycle")


# سياسات الاحتفاظ الافتراضيّة (بالأيّام) — قابلة للضبط عبر env
RETENTION = {
    "temp": float(os.getenv("RASTER_TEMP_RETENTION_DAYS", "1")),  # مؤقّت
    "thumbnail": float(os.getenv("RASTER_THUMB_RETENTION_DAYS", "30")),  # مصغّرات
    "derived": float(os.getenv("RASTER_DERIVED_RETENTION_DAYS", "90")),  # مشتقّات
    # النواتج الدائمة (offline_packs، COG أصليّة) لا تُحذَف تلقائيّاً
}
PROTECTED_DIRS = {"offline_packs"}  # لا تُمَسّ أبداً


def _age_days(path: str) -> float:
    try:
        return (time.time() - os.path.getmtime(path)) / 86400.0
    except OSError:
        return 0.0


def scan_storage(upload_dir: str) -> dict:
    """يحصي التخزين: إجمالي الحجم + توزيعه (للمراقبة قبل التنظيف)."""
    total_bytes = 0
    by_type: dict[str, int] = {"tif": 0, "png": 0, "mbtiles": 0, "pmtiles": 0, "other": 0}
    file_count = 0
    if not os.path.isdir(upload_dir):
        return {"total_mb": 0, "files": 0, "by_type_mb": {}}
    for root, _dirs, files in os.walk(upload_dir):
        for fn in files:
            path = os.path.join(root, fn)
            try:
                sz = os.path.getsize(path)
            except OSError:
                continue
            total_bytes += sz
            file_count += 1
            ext = fn.rsplit(".", 1)[-1].lower() if "." in fn else "other"
            by_type[ext if ext in by_type else "other"] += sz
    return {
        "total_mb": round(total_bytes / 1e6, 1),
        "files": file_count,
        "by_type_mb": {k: round(v / 1e6, 1) for k, v in by_type.items() if v},
    }


def cleanup(upload_dir: str, dry_run: bool = True) -> dict:
    """ينظّف النواتج المنتهية حسب سياسة الاحتفاظ.

    dry_run=True (افتراضي): يُبلّغ بما سيُحذَف دون حذف فعلي (آمن). مرّر
    dry_run=False للحذف الفعلي. النواتج المحميّة (offline_packs) لا تُمَسّ.
    """
    if not os.path.isdir(upload_dir):
        return {"scanned": 0, "removed": 0, "freed_mb": 0, "dry_run": dry_run}

    removed: list[str] = []
    freed_bytes = 0
    scanned = 0

    for entry in os.listdir(upload_dir):
        full = os.path.join(upload_dir, entry)
        # تخطّى المجلّدات المحميّة
        if entry in PROTECTED_DIRS:
            continue
        # صنّف النوع حسب الاسم/الامتداد
        if entry.endswith(".tmp") or entry.startswith("tmp_"):
            kind = "temp"
        elif "thumb" in entry.lower() or entry.endswith("_thumb.png"):
            kind = "thumbnail"
        elif entry.endswith((".png", ".tif")):
            kind = "derived"
        else:
            continue  # غير معروف → لا تلمسه (محافظ)

        scanned += 1
        max_age = RETENTION.get(kind, 90)
        if _age_days(full) > max_age:
            try:
                sz = os.path.getsize(full) if os.path.isfile(full) else 0
                if not dry_run:
                    if os.path.isfile(full):
                        os.remove(full)
                removed.append(entry)
                freed_bytes += sz
            except OSError as e:
                _log.warning("تعذّر حذف ملفّ راستر قديم %s: %s", full, e)

    return {
        "scanned": scanned,
        "removed": len(removed),
        "removed_sample": removed[:10],
        "freed_mb": round(freed_bytes / 1e6, 1),
        "dry_run": dry_run,
        "note": "النواتج المحميّة (offline_packs) لا تُحذَف؛ dry_run افتراضي للأمان",
    }
