"""
api/decision_engine.py — محرّك القرار الزراعي الموحّد (عقل الحقل)

الطبقة التي تتوّج المنظومة: تربط كلّ الوحدات في تدفّق قرار واحد. بدل أن
يستعلم المزارع عن كلّ وحدة منفصلة، يُدخل موقع حقله وبياناته الأساسيّة فيحصل
على **قرار متكامل**: ماذا يزرع، لماذا، متى، وما المخاطر والخطوات.

التدفّق المنسّق (orchestration):
  الموقع (GPS/محافظة) → الإقليم المناخي → المحاصيل الملائمة
    → فحص ملاءمة الحقل (تربة/ملوحة) → المخاطر الموسميّة
    → الدليل العالمي (للصحراء) → التوصية المرتّبة + الخطوات

هذا ليس وحدةً جديدةً بمعرفة جديدة، بل **منسّق (orchestrator)** يستدعي
الوحدات الموجودة ويجمع مخرجاتها في قرار واحد متماسك. لا يكرّر منطقاً.

⚠ القرار النهائي للمزارع. المحرّك يرتّب الخيارات بشفافيّة (لماذا) لا يفرضها.
كلّ مكوّن يحمل تنويهه. التربة والسوق المحلّي والخبرة الميدانيّة حاسمة.
"""
from __future__ import annotations

from typing import Dict, Optional


