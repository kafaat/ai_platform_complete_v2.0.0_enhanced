"""بطاقة ذكاء الحقل الموحَّدة (V65) — تجميع صادق لأوليّات موجودة في بطاقة قرار واحدة.

**الفجوة (تدقيق المراحل 9–15 / التقرير الخارجيّ P5+P9):** الأوليّات موجودة (حالة موحّدة،
حزمة أدلّة، ثقة، تنبيهات) لكن مبعثرة عبر ~10 بطاقات FieldView؛ لا بطاقة قرار **واحدة**
تجمع: أحدث مشهد · حالة المزوّدين · NDVI الحاليّ مقابل التاريخيّ · العجز المائيّ · المناطق
الضعيفة · التنبيهات · توصية الاستطلاع · قائمة الأدلّة · الثقة.

**الحلّ (منطق صرف، بلا I/O — قابل للاختبار حتميّاً):** مُجمِّع يأخذ مخرَج `analyze`
القائم + إشارات تكميليّة اختياريّة، ويبني البطاقة. **صدق حاسم:** كلّ قسم إمّا **حاضر
بقيمة** أو **مُعلَّم `missing` بسبب صريح** — لا اختلاق. `completeness` نسبة الأقسام الحاضرة.

لا يجلب بيانات ولا يستدعي خدمات؛ يستهلك ما هو مُمرَّر فقط (يبقى الجلب في المُنسّق/الراوتر).
"""

from __future__ import annotations

from typing import Any

_SCHEMA = "sahool.field_intelligence_card/1"

# أقسام بيانات اختياريّة تدخل حساب الاكتمال (توفّر إشارة). الأقسام المُشتقّة دائمة
# الحضور (risk_alerts/confidence/scouting_recommendation) لا تُحسَب — الاكتمال يعكس
# توفّر البيانات لا المخرجات المُشتقّة.
_OPTIONAL_SECTIONS = (
    "latest_scene",
    "provider_status",
    "ndvi_vs_historical",
    "water_deficit",
    "weak_zones",
    "evidence",
)


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and out not in (float("inf"), float("-inf")) else None


def _missing(reason: str) -> dict[str, Any]:
    return {"status": "missing", "reason": reason}


def _present(payload: dict[str, Any]) -> dict[str, Any]:
    return {"status": "present", **payload}


def _ndvi_vs_historical(current: Any, history: Any, *, above: float = 0.05) -> dict[str, Any]:
    cur = _num(current)
    if cur is None:
        return _missing("no_current_ndvi")
    vals = [v for v in (history or []) if _num(v) is not None] if isinstance(history, list) else []
    if len(vals) < 2:
        return _missing("insufficient_history")
    mean = sum(_num(v) for v in vals) / len(vals)  # type: ignore[misc]
    anomaly = round(cur - mean, 4)
    if anomaly > above:
        label = "above_historical"
    elif anomaly < -above:
        label = "below_historical"
    else:
        label = "near_historical"
    return _present(
        {
            "current": round(cur, 4),
            "historical_mean": round(mean, 4),
            "n_history": len(vals),
            "anomaly": anomaly,
            "label": label,
        }
    )


def _weak_zones(weak_zones: Any) -> dict[str, Any]:
    if not isinstance(weak_zones, list) or not weak_zones:
        return _missing("no_zone_data")
    weak = [
        z
        for z in weak_zones
        if isinstance(z, dict)
        and str(z.get("productivity_class", "")).lower() in {"low", "problem"}
    ]
    return _present(
        {
            "count": len(weak),
            "zone_ids": [str(z.get("zone_id")) for z in weak if z.get("zone_id") is not None],
        }
    )


def _scouting_recommendation(
    analyze: dict[str, Any], weak_section: dict[str, Any]
) -> dict[str, Any]:
    alerts = analyze.get("alerts")
    severe = 0
    if isinstance(alerts, list):
        severe = sum(
            1
            for a in alerts
            if isinstance(a, dict) and str(a.get("severity", "")).lower() in {"warning", "critical"}
        )
    weak_count = weak_section.get("count", 0) if weak_section.get("status") == "present" else 0
    if severe or weak_count:
        return _present(
            {
                "action": "scout",
                "priority": "high" if severe else "medium",
                "reason": f"{severe} alert(s), {weak_count} weak zone(s)",
            }
        )
    return _present({"action": "monitor", "priority": "low", "reason": "no active triggers"})


