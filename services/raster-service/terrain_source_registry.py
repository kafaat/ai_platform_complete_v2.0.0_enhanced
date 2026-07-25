"""terrain_source_registry.py — سجل مصادر التضاريس متعدّد الدقّة + resolver + lineage.

TERRAIN (قرار المالك): أساسٌ عالميّ مجانيّ 30م (Copernicus GLO-30) مع دعم خرائط 10م/5م
موثّقة عند تزويدها. لا ملف DEM واحد صلب — الخدمة تقرأ سجلّ ``config/terrain_sources.yml``
ويختار المُحلِّل (resolver) أعلى مصدر صالح يغطّي الحقل بالأولويّة: 5م → 10م → 30م.

صدق صارم (منع دقّة وهميّة):
  • ``native_resolution_m`` (الدقّة الأصلية للمصدر) مستقلّ عن ``storage_pixel_size_m``
    (حجم بكسل التخزين/العرض). GLO-30 المُعاد أخذ عيّناته إلى 5م يبقى
    ``effective_resolution_m = 30`` و``is_upsampled = true``.
  • ``effective_resolution_m = max(native, storage)`` — لا يُدَّعى أدقّ من الأصل أبداً.
  • كلّ نتيجة تضاريس تحمل ``terrain_source`` lineage (المصدر + الدقّتان + المرجع الرأسيّ
    + التحقّق) كي لا يظنّ المستهلِك أنّ 30م هي 5م.

هذه الوحدة منطق نقيّ (بلا rasterio/numpy) — تُختبَر كوحدة؛ التصيير الفعليّ في
``terrain_render``/``terrain_analysis`` يستهلك المصدر المُحَلَّل.
"""

from __future__ import annotations

import os
from pathlib import Path

# مسار السجل الافتراضيّ (قابل للتجاوز عبر env للاختبار/النشر).
_DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "terrain_sources.yml"

# الحالات التي تُعتبر «قابلة للاستعمال» عند الحلّ (active=الأساس المعتمد · validated=مصدر مزوّد مُتحقَّق).
_USABLE_STATUSES = ("active", "validated")


def _config_path() -> Path:
    # افتراضيّ داخليّ: عند غياب/فراغ المتغيّر نستعمل السجلّ المُحزَّم (لا متغيّر تشغيل إلزاميّ).
    override = os.getenv("TERRAIN_SOURCES_CONFIG", "").strip()
    return Path(override) if override else _DEFAULT_CONFIG


def effective_resolution_m(native_resolution_m: float, storage_pixel_size_m: float | None) -> float:
    """الدقّة الفعّالة = max(الأصلية, التخزينيّة) — لا نُدّعي أدقّ من المصدر الأصليّ (منع upsample وهميّ)."""
    native = float(native_resolution_m)
    if storage_pixel_size_m is None:
        return native
    return max(native, float(storage_pixel_size_m))


def is_upsampled(native_resolution_m: float, storage_pixel_size_m: float | None) -> bool:
    """صحيح حين التخزين أدقّ من الأصل (إعادة أخذ عيّنات صاعدة) — الدقّة الحقيقيّة تبقى الأصلية."""
    if storage_pixel_size_m is None:
        return False
    return float(storage_pixel_size_m) < float(native_resolution_m)