def decide_for_location(
    location: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    elevation_m: Optional[float] = None,
    soil_ph: Optional[float] = None,
    soil_ec_dsm: Optional[float] = None,
    area_ha: Optional[float] = None,
) -> Dict:
    """قرار زراعي متكامل لحقل من موقعه وبياناته الأساسيّة.

    يُدخل المزارع إمّا اسم محافظة/مديريّة أو إحداثيّات GPS (+ارتفاع)،
    واختياريّاً تربة (pH/EC) ومساحة. يُخرج المحرّك قراراً مرتّباً.
    """
    result: Dict = {"supported": True, "steps_ar": []}

    # ── الخطوة ١: تحديد الإقليم المناخي ──
    zone_key = None
    zone_info = None
    if lat is not None and lon is not None:
        from api.geo_zone_locator import locate_field
        loc = locate_field(lat, lon, elevation_m)
        if loc.get("supported"):
            zone_key = loc.get("zone")
            zone_info = loc
            result["location_ar"] = {
                "method": "GPS", "governorate_ar": loc.get("governorate_ar"),
                "zone_name_ar": loc.get("zone_name_ar"),
                "climate_ar": loc.get("climate_ar"),
            }
            result["steps_ar"].append("① حُدّد الإقليم من إحداثيّات الحقل")
            if loc.get("multi_zone_warning_ar"):
                result["location_warning_ar"] = loc["multi_zone_warning_ar"]
        else:
            return {"supported": False, "message_ar": loc.get("message_ar")}
    elif location:
        from api.agro_climate_zones import identify_zone_v2
        idz = identify_zone_v2(location, elevation_m)
        if idz.get("supported"):
            zone_key = idz.get("zone")
            zone_info = idz
            result["location_ar"] = {
                "method": "اسم", "input_ar": location,
                "zone_name_ar": idz.get("name_ar"),
                "climate_ar": idz.get("climate_ar"),
            }
            result["steps_ar"].append("① حُدّد الإقليم من اسم الموقع")
        else:
            # محافظة متعدّدة الأقاليم تحتاج تحديداً
            return {
                "supported": False,
                "needs_clarification_ar": idz.get("message_ar"),
                "example_districts_ar": idz.get("example_districts_ar"),
            }
    else:
        return {"supported": False,
                "message_ar": "أدخل موقعاً (اسم محافظة/مديريّة) أو إحداثيّات GPS."}

    if not zone_key:
        return {"supported": False, "message_ar": "تعذّر تحديد الإقليم."}

    # ── الخطوة ٢: المحاصيل الملائمة للإقليم + التنبيه المائي ──
    from api.agro_climate_zones import suited_for_zone
    suited = suited_for_zone(zone_key)
    result["suited_crops_ar"] = suited.get("suited_crops_ar")
    result["avoid_ar"] = suited.get("avoid_ar")
    result["water_strategy_ar"] = suited.get("water_note_ar")
    result["rainfed_possible"] = suited.get("rainfed_possible")
    result["steps_ar"].append("② جُلبت محاصيل الإقليم الملائمة + استراتيجيّة الماء")

    # ── الخطوة ٣: الدليل العالمي (للصحراء الداخليّة فقط) ──
    from api.climate_analogs import analogs_for_zone, strategic_tiers
    analogs = analogs_for_zone(zone_key)
    if analogs.get("applicable"):
        result["global_evidence_ar"] = {
            "regions_ar": analogs.get("analog_regions_ar"),
            "evidence_ar": analogs.get("evidence_ar"),
            "strategic_crops_ar": analogs.get("proven_strategic_crops_ar"),
            "direction_ar": analogs.get("strategic_direction_ar"),
        }
        # التصنيف الاستراتيجي (أشجار أساسيّة أوّلاً)
        tiers = strategic_tiers()
        result["strategic_tiers_ar"] = {
            t: [c["crop_ar"] for c in crops]
            for t, crops in list(tiers["tiers"].items())[:2]  # أعلى فئتين
        }
        # نموذج البستان المختلط الاستثماري (للصحراء — لوز/زيتون/فستق)
        from api.orchard_planner import mixed_orchard_plan
        _orchard = mixed_orchard_plan(area_ha or 1.0)
        if _orchard.get("supported"):
            result["mixed_orchard_ar"] = {
                "model_ar": _orchard["model_ar"],
                "blocks_summary_ar": [
                    f"{b['crop_ar']}: {b['trees']} شجرة ({b['role_ar']})"
                    for b in _orchard["blocks"]
                ],
                "strategy_ar": _orchard["strategy_ar"],
                "arid_warning_ar": _orchard["arid_warning_ar"],
            }
        result["steps_ar"].append("③ أُرفق الدليل العالمي + التصنيف الاستراتيجي + نموذج البستان (صحراء)")
        # طبقات الفرص عالية القيمة (للصحراء — موثّقة)
        from api.high_value_crops import list_high_value_crops
        from api.niche_export_crops import list_niche_crops
        _hv = list_high_value_crops()
        result["high_value_opportunities_ar"] = {
            "top_3_ar": _hv.get("top_3_for_jawf_ar"),
            "note_ar": "محاصيل عالية القيمة مثبتة للصحراء — راجع /high-value-crops للتفصيل.",
        }
        _niche = list_niche_crops()
        result["niche_export_opportunities_ar"] = {
            "top_3_ar": _niche.get("top_opportunities_ar"),
            "yemen_edge_ar": _niche.get("yemen_heritage_edge_ar"),
            "note_ar": "منتجات تصديريّة متخصّصة — راجع /niche-crops للتفصيل.",
        }

    # ── الخطوة ٤: المخاطر الموسميّة + ساعات البرودة ──
    from api.seasonal_risk import zone_risk_calendar, chill_hours_estimate
    risk = zone_risk_calendar(zone_key)
    if risk.get("supported"):
        high_risks = [h["hazard_ar"] for h in risk["hazards"]
                      if h["severity"] == "high"]
        result["seasonal_risks_ar"] = {
            "high_severity_ar": high_risks,
            "advice_ar": risk.get("advice_ar"),
        }
    chill = chill_hours_estimate(zone_key)
    if chill.get("supported"):
        result["chill_hours_ar"] = {
            "estimated": chill["estimated_chill_hours"],
            "verdict_ar": chill["verdict_ar"],
        }
    # بيانات طقس فعليّة مرجعيّة (للجوف — من 5 سنوات NASA POWER موثّقة)
    if zone_key == "inland_desert":
        _ref = _load_jawf_climate_ref()
        if _ref:
            result["actual_climate_data_ar"] = {
                "source_ar": _ref.get("source"),
                "annual_rainfall_mm": _ref.get("annual_rainfall_mm"),
                "heat_stress_days_per_year": _ref.get("heat_stress_days_per_year"),
                "temp_record_ar": f"سُجّل من {_ref.get('temp_min_record')}° إلى "
                                  f"{_ref.get('temp_max_record')}°م",
                "note_ar": (
                    "بيانات فعليّة (5 سنوات) لا تقديرات — "
                    f"~{_ref.get('heat_stress_days_per_year')} يوم إجهاد حراري/سنة، "
                    "خطّط لتجنّب الإزهار في الذروة."
                ),
            }
    result["steps_ar"].append("④ قُيّمت المخاطر الموسميّة + ساعات البرودة")

    # ── الخطوة ٥: فحص ملاءمة الحقل المحدّد (إن توفّرت التربة) ──
    if soil_ph is not None or soil_ec_dsm is not None:
        result["field_fit_note_ar"] = (
            f"بيانات حقلك (pH={soil_ph}, EC={soil_ec_dsm}) — افحص ملاءمة "
            "محصول محدّد عبر محرّك الملاءمة (crop-suitability) للحصول على "
            "نتيجة كمّيّة. "
        )
        # تنبيه ملوحة مبكّر
        if soil_ec_dsm is not None and soil_ec_dsm >= 4:
            result["salinity_alert_ar"] = (
                f"⚠ ملوحة مرتفعة (EC={soil_ec_dsm}) — اختر محاصيل/أصولاً "
                "متحمّلة (نخيل/زيتون/رمّان) وراجع وحدة إدارة الملوحة."
            )
        if soil_ph is not None and soil_ph >= 7.8:
            result["alkalinity_alert_ar"] = (
                f"⚠ قلويّة عالية (pH={soil_ph}) — تثبيت الفوسفور/الحديد/الزنك "
                "محتمل. راجع برنامج التسميد (4R)."
            )
            # إرشاد موثّق من دراسة السنيدار الحكوميّة (نفس ظروف الجوف القلويّة)
            if zone_key == "inland_desert":
                result["sunaydar_guidance_ar"] = (
                    "بيانات السنيدار الأرضيّة (شرق الحزم، pH~8.2، كلس 31%) تؤكّد "
                    "هذا النمط. توصيات الدراسة الحكوميّة: فوسفور عالٍ عند الزراعة "
                    "(لمواجهة التثبيت) + سماد عضوي لرفع المادة العضوية + رشّ "
                    "حديد/زنك ورقي (chelated) + ريّ تنقيط لتفادي ترسّب الأملاح."
                )
        result["steps_ar"].append("⑤ فُحصت بيانات التربة (تنبيهات ملوحة/قلويّة)")

    # ── الخطوة ٦: اعتبار المساحة (إن توفّرت) ──
    if area_ha is not None:
        if area_ha < 2:
            scale_ar = "حقل صغير — مناسب لمحاصيل عالية القيمة/زراعة محميّة."
        elif area_ha > 50:
            scale_ar = "حقل كبير — يحتمل المكننة (حبوب/أعلاف) + مناطق متخصّصة."
        else:
            scale_ar = "حقل متوسّط — مرونة في المزج بين الأشجار والمحاصيل."
        result["area_note_ar"] = f"{area_ha} هكتار: {scale_ar}"
        result["steps_ar"].append("⑥ روعيت مساحة الحقل")

    # ── القرار المجمّع ──
    result["decision_summary_ar"] = _build_summary(zone_key, suited, analogs,
                                                   chill, soil_ec_dsm)
    result["next_actions_ar"] = [
        "افحص ملاءمة محصولك المختار لحقلك (محرّك الملاءمة)",
        "قدّر الجدوى الاقتصاديّة (وحدة الاقتصاد الزراعي)",
        "حدّد موعد الزراعة الأمثل (تقويم الزراعة)",
        "خطّط الإكثار والريّ (الإكثار + ميزان الماء)",
    ]
    result["disclaimer_ar"] = (
        "قرار إرشادي يجمع تحليل المنصّة. القرار النهائي لك — التربة الدقيقة "
        "والسوق المحلّي والخبرة الميدانيّة حاسمة. استشر هيئة البحوث والإرشاد."
    )
    return result