def _evidence(analyze: dict[str, Any]) -> dict[str, Any]:
    prov = analyze.get("provenance")
    sources: list[str] = []
    if isinstance(prov, dict):
        sources = sorted(str(k) for k in prov)
    elif isinstance(prov, list):
        sources = [str(s) for s in prov]
    if not sources:
        return _missing("no_provenance")
    return _present({"sources": sources, "count": len(sources)})


def assemble_field_intelligence_card(
    analyze: dict[str, Any],
    *,
    latest_scene: dict[str, Any] | None = None,
    provider_status: Any = None,
    ndvi_current: Any = None,
    ndvi_history: Any = None,
    water_deficit: Any = None,
    weak_zones: Any = None,
) -> dict[str, Any]:
    """يبني بطاقة ذكاء الحقل من مخرَج ``analyze`` + إشارات تكميليّة (صادق، غير جالب).

    كلّ قسم اختياريّ إمّا حاضر أو ``missing`` بسبب — لا اختلاق. ``risk_alerts``
    و``confidence`` دائماً حاضران (من ``analyze``). ``completeness`` نسبة الأقسام الحاضرة.
    """
    analyze = analyze if isinstance(analyze, dict) else {}
    truths = analyze.get("operational_truths")
    truths = truths if isinstance(truths, dict) else {}

    # NDVI الحاليّ: صريح أو من الحقائق التشغيليّة.
    cur_ndvi = ndvi_current if ndvi_current is not None else truths.get("ndvi")
    wd = water_deficit if water_deficit is not None else truths.get("water_deficit")

    sections: dict[str, Any] = {}
    sections["latest_scene"] = (
        _present(
            {
                "scene_id": latest_scene.get("scene_id"),
                "acquisition_date": latest_scene.get("acquisition_date"),
                "provider": latest_scene.get("provider"),
                "cloud_cover": latest_scene.get("cloud_cover"),
                "cog_ready": latest_scene.get("cog_ready"),
            }
        )
        if isinstance(latest_scene, dict) and latest_scene.get("scene_id")
        else _missing("no_scene_supplied")
    )
    sections["provider_status"] = (
        _present({"providers": provider_status})
        if provider_status
        else _missing("no_provider_status_supplied")
    )
    sections["ndvi_vs_historical"] = _ndvi_vs_historical(cur_ndvi, ndvi_history)
    sections["water_deficit"] = (
        _present({"value": _num(wd)})
        if _num(wd) is not None
        else _missing("no_water_deficit_signal")
    )
    sections["weak_zones"] = _weak_zones(weak_zones)
    sections["evidence"] = _evidence(analyze)
    sections["scouting_recommendation"] = _scouting_recommendation(analyze, sections["weak_zones"])

    # أقسام دائمة الحضور (لا تدخل الاكتمال كاختياريّة).
    alerts = analyze.get("alerts") if isinstance(analyze.get("alerts"), list) else []
    risk_alerts = {
        "count": len(alerts),
        "top_severity": _top_severity(alerts),
        "items": alerts,
    }
    confidence = {
        "value": analyze.get("confidence"),
        "reason": analyze.get("confidence_reason"),
    }

    present = [s for s in _OPTIONAL_SECTIONS if sections[s].get("status") == "present"]
    missing = [s for s in _OPTIONAL_SECTIONS if sections[s].get("status") != "present"]
    completeness = round(len(present) / len(_OPTIONAL_SECTIONS), 3)

    return {
        "schema": _SCHEMA,
        "field_id": analyze.get("field_id"),
        "generated_at": analyze.get("generated_at"),
        "sections": {**sections, "risk_alerts": risk_alerts, "confidence": confidence},
        "completeness": completeness,
        "missing_sections": missing,
    }


def _top_severity(alerts: list[Any]) -> str | None:
    order = {"info": 0, "notice": 1, "warning": 2, "critical": 3}
    best = -1
    best_label: str | None = None
    for a in alerts:
        if isinstance(a, dict):
            sev = str(a.get("severity", "")).lower()
            if order.get(sev, -1) > best:
                best = order[sev]
                best_label = sev
    return best_label