def load_terrain_sources(
    config_path: str | os.PathLike | None = None,
    field_dem_path: str | None = None,
) -> list[dict]:
    """يحمّل مصادر التضاريس من YAML، ويطوي ``FIELD_DEM_PATH`` كأساس مُزوَّد (توافق للخلف).

    غياب/تعذّر السجل ⇒ قائمة فارغة (المسار يبقى fail-closed صادق). لا اختلاق مصدر.
    """
    sources: list[dict] = []
    path = Path(config_path) if config_path else _config_path()
    try:
        import yaml

        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for s in raw.get("sources", []) or []:
            if isinstance(s, dict) and s.get("id"):
                sources.append(dict(s))
    except (FileNotFoundError, OSError):
        sources = []
    except Exception:  # noqa: BLE001 — سجلّ تالف لا يُسقط الخدمة؛ يُدهور إلى fail-closed
        sources = []

    # توافق للخلف: ملفّ FIELD_DEM_PATH موجود ⇒ يُزوِّد الأساس العالميّ (GLO-30) تلقائيّاً.
    dem = field_dem_path if field_dem_path is not None else os.getenv("FIELD_DEM_PATH")
    if dem and os.path.isfile(dem):
        baseline = next((s for s in sources if s.get("id") == "copernicus-glo30"), None)
        if baseline is not None:
            baseline["provisioned"] = True
            baseline["uri"] = dem
        else:
            sources.append(
                {
                    "id": "field-dem-path",
                    "model_type": "DEM",
                    "native_resolution_m": float(os.getenv("FIELD_DEM_NATIVE_RES_M", "30")),
                    "coverage_type": "global",
                    "source_kind": "public_baseline",
                    "priority": 100,
                    "status": "active",
                    "provisioned": True,
                    "uri": dem,
                }
            )
    return sources


def _bbox_covers(coverage_bbox: list | None, field_bbox: list | None) -> bool:
    """هل تحتوي تغطية المصدر مربّعَ إحاطة الحقل كاملاً؟ (للمصادر selected_areas)."""
    if not field_bbox or len(field_bbox) != 4:
        return False
    if not coverage_bbox or len(coverage_bbox) != 4:
        return False
    cminx, cminy, cmaxx, cmaxy = (float(v) for v in coverage_bbox)
    fminx, fminy, fmaxx, fmaxy = (float(v) for v in field_bbox)
    return cminx <= fminx and cminy <= fminy and cmaxx >= fmaxx and cmaxy >= fmaxy


def _source_usable_for(source: dict, field_bbox: list | None) -> bool:
    """مصدر صالح للحلّ: مُزوَّد + حالة قابلة + يغطّي الحقل (عالميّ دائماً، أو bbox يحتوي)."""
    if not source.get("provisioned"):
        return False
    if str(source.get("status")) not in _USABLE_STATUSES:
        return False
    if not source.get("uri"):
        return False
    if source.get("coverage_type") == "global":
        return True
    # selected_areas: يجب أن تحتوي تغطيته المُعلَنة مربّعَ إحاطة الحقل كاملاً.
    return _bbox_covers(source.get("coverage_bbox"), field_bbox)


def terrain_lineage(source: dict, storage_pixel_size_m: float | None = None) -> dict:
    """يبني كتلة nasab (lineage) صادقة لمصدر مُحَلَّل — تُلحَق بكلّ نتيجة تضاريس."""
    native = float(source.get("native_resolution_m") or 30.0)
    return {
        "terrain_source_id": source.get("id"),
        "model_type": source.get("model_type"),
        "native_resolution_m": native,
        "effective_resolution_m": effective_resolution_m(native, storage_pixel_size_m),
        "is_upsampled": is_upsampled(native, storage_pixel_size_m),
        "vertical_datum": source.get("vertical_datum"),
        "horizontal_crs": source.get("horizontal_crs"),
        "source_kind": source.get("source_kind"),
        "source_version": source.get("source_version"),
        "validated": str(source.get("status")) in _USABLE_STATUSES,
    }


