"""Pure merging and selection of field imagery acquisition-date records.

The field router owns authorization, tenant-scoped data reads and provider I/O.
This module owns date deduplication and the scene/AOI cloud display contract.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta


def utc_instant(value) -> datetime | None:
    """ISO8601 timestamp ⇒ ``datetime`` بـUTC؛ غير صالح/فارغ ⇒ None.

    طابع بلا منطقة يُعامَل UTC (عقد STAC). لا تُختلَق ساعة: التاريخ اليوميّ وحده ليس لحظة.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        instant = value
    elif isinstance(value, date) or len(str(value).strip()) == 10:
        return None
    else:
        try:
            instant = datetime.fromisoformat(str(value).strip())
        except ValueError:
            return None
    if instant.tzinfo is None:
        return instant.replace(tzinfo=UTC)
    return instant.astimezone(UTC)


def utc_day(value) -> str | None:
    """يوم الالتقاط بـUTC (``YYYY-MM-DD``) من تاريخ أو طابع ISO8601؛ غير صالح ⇒ None.

    T4 (acq-provenance): قصّ أوّل 10 محارف كان يُجمِّع ``2026-10-01T00:30:00+03:00`` تحت
    1 أكتوبر بينما يومه بـUTC هو 30 سبتمبر. نُحلّل المنطقة الزمنيّة ثمّ نأخذ يوم UTC.
    """
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and len(value.strip()) == 10:
        try:
            return date.fromisoformat(value.strip()).isoformat()
        except ValueError:
            return None
    instant = utc_instant(value)
    return instant.date().isoformat() if instant is not None else None


def create_date_accumulator(*, display_index, high_quality_clear_pct, min_clear_pct):
    """Return per-request records and their merge function; perform no I/O."""
    by_date: dict[str, dict] = {}
    # T1 (acq-provenance): خصائص المشهد لكلّ يوم تأتي من **مساهم ممثِّل واحد** — لا أوّل
    # قيمة غير فارغة لكلّ خاصّية مستقلّةً (كان ذلك يُلصِق scene_id من A بوقت وسحابة B).
    # ترتيب الممثِّل (الأصغر أفضل): المُدَام (has_cog) أوّلاً لأنّ صورة البطاقة منه، ثمّ
    # أدنى سحابة صالحة (AOI إن حُسِبت وإلّا المشهد)، ثمّ أحدث وقت التقاط، ثمّ الأغنى نَسَباً
    # (AOI · وقت · scene_id)؛ التعادل التامّ للأسبق.
    # مساهمو **المشهد نفسه** (scene_id واحد — مثل الطبقة في الذاكرة وصفّ القاعدة للأصل ذاته)
    # يُدمَجون أوّلاً: كلٌّ يُكمِل ما ينقص الآخر — ذلك ليس خلطاً لأنّه مشهد واحد — ثمّ يُرتَّب
    # المشهد المدموج مع غيره من جديد (لا ممثِّل بقيمة أبطلها مشهده نفسه).
    scenes_by_date: dict[str, dict] = {}

    def _clip_cloud(value):
        try:
            return max(0.0, min(100.0, float(value)))
        except (TypeError, ValueError):
            return None

    def _effective_cloud(scene):
        # الجودة تُشتقّ من سحابة الحقل إن حُسِبت، وإلّا من سحابة المشهد (لا نستبعد
        # تاريخاً نظيفاً فوق الحقل بسحابة مشهد وحدها).
        aoi = scene["aoi_cloud_pct"]
        return aoi if aoi is not None else scene["scene_cloud_pct"]

    def _rank(scene):
        effective = _effective_cloud(scene)
        instant = utc_instant(scene["acquisition_datetime"])
        return (
            not scene["has_cog"],
            effective is None,
            effective if effective is not None else 0.0,
            -instant.timestamp() if instant is not None else float("inf"),
            (scene["aoi_cloud_pct"] is None) + (instant is None) + (scene["scene_id"] is None),
            scene["order"],
        )

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
        d = utc_day(date_value)
        if d is None:
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
                # عدد المساهمين (أصول/عناصر كتالوج) المدموجين في هذا اليوم.
                "contributors": 0,
            },
        )
        rec["contributors"] += 1
        rec["has_cog"] = bool(rec["has_cog"] or has_cog)
        if idx:
            rec["indices"].add(display_index(idx))
        scenes = scenes_by_date.setdefault(d, {})
        order = rec["contributors"]
        sid = str(scene_id) if scene_id else None
        # مساهم بلا scene_id لا يُنسَب إلى مشهد غيره: مجموعة خاصّة به.
        scene = scenes.setdefault(
            sid if sid is not None else ("", order),
            {
                "order": order,
                "has_cog": False,
                "scene_cloud_pct": None,
                "aoi_cloud_pct": None,
                "scene_id": sid,
                "acquisition_datetime": None,
            },
        )
        scene["has_cog"] = bool(scene["has_cog"] or has_cog)
        # المشهد نفسه: نملأ الناقص فقط، ولا نستبدل قيمة معروفة.
        for key, value in (
            ("scene_cloud_pct", _clip_cloud(cloud_pct)),
            ("aoi_cloud_pct", _clip_cloud(aoi_cloud_pct)),
            ("acquisition_datetime", str(acquisition_datetime) if acquisition_datetime else None),
        ):
            if scene[key] is None:
                scene[key] = value

        best = min(scenes.values(), key=_rank)
        scene_cloud = best["scene_cloud_pct"]
        aoi_cloud = best["aoi_cloud_pct"]
        effective = _effective_cloud(best)
        rec["scene_cloud_pct"] = scene_cloud
        rec["cloud_pct"] = scene_cloud  # توافق قديم: scene-level صراحةً
        rec["aoi_cloud_pct"] = aoi_cloud
        rec["clear_pct"] = 100.0 - effective if effective is not None else None
        rec["quality_label"] = (
            None
            if effective is None
            else "high"
            if rec["clear_pct"] >= high_quality_clear_pct
            else "medium"
            if rec["clear_pct"] >= min_clear_pct
            else "cloudy"
        )
        rec["scene_id"] = best["scene_id"]
        # لا يُستبدَل وقت التقاط مجهول بوقت مشهد آخر ولا بوقت معالجة.
        rec["acquisition_datetime"] = best["acquisition_datetime"]

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
