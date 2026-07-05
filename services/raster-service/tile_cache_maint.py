"""صيانة كاش بلاطات الراستر القرصيّ: تعقيم المسار + الإبطال + الإخلاء (TTL/حصّة).

مُستقلّ عن ``main.py`` (بلا FastAPI) عمداً كي يستورده عامل الإبطال بخفّة ويُختبَر
بلا تحميل التطبيق كاملاً. مصدر واحد لبنية مسار الكاش تتشاركه الكتابة (main._tile_cache_key)
والإبطال (عامل الإبطال) — فلا ينحرف الحذف عن مكان الكتابة.
"""

from __future__ import annotations

import logging
import os
import shutil
import time

logger = logging.getLogger("raster-service.tile_cache_maint")

# نفس مصدر main.UPLOAD_DIR (RASTER_UPLOAD_DIR) — يُقرأ عند الاستيراد، ويُمكن ترقيعه في الاختبار.
UPLOAD_DIR = os.getenv("RASTER_UPLOAD_DIR", "/tmp/sahool_rasters")


def safe_cache_segment(s) -> str:
    """يُعقّم مقطع مسار كاش (يمنع اجتياز الدليل): يُبقي [A-Za-z0-9_-] فقط ويطوي ``..``."""
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(s or "na"))
    return cleaned.replace("..", "_")


def tile_cache_field_dir(tenant_id: str | None, field_id: str) -> str:
    """دليل كاش بلاطات حقل بعينه: ``UPLOAD_DIR/tile_cache/<tenant>/<field>``."""
    return os.path.join(
        UPLOAD_DIR, "tile_cache", safe_cache_segment(tenant_id), safe_cache_segment(field_id)
    )


def invalidate_field_tile_cache(tenant_id: str | None, field_id: str) -> int:
    """يحذف كلّ بلاطات حقل مُخبّأة (كلّ المؤشّرات/التواريخ/الإصدارات). يُرجِع عدد
    الملفّات المحذوفة. آمن: يعمل على دليل الحقل المُعقَّم فقط، ولا يرمي (best-effort)."""
    root = tile_cache_field_dir(tenant_id, field_id)
    if not os.path.isdir(root):
        return 0
    count = 0
    for _dirpath, _dirnames, filenames in os.walk(root):
        count += len(filenames)
    try:
        shutil.rmtree(root, ignore_errors=True)
    except OSError as e:  # pragma: no cover — rmtree(ignore_errors) نادراً ما يرمي
        logger.warning("tile cache invalidate skipped (%s/%s): %s", tenant_id, field_id, e)
        return 0
    return count


def prune_tile_cache(ttl_seconds: int | None = None, max_bytes: int | None = None) -> dict:
    """إخلاء محكوم لكاش البلاطات القرصيّ (لا TTL/حصّة سابقاً — نموّ بلا حدّ).

    (١) TTL: يحذف الملفّات الأقدم من ``ttl_seconds`` (بـmtime). (٢) الحصّة: إن تجاوز
    المجموع ``max_bytes`` يحذف الأقدم أوّلاً حتّى النزول تحت الحصّة. القيم من البيئة
    عند None: ``TILE_CACHE_TTL_SECONDS`` و``TILE_CACHE_MAX_BYTES`` (0/غياب = مُعطَّل).
    يُرجِع dict إحصاءات. best-effort: لا يرمي."""
    if ttl_seconds is None:
        ttl_seconds = int(os.getenv("TILE_CACHE_TTL_SECONDS", "0") or "0")
    if max_bytes is None:
        max_bytes = int(os.getenv("TILE_CACHE_MAX_BYTES", "0") or "0")
    root = os.path.join(UPLOAD_DIR, "tile_cache")
    stats = {"deleted_ttl": 0, "deleted_quota": 0, "bytes_freed": 0, "scanned": 0}
    if not os.path.isdir(root) or (ttl_seconds <= 0 and max_bytes <= 0):
        return stats
    now = time.time()
    files: list[tuple[float, int, str]] = []  # (mtime, size, path)
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            p = os.path.join(dirpath, name)
            try:
                st = os.stat(p)
            except OSError:
                continue
            files.append((st.st_mtime, st.st_size, p))
    stats["scanned"] = len(files)
    remaining: list[tuple[float, int, str]] = []
    for mtime, size, p in files:
        if ttl_seconds > 0 and (now - mtime) > ttl_seconds:
            try:
                os.remove(p)
                stats["deleted_ttl"] += 1
                stats["bytes_freed"] += size
            except OSError:
                remaining.append((mtime, size, p))
        else:
            remaining.append((mtime, size, p))
    if max_bytes > 0:
        total = sum(sz for _m, sz, _p in remaining)
        if total > max_bytes:
            remaining.sort(key=lambda t: t[0])  # الأقدم أوّلاً
            for _mtime, size, p in remaining:
                if total <= max_bytes:
                    break
                try:
                    os.remove(p)
                    stats["deleted_quota"] += 1
                    stats["bytes_freed"] += size
                    total -= size
                except OSError:
                    continue
    return stats
