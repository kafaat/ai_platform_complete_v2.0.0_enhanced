"""Pure merging and selection of field imagery acquisition-date records.

The field router owns authorization, tenant-scoped data reads and provider I/O.
This module owns date deduplication and the scene/AOI cloud display contract.
"""

from __future__ import annotations

from datetime import datetime, timedelta


def create_date_accumulator(*, display_index, high_quality_clear_pct, min_clear_pct):
    """Return per-request records and their merge function; perform no I/O."""
    by_date: dict[str, dict] = {}

    def _clip_cloud(value):
        try:
            return max(0.0, min(100.0, float(value)))
        except (TypeError, ValueError):
            return None

    def _add(
        date_value,
        *,
        idx=None,
        has_cog=True,
        cloud_pct=None,
        aoi_cloud_pct=None,
        scene_id=None,
        acquisition_datetime=None,
    ):
        if not date_value:
            return
        d = str(date_value)[:10]
        if len(d) != 10:
            return
        rec = by_date.setdefault(
            d,
            {
                "date": d,
                "has_cog": False,
                "indices": set(),
                # عقد سحابة صريح مزدوج القيمة (AOI-CLOUD-CONTRACT):
                #  • scene_cloud_pct — سحابة المشهد كاملاً من كتالوج STAC.
                #  • aoi_cloud_pct — السحابة فوق مضلّع الحقل (AOI-clipped)؛ NULL=«لم يُحسب»
                #    (ليس 0%) — فلا يُستبعَد تاريخ نظيف فوق الحقل بسحابة مشهد عالية.
                #  • cloud_pct — يبقى توافقاً قديماً، مساوٍ لسحابة المشهد صراحةً.
                # clear_pct/quality_label تُشتقّان من القيمة الأنسب للحقل (AOI إن توفّرت).
                "cloud_pct": None,
                "scene_cloud_pct": None,
                "aoi_cloud_pct": None,
                "clear_pct": None,
                "quality_label": None,
                "scene_id": None,
                # وقت الالتقاط الحقيقيّ (ISO8601 UTC) من كتالوج STAC حين توفّره؛ يبقى None
                # (فتعرض الواجهة التاريخ وحده) إن لم يُسجَّل مشهد — لا اختلاق ساعة.
                "acquisition_datetime": None,
            },
        )
        rec["has_cog"] = bool(rec["has_cog"] or has_cog)
        if idx:
            rec["indices"].add(display_index(idx))
        scene_cloud = _clip_cloud(cloud_pct)
        aoi_cloud = _clip_cloud(aoi_cloud_pct)
        if scene_cloud is not None and rec["scene_cloud_pct"] is None:
            rec["scene_cloud_pct"] = scene_cloud
            rec["cloud_pct"] = scene_cloud  # توافق قديم: scene-level صراحةً
        if aoi_cloud is not None and rec["aoi_cloud_pct"] is None:
            rec["aoi_cloud_pct"] = aoi_cloud
        # الجودة تُشتقّ من سحابة الحقل إن حُسِبت، وإلّا من سحابة المشهد (لا نستبعد
        # تاريخاً نظيفاً فوق الحقل بسحابة مشهد وحدها).
        effective = rec["aoi_cloud_pct"] if rec["aoi_cloud_pct"] is not None else rec["cloud_pct"]
        if effective is not None:
            rec["clear_pct"] = 100.0 - effective
            rec["quality_label"] = (
                "high"
                if rec["clear_pct"] >= high_quality_clear_pct
                else "medium"
                if rec["clear_pct"] >= min_clear_pct
                else "cloudy"
            )
        if scene_id and not rec["scene_id"]:
            rec["scene_id"] = str(scene_id)
        if acquisition_datetime and not rec["acquisition_datetime"]:
            rec["acquisition_datetime"] = str(acquisition_datetime)

    return by_date, _add


def select_available_dates(
    by_date: dict[str, dict], *, cutoff: str | None, limit: int
) -> list[dict]:
    """Apply the requested timeline cutoff and return newest distinct dates first."""
    dates = []
    for rec in by_date.values():
        if cutoff is not None and rec["date"] < cutoff:
            continue
        rec["indices"] = sorted(rec["indices"])
        dates.append(rec)
    dates.sort(key=lambda r: r["date"], reverse=True)
    return dates[:limit]


def timeline_cutoff(months: int, now: datetime) -> str:
    """Use the same rolling 31-day month window for stored and provider dates."""
    # نافذة الشريط الزمنيّ: عند دمج المزوّد (نداء الشريط)، الشريط محكومٌ بالفترة
    # المختارة (months) — فلا تُعاد تواريخ **معالَجة** أقدم من النافذة، وإلّا ظهر 24
    # شهراً من backfill سابق رغم اختيار 3/6/12. النداء بلا include_provider (منتقي
    # المشهد) يبقى بلا قصّ كي يعرض كلّ المشاهد الجاهزة المخزّنة.
    return (now - timedelta(days=months * 31)).date().isoformat()