def resolve_terrain_source(
    sources: list[dict],
    field_bbox: list | None = None,
    tenant_id: str | None = None,
    requested_product: str = "terrain",
) -> dict:
    """يختار أعلى مصدر صالح يغطّي الحقل (5م → 10م → 30م) ويُرجِع مظروف حلّ صادقاً.

    ``{resolved: bool, dem_path, native_resolution_m, lineage, reason}``. لا مصدر مُزوَّد
    يغطّي الحقل ⇒ ``resolved=false`` بسبب صريح (يُبقي المسار fail-closed / OPERATOR_BLOCKED).
    """
    candidates = [s for s in sources if _source_usable_for(s, field_bbox)]
    if not candidates:
        # صدق: لا مصدر مُزوَّد — نُعلن الأساس المعروف (إن وُجد) كـ«مدعوم غير مُزوَّد».
        baseline = next(
            (s for s in sources if s.get("id") == "copernicus-glo30"),
            None,
        )
        return {
            "resolved": False,
            "dem_path": None,
            "native_resolution_m": float(baseline.get("native_resolution_m")) if baseline else None,
            "lineage": None,
            "reason": "no_provisioned_terrain_source_covers_field",
        }
    # أعلى أولويّة أوّلاً؛ التعادل يُحسَم بالدقّة الأصلية الأدقّ (native أصغر).
    chosen = sorted(
        candidates,
        key=lambda s: (int(s.get("priority") or 0), -float(s.get("native_resolution_m") or 1e9)),
        reverse=True,
    )[0]
    native = float(chosen.get("native_resolution_m") or 30.0)
    return {
        "resolved": True,
        "dem_path": chosen.get("uri"),
        "native_resolution_m": native,
        "lineage": terrain_lineage(chosen, storage_pixel_size_m=None),
        "reason": None,
    }


# ── Terrain-RGB (ترميز Mapbox القياسيّ للارتفاع) — منطق نقيّ يستهلكه التصيير ────────────
# height = -10000 + ((R*256*256 + G*256 + B) * 0.1)  — تباعد 0.1م، مدى ~[-10000, +1667721.5]
_TERRAIN_RGB_BASE = -10000.0
_TERRAIN_RGB_STEP = 0.1


def encode_terrain_rgb(elevation_m: float) -> tuple[int, int, int]:
    """يُرمِّز ارتفاعاً (م) إلى (R,G,B) بمواصفة Terrain-RGB. ترميزٌ للارتفاع لا رفعٌ للدقّة."""
    v = round((float(elevation_m) - _TERRAIN_RGB_BASE) / _TERRAIN_RGB_STEP)
    v = max(0, min(v, 256 * 256 * 256 - 1))
    r = (v >> 16) & 0xFF
    g = (v >> 8) & 0xFF
    b = v & 0xFF
    return r, g, b


def decode_terrain_rgb(r: int, g: int, b: int) -> float:
    """يفكّ (R,G,B) إلى ارتفاع (م) — عكس :func:`encode_terrain_rgb` (لاختبار الاستدارة)."""
    return _TERRAIN_RGB_BASE + ((int(r) * 65536 + int(g) * 256 + int(b)) * _TERRAIN_RGB_STEP)


def terrain_rgb_metadata(lineage: dict | None) -> dict:
    """metadata لبلاطة Terrain-RGB — يحفظ الدقّة الأصلية (لا يرفعها الترميز) صراحةً."""
    lin = lineage or {}
    return {
        "encoding": "terrain-rgb",
        "base_m": _TERRAIN_RGB_BASE,
        "step_m": _TERRAIN_RGB_STEP,
        # الترميز لا يرفع الدقّة: الدقّة الفعّالة تبقى من المصدر الأصليّ.
        "native_resolution_m": lin.get("native_resolution_m"),
        "effective_resolution_m": lin.get("effective_resolution_m"),
        "is_upsampled": lin.get("is_upsampled", False),
        "terrain_source_id": lin.get("terrain_source_id"),
    }


def resolution_policy(sources: list[dict]) -> dict:
    """ملخّص سياسة الدقّة للحالة/التوثيق — الأساس + المصادر الاختياريّة وحالة تزويدها."""
    baseline = next((s for s in sources if s.get("coverage_type") == "global"), None)
    optional = [s for s in sources if s.get("coverage_type") != "global"]
    return {
        "baseline": None
        if baseline is None
        else {
            "dataset": baseline.get("id"),
            "native_resolution_m": baseline.get("native_resolution_m"),
            "role": "global_fallback",
            "provisioned": bool(baseline.get("provisioned")),
        },
        "optional_sources": [
            {
                "native_resolution_m": s.get("native_resolution_m"),
                "status": s.get("status"),
                "provisioned": bool(s.get("provisioned")),
            }
            for s in optional
        ],
        "selection_policy": ["validated_5m", "validated_10m", "glo30_30m"],
    }
