"""bulletin_figure.py — تحويل النشرة الإقليميّة إلى شكل نشر تصنيفيّ (الشريحة C) — منطق صرف.

يأخذ مخرَج ``core.regional_bulletin.build_regional_bulletin`` (محافظة→مديريّات، حالة NDVI)
ويشتقّ صفوف عرض + ألوان الحالة + فحوص ذاتيّة. **صدق حاسم:** هذا **شكل تصنيفيّ لا خريطة
جغرافيّة** — لا توجد حدود إداريّة (choropleth) في المستودع، فلا نُلفِّق جغرافيا. المجموعات
المكتومة للخصوصيّة تبقى «مكتوم» بلا أرقام (نحترم أرضيّة الخصوصيّة في النشرة).
"""

from __future__ import annotations

from typing import Any

# ألوان الحالة (نمط GEOGLAM): استثنائيّة→ضعيفة. المكتوم/المجهول رماديّ (لا إيحاء بقيمة).
CONDITION_COLORS: dict[str, str] = {
    "exceptional": "#1a9850",
    "favourable": "#a6d96a",
    "watch": "#fee08b",
    "poor": "#d73027",
    "unknown": "#cccccc",
    "suppressed": "#9e9e9e",
}
_CONDITION_AR = {
    "exceptional": "استثنائيّة",
    "favourable": "جيّدة",
    "watch": "مراقبة",
    "poor": "ضعيفة",
    "unknown": "مجهولة",
    "suppressed": "مكتوم (خصوصيّة)",
}


def _row(gov: str, dist: str | None, group: dict[str, Any]) -> dict[str, Any]:
    suppressed = group.get("status") == "suppressed_for_privacy"
    cond = "suppressed" if suppressed else str(group.get("condition") or "unknown")
    return {
        "governorate": gov,
        "district": dist,
        "level": "district" if dist is not None else "governorate",
        "status": group.get("status"),
        "condition": cond,
        "condition_ar": _CONDITION_AR.get(cond, cond),
        "color": CONDITION_COLORS.get(cond, CONDITION_COLORS["unknown"]),
        # صدق: المكتوم بلا قيمة رقميّة (لا تسريب)؛ المنشور يحمل شذوذه.
        "mean_ndvi_anomaly": None if suppressed else group.get("mean_ndvi_anomaly"),
        "label": _CONDITION_AR["suppressed"] if suppressed else _CONDITION_AR.get(cond, cond),
    }


def bulletin_to_rows(bulletin: Any) -> list[dict[str, Any]]:
    """يُسطِّح النشرة إلى صفوف عرض (محافظة ثمّ مديريّاتها). مدخل شاذّ ⇒ قائمة فارغة."""
    if not isinstance(bulletin, dict):
        return []
    rows: list[dict[str, Any]] = []
    for gov in bulletin.get("governorates") or []:
        if not isinstance(gov, dict) or not gov.get("governorate"):
            continue
        gname = str(gov["governorate"])
        rows.append(_row(gname, None, gov))
        for dist in gov.get("districts") or []:
            if isinstance(dist, dict) and dist.get("district"):
                rows.append(_row(gname, str(dist["district"]), dist))
    return rows


def _result(name: str, severity: str, passed: bool | None, detail: str) -> dict[str, Any]:
    return {"name": name, "severity": severity, "passed": passed, "detail": detail}


def bulletin_self_checks(bulletin: Any) -> dict[str, Any]:
    """فحوص ذاتيّة للنشرة: وجود محافظات + احترام الخصوصيّة + إعلان «تصنيفيّ لا جغرافيّ».

    ``admin_geometry_present`` **دائماً متخطٍّ بسبب** (لا حدود ⇒ ليست خريطة) — إعلان صادق
    لا فشل. ``privacy_floor_respected`` **required**: أيّ مجموعة مكتومة تُسرِّب رقماً ⇒ فشل.
    """
    b = bulletin if isinstance(bulletin, dict) else {}
    govs = b.get("governorates") or []
    checks = [_result("has_governorates", "required", bool(govs), f"{len(govs)} محافظة")]

    # الخصوصيّة: كلّ مجموعة suppressed يجب ألّا تحمل mean_ndvi_anomaly/condition.
    leaks: list[str] = []

    def _scan(group: dict[str, Any], name: str) -> None:
        if group.get("status") == "suppressed_for_privacy" and (
            group.get("mean_ndvi_anomaly") is not None or group.get("condition") is not None
        ):
            leaks.append(name)

    for gov in govs:
        if not isinstance(gov, dict):
            continue
        _scan(gov, str(gov.get("governorate")))
        for dist in gov.get("districts") or []:
            if isinstance(dist, dict):
                _scan(dist, f"{gov.get('governorate')}/{dist.get('district')}")
    checks.append(
        _result(
            "privacy_floor_respected",
            "required",
            not leaks,
            "لا تسريب" if not leaks else f"تسريب في: {leaks}",
        )
    )
    checks.append(
        _result(
            "admin_geometry_present",
            "quality",
            None,
            "لا حدود إداريّة — شكل تصنيفيّ لا choropleth جغرافيّ (تخطٍّ صادق)",
        )
    )
    failed_req = [c for c in checks if c["severity"] == "required" and c["passed"] is False]
    failed_q = [c for c in checks if c["severity"] == "quality" and c["passed"] is False]
    quality = "failed" if failed_req else ("degraded" if failed_q else "good")
    return {
        "checks": checks,
        "passed": not failed_req,
        "quality": quality,
        "n_failed_required": len(failed_req),
        "n_failed_quality": len(failed_q),
    }