def _build_summary(zone_key, suited, analogs, chill, ec) -> str:
    """يبني ملخّص قرار نصّي متماسك."""
    parts = []
    crops = suited.get("suited_crops_ar") or []
    if crops:
        parts.append(f"الأنسب لإقليمك: {'، '.join(crops[:4])}")
    if analogs.get("applicable"):
        parts.append(
            "محاصيل صحراويّة استراتيجيّة مثبتة عالميّاً (نخيل/زيتون/رمّان/عنب) "
            "— توجّه لزراعة فاخرة عالية القيمة لا الكمّ المستنزف"
        )
    if chill.get("supported") and chill["estimated_chill_hours"] == 0:
        parts.append("تجنّب الأشجار المحتاجة للبرودة (تفاح) — لا برودة كافية")
    if not suited.get("rainfed_possible"):
        parts.append("الريّ ضروري — أدِر الماء بدقّة (تنقيط/عجز محسوب)")
    if ec is not None and ec >= 4:
        parts.append("راعِ الملوحة باختيار محاصيل وأصول متحمّلة")
    return ". ".join(parts) + "."


def _load_jawf_climate_ref() -> Optional[Dict]:
    """يحمّل ملخّص طقس الجوف الفعلي المرجعي (5 سنوات NASA POWER)، إن وُجد."""
    import json
    import os
    path = os.path.join(os.path.dirname(__file__), "..", "data",
                        "reference", "aljawf_climate_summary.json")
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
