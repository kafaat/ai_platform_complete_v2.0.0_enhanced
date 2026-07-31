"""
field_intelligence_adapters.py — محوّلات المصادر الحيّة (HTTP).

تستبدل نقاط الحقن (mock) في field_intelligence_coordinator بنداءات HTTP
فعليّة للخدمات (weather/soil/raster). تُستدعى من endpoint التشغيل.

التصميم: كلّ محوّل دالّة تأخذ FieldRequest وتُرجِع dict خام أو None (متعذّر).
صدق: عند فشل/تعذّر الخدمة، تُرجِع None (يُعلَن كمصدر متعذّر) — لا تخترع بيانات.
المهلات وإعادة المحاولة محكومة؛ الأخطاء تُلتقَط ولا تُسقط الطلب كلّه.
"""

from __future__ import annotations

import os

from api.raster_service_client import (
    get_field_terrain_sync,
    get_indices_sync,
    get_provider_status_sync,
)

# عناوين الخدمات الداخليّة (قابلة للضبط من البيئة — افتراضات compose)
WEATHER_URL = os.getenv("WEATHER_SERVICE_URL", "http://sahool-weather-service:8000")
SOIL_URL = os.getenv("SOIL_SERVICE_URL", "http://sahool-soil-service:8000")
PLATFORM_URL = os.getenv("PLATFORM_SERVICE_URL", "http://sahool-platform:8000")
# بوّابة القرار المركزيّة (guardrails-engine /validate) — نفس افتراض supervisor-agent
# (main.py:72). كلّ قرار قابل للتنفيذ يجب أن يمرّ بها فعليّاً قبل أن يصير executable.
GUARDRAILS_URL = os.getenv("GUARDRAILS_URL", "http://sahool-guardrails-engine:8000")
HTTP_TIMEOUT = float(os.getenv("ADAPTER_TIMEOUT", "20.0"))

# راية تفعيل المحوّل الحيّ للحَوكمة (DEFAULT ON — هذه دعوة تفعيل صريحة). عند ضبطها
# "false" يُحذَف guardrails_fn من build_live_adapters ⇒ تبقى الحَوكمة not_evaluated
# ⇒ كلّ قرار استشاريّ فقط (executable=False) — رجوع آمن لسلوك ما قبل التفعيل بلا كود.
LIVE_GUARDRAILS_ENABLED = os.getenv("ENABLE_LIVE_GUARDRAILS", "true").strip().lower() != "false"


def _is_truthy(val: str | None) -> bool:
    """هل قيمة بيئة تعني التفعيل؟ (1/true/yes/on — بلا حساسيّة لحالة الأحرف)."""
    return (val or "").strip().lower() in {"1", "true", "yes", "on"}


def _auth_headers(authorization: str | None) -> dict | None:
    """رأس التفويض (Bearer) لتمريره للنقاط المحميّة بـJWT. None ⇒ بلا رأس."""
    return {"Authorization": authorization} if authorization else None


# توكن خدمة-لخدمة (X-Agent-Token == SAHOOL_AGENT_TOKEN) — تطلبه نقاط raster المحميّة
# بـ_require_service_token (مثل /indices الذي يغذّي sensing_adapter). بدونه تُرفَض
# النداءات (503/401) وتُبتلَع ⇒ تغذية الاستشعار ميتة صامتاً (نفس صنف خطأ imagery).
AGENT_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN", "")


def _get_json(
    url: str,
    params: dict | None = None,
    *,
    authorization: str | None = None,
    agent_token: str | None = None,
    tenant_id: str | None = None,
) -> dict | None:
    """نداء GET آمن — يُرجِع JSON أو None عند أيّ فشل (صدق: لا اختراع).

    يمرّر رأس التفويض (Bearer) و/أو توكن الخدمة (X-Agent-Token) و/أو المستأجِر الموثوق
    (X-Tenant-Id، نمط SEC-3: الهُويّة من البوّابة/المنصّة الموثوقة) إن وُجدت — النقاط
    المحميّة tenant-scoped تُرجِع لا صفوف بدونها ⇒ None/فارغ.
    """
    try:
        import httpx
    except ImportError:
        return None  # بيئة بلا httpx — يُعلَن كمتعذّر
    headers = _auth_headers(authorization) or {}
    if agent_token:
        headers["X-Agent-Token"] = agent_token
    if tenant_id:
        headers["X-Tenant-Id"] = str(tenant_id)
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            resp = client.get(url, params=params or {}, headers=headers or None)
            resp.raise_for_status()
            return resp.json()
    except Exception:  # noqa: BLE001 — أيّ فشل → متعذّر (لا نُسقط الطلب)
        return None


def fetch_provider_status(*, agent_token: str | None = None) -> dict | None:
    """يجلب حالة مزوّدي الصور عبر raster facade — آمن الفشل.

    P2.3: لا يفتح هذا المحوّل عنوان raster-service أو توكنه مباشرة.
    raster متعذّر/بلا httpx ⇒ ``None`` (⇒ ``provider_status`` في البطاقة يبقى missing
    بسبب صريح، لا اختلاق). بيانات وصفيّة غير حسّاسة.
    """
    return get_provider_status_sync(timeout_s=HTTP_TIMEOUT)


def fetch_soil_baseline(req, *, agent_token: str | None = None) -> dict | None:
    """يجلب خطّ أساس التربة (SoilGrids) من soil-service ``/v1/soil/soilgrids`` — آمن الفشل.

    يتطلّب lat/lon (خصائص نقطيّة). ``/v1/soil/soilgrids`` محميّ بـ``_require_service_token``
    ⇒ يُمرَّر ``agent_token`` (X-Agent-Token). أيّ تعذّر (بلا إحداثيّات/توكن/تغطية/شبكة)
    ⇒ ``None`` (⇒ ``soil_baseline`` في البطاقة يبقى missing بصدق، لا اختلاق).
    """
    if req.lat is None or req.lon is None:
        return None
    return _get_json(
        f"{SOIL_URL}/v1/soil/soilgrids",
        {"lon": req.lon, "lat": req.lat},
        agent_token=agent_token or AGENT_TOKEN,
    )


def fetch_terrain_summary(req, *, tenant_id: str | None = None) -> dict | None:
    """يجلب مُلخّص تضاريس الحقل عبر raster facade — آمن الفشل.

    النقطة tenant-scoped عبر ``X-Tenant-Id`` (المستأجِر الموثوق من المنصّة، نمط SEC-3)؛
    raster يشتقّ مضلّع الحقل ذاتيّاً ويقصّ داخله. أيّ تعذّر (raster/DEM/هندسة) ⇒ ``None``
    (⇒ قسم ``terrain`` في البطاقة يبقى missing بصدق، لا اختلاق). لا يُمرَّر tenant من الجسم.
    """
    return get_field_terrain_sync(req.field_id, tenant_id=tenant_id, timeout_s=HTTP_TIMEOUT)


def _post_json(
    url: str,
    payload: dict | None = None,
    *,
    authorization: str | None = None,
    agent_token: str | None = None,
) -> dict | None:
    """نداء POST آمن — يُرجِع JSON أو None عند أيّ فشل (صدق: لا اختراع).

    يمرّر رأس التفويض (Bearer) و/أو توكن الخدمة (X-Agent-Token) إن وُجدا — نقطة
    guardrails /validate محميّة بـ_require_service_token ⇒ بدونه 401/503 (⇒ None).
    """
    try:
        import httpx
    except ImportError:
        return None
    headers = _auth_headers(authorization) or {}
    if agent_token:
        headers["X-Agent-Token"] = agent_token
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            resp = client.post(url, json=payload or {}, headers=headers or None)
            resp.raise_for_status()
            return resp.json()
    except Exception:  # noqa: BLE001 — أيّ فشل → متعذّر
        return None


def weather_adapter(req) -> dict | None:
    """يجلب الطقس الحيّ من weather-service → {heat_risk, forecast_at}.

    weather-service هو مالك اتصال Open-Meteo والتطبيع. هذه الطبقة لا تضرب
    Open-Meteo مباشرة ولا تُعيد حساب ET0؛ هي adapter orchestration فقط.
    """
    if req.lat is None or req.lon is None:
        return None
    data = _get_json(
        f"{WEATHER_URL}/v1/weather/current",
        {"lat": req.lat, "lon": req.lon, "model": "best_match"},
        agent_token=AGENT_TOKEN,
        tenant_id=getattr(req, "tenant_id", None),
    )
    if not data:
        return None
    temp = data.get("temperature_c")
    heat_risk = None
    if isinstance(temp, (int, float)):
        heat_risk = max(0.0, min(1.0, (float(temp) - 30.0) / 15.0))
    return {
        "source": data.get("source", "weather-service"),
        "heat_risk": data.get("heat_stress_index", data.get("heat_risk", heat_risk)),
        "forecast_at": data.get("timestamp") or data.get("time"),
        "temperature_c": temp,
        "humidity_pct": data.get("humidity_pct"),
        "wind_speed_ms": data.get("wind_speed_ms"),
        "precipitation_mm": data.get("precipitation_mm"),
    }


def weather_forecast_adapter(req, *, authorization: str | None = None) -> dict | None:
    """يجلب توقع 7 أيام من weather-service. None عند التعذّر.

    يمنع نمط Platform fallback القديم: لا يوجد اتصال مباشر بـOpen-Meteo هنا؛
    الخدمة المختصة هي التي تملك provider/cache/ET0.
    """
    if _is_truthy(os.getenv("WEATHER_LIVE_DISABLED")):
        return None
    if req.lat is None or req.lon is None:
        return None
    data = _get_json(
        f"{WEATHER_URL}/v1/weather/forecast",
        {"lat": req.lat, "lon": req.lon, "days": 7, "model": "best_match"},
        authorization=authorization,
        agent_token=AGENT_TOKEN,
        tenant_id=getattr(req, "tenant_id", None),
    )
    if not data:
        return None
    daily = data.get("daily")
    if not isinstance(daily, list) or not daily:
        return None
    return {
        "source": data.get("source", "weather-service"),
        "forecast_at": daily[0].get("date") or data.get("time"),
        "elevation_m": data.get("elevation_m"),
        "daily": daily,
    }


def soil_adapter(req) -> dict | None:
    """يجلب تحليل التربة → {ec_dsm, sampled_at}. None عند التعذّر."""
    data = _get_json(f"{SOIL_URL}/api/v1/soil/{req.field_id}")
    if not data:
        return None
    return {"ec_dsm": data.get("ec_dsm", data.get("ec")), "sampled_at": data.get("sampled_at")}


def sensing_adapter(req) -> dict | None:
    """يجلب مؤشّرات الاستشعار → {ndvi, ndre, ...}. None عند التعذّر."""
    if req.lat is None or req.lon is None:
        return None
    data = get_indices_sync(req.field_id, lat=req.lat, lon=req.lon, timeout_s=HTTP_TIMEOUT)
    if not data:
        return None
    # تمرير المؤشّرات المتاحة فقط (الغائب يُعلَن في المايسترو)
    out = {}
    for k in ("ndvi", "ndre", "ndsi", "ndwi", "bsi", "si", "rvi"):
        if data.get(k) is not None:
            out[k] = data[k]
    out["resolution_m"] = data.get("resolution_m", 10.0)
    out["field_coverage"] = data.get("field_coverage")
    out["observed_at"] = data.get("observed_at")
    # غطاء السحب — يُمرَّر ليُفعّل تحويل الوزن للرادار في fuse_health (كان مفقوداً)
    if data.get("cloud_cover") is not None:
        out["cloud_cover"] = data["cloud_cover"]
    return out or None


def memory_adapter(req, *, authorization: str | None = None) -> dict | None:
    """يجلب السياق التاريخي للحقل (farm_memory) → {recurring_issues, ...}.

    Runtime Cohesion: يصل ذاكرة الحقل بحلقة القرار. يقرأ تاريخ الأحداث من
    خدمة المنصّة (events عبر event_replay)، يكشف القضايا المتكرّرة (ملوحة/
    إجهاد يتكرّر) لإغناء القرار. None عند التعذّر (صدق: لا تاريخ مخترَع).

    النقطة محميّة بـJWT ⇒ يجب تمرير authorization وإلّا تُرجِع 401 (⇒ None دائماً).
    """
    data = _get_json(
        f"{PLATFORM_URL}/api/v1/fields/{req.field_id}/history",
        {"tenant_id": req.tenant_id},
        authorization=authorization,
    )
    if not data:
        return None
    events = data.get("events", [])
    if not events:
        return {
            "recurring_issues": [],
            "total_events": 0,
            "note_ar": "لا تاريخ مسجّل بعد لهذا الحقل",
        }
    # كشف التكرار: قضايا ظهرت ≥ مرّتين في التاريخ (سياق للقرار)
    issue_counts: dict = {}
    for e in events:
        for tag in e.get("issue_tags") or []:
            issue_counts[tag] = issue_counts.get(tag, 0) + 1
    recurring = [k for k, v in issue_counts.items() if v >= 2]
    return {
        "recurring_issues": recurring,
        "total_events": len(events),
        "issue_counts": issue_counts,
    }


def simulate_adapter(req, decision, state, *, authorization: str | None = None) -> dict | None:
    """يشغّل محاكاة what-if لتقدير أثر الإجراء المقترَح على المحصول/الماء.

    Runtime Cohesion: يصل المحاكاة بحلقة القرار. يطلب من خدمة WOFOST محاكاة
    سيناريو (مثلاً: مع/بلا تدخّل) ويقارن. None عند التعذّر (لا أرقام مخترَعة).
    """
    crop = req.crop or "قمح صلب"
    payload = {
        "field_id": req.field_id,
        "crop": crop,
        "lat": req.lat,
        "lon": req.lon,
        "scenario": "recommended_action",  # الخدمة تفسّر القرار المقترَح
    }
    data = _post_json(
        f"{PLATFORM_URL}/api/v1/simulate/what-if", payload, authorization=authorization
    )
    if not data:
        return None
    # هل الإجراء المقترَح يُحسّن النتيجة فعلاً؟ (للقرار)
    baseline = data.get("baseline_yield_t_ha")
    with_action = data.get("action_yield_t_ha")
    helps = None
    if baseline is not None and with_action is not None:
        helps = with_action > baseline * 1.02  # تحسّن >2% يُعتبر مُجدياً
    return {
        "baseline_yield_t_ha": baseline,
        "action_yield_t_ha": with_action,
        "water_saved_mm": data.get("water_saved_mm"),
        "recommended_action_helps": helps,
    }


# ── محوّل الحَوكمة الحيّ (guardrails-engine /validate) — الأكثر حساسيّة للسلامة ──
#
# مبدأ حاكم: fail-closed. القرار لا يصير executable إلّا إذا أقرّت guardrails فعليّاً
# (allowed==True). أيّ غموض/خطأ/تعذّر ⇒ حالة ليست في GOVERNANCE_APPROVED_STATES ⇒
# يبقى استشاريّاً. لا نختلق موافقة أبداً.
#
# خريطة صريحة: نوع إجراء field-intelligence (decision["action_type"] أو قضيّة
# decision["structured"]["issue"]) → نوع إجراء guardrails. نُدرِج فقط التناظر السلاميّ
# **القاطع** الذي لا لبس فيه. أيّ نوع غير مُدرَج (تقييم/متابعة/استشارة) ⇒ لا إجراء سلامة
# حرج ⇒ not_applicable (يبقى executable=False — لا موافقة تلقائيّة).
#
# الحالة الراهنة لـ_derive_policy تُنتج action_type واحداً من اثنين فقط:
#   • "soil_remediation" (ملوحة حرجة، غسيل/صرف) → ماء ريّ → "irrigation"  [قاطع]
#   • "investigate_stress" (حيويّة منخفضة — افحص ميدانيّاً) → تقييم لا إجراء → not_applicable
# المداخل الأخرى (fertilization/pesticide/harvest) مُدرَجة استباقيّاً للتوافق إن أنتجها
# المنطق مستقبلاً؛ لا يُولّدها الكود اليوم.
_DECISION_TO_GUARDRAILS_ACTION: dict[str, str] = {
    # القاطع اليقينيّ اليوم: معالجة الملوحة بالغسيل = ماء ريّ ⇒ irrigation.
    "soil_remediation": "irrigation",
    "salinity": "irrigation",  # عبر structured["issue"]
    # توافق استباقيّ (لا يُنتجها _derive_policy حاليّاً، لكن التناظر قاطع إن وُجدت):
    "fertilization": "fertilization",
    "nutrient": "fertilization",
    "pesticide": "pesticide",
    "pest": "pesticide",
    "harvest": "harvest",
    "harvest_timing": "harvest",
    # صريح: قرار تقييميّ/استشاريّ بحت — لا إجراء سلامة حرج (يبقى استشاريّاً).
    "investigate_stress": "not_applicable",
    "monitor": "not_applicable",
    "investigate": "not_applicable",
}


def _map_decision_to_guardrails_action(decision: dict) -> str | None:
    """يُرجِع نوع إجراء guardrails القاطع لقرار field-intelligence، أو None.

    صدق + fail-closed: نطابق فقط حين يوجد تناظر سلاميّ **قاطع**. الأولويّة للـ
    action_type الصريح، ثمّ لقضيّة structured["issue"]. غياب أيّ تطابق ⇒ None
    (يُعامَل كـnot_applicable من المُنادي — لا موافقة). نتجاهل مداخل not_applicable
    المُدرَجة (نُرجِع None لها صراحةً) فلا تُرسَل أصلاً لـguardrails.
    """
    candidates: list[str] = []
    at = decision.get("action_type")
    if isinstance(at, str) and at:
        candidates.append(at.strip().lower())
    structured = decision.get("structured")
    if isinstance(structured, dict):
        issue = structured.get("issue")
        if isinstance(issue, str) and issue:
            candidates.append(issue.strip().lower())
    for key in candidates:
        mapped = _DECISION_TO_GUARDRAILS_ACTION.get(key)
        if mapped and mapped != "not_applicable":
            return mapped
    return None


def guardrails_adapter(decision: dict, state, *, authorization: str | None = None) -> dict:
    """محوّل الحَوكمة الحيّ — يُرجِع dict حَوكمة لـrun_field_intelligence (SYNC).

    عقد القيمة المُرجَعة (يُستهلَك في governance_permits_dispatch):
      • allowed==True   → {"status": "approved", ...}     → executable يصير True
      • allowed==False  → {"status": "halted", ...}       → NOT approved (False)
      • لا تناظر سلاميّ  → {"status": "not_applicable", ...} → NOT approved (False)
      • أيّ خطأ/تعذّر    → {"status": "error", ...}         → NOT approved (False)

    fail-closed مطلق: لا نُرجِع approved إلّا إذا أقرّت guardrails فعليّاً. لا نرفع
    استثناءً أبداً (المُنادي يلفّه أيضاً، لكنّنا دفاعيّون). غياب توكن الخدمة ⇒ خطأ.
    """
    try:
        action_type = _map_decision_to_guardrails_action(decision)
        if action_type is None:
            # قرار استشاريّ/تقييميّ بحت — لا إجراء سلامة حرج ⇒ يبقى استشاريّاً.
            # ملاحظة: not_applicable ليست في GOVERNANCE_APPROVED_STATES ⇒ executable=False.
            return {
                "status": "not_applicable",
                "note": "قرار استشاريّ/تقييميّ — لا إجراء سلامة حرج",
            }
        if not AGENT_TOKEN:
            # بلا توكن خدمة /validate يردّ 401/503 ويُبتلَع ⇒ نُعلنه صراحةً (fail-closed).
            return {
                "status": "error",
                "note": "SAHOOL_AGENT_TOKEN غير مضبوط — تعذّر التحقّق من الحَوكمة",
            }

        truths = getattr(state, "operational_truths", {}) or {}
        tenant_id = getattr(state, "tenant_id", None) or ""
        field_id = getattr(state, "field_id", None)

        # action_data: حمولة القرار المنظَّمة + توصياته (ما يُحكَم عليه).
        action_data: dict = {}
        structured = decision.get("structured")
        if isinstance(structured, dict):
            action_data.update(structured)
        recs = decision.get("recommendations_ar")
        if recs:
            action_data["recommendations_ar"] = recs

        # farm_context: حدّ أدنى من الحالة الموحّدة (مؤشّرات السلامة ذات الصلة).
        farm_context: dict = {
            "field_id": field_id,
            "tenant_id": tenant_id,
            "crop": getattr(state, "crop", None),
            "effective_status": truths.get("effective_status"),
            "salinity_class": truths.get("salinity_class"),
            "salinity_risk": truths.get("salinity_risk"),
            "crop_vigor": truths.get("crop_vigor"),
            "ndvi_trend": truths.get("ndvi_trend"),
            "growth_stage": truths.get("growth_stage") or truths.get("fao56_stage"),
        }
        # تنظيف None لتقليل ضوضاء السياق (لا يؤثّر على عقد الاكتمال — حقوله مختلفة).
        farm_context = {k: v for k, v in farm_context.items() if v is not None}

        payload = {
            "action_type": action_type,
            "action_data": action_data or {"advisory": True},
            "farm_context": farm_context,
            "user_id": "field-intelligence",
            "tenant_id": str(tenant_id),
            "request_source": "system",
            "auto_approve_low_risk": True,
        }

        result = _post_json(
            f"{GUARDRAILS_URL}/v1/validate",
            payload,
            authorization=authorization,
            agent_token=AGENT_TOKEN,
        )
        if not result:
            return {
                "status": "error",
                "note": "تعذّر الوصول لمحرّك الحَوكمة (/v1/validate) — استشاريّ فقط",
            }
        allowed = result.get("allowed")
        if allowed is True:
            return {
                "status": "approved",
                "overall_risk": result.get("overall_risk"),
                "tier_checks": result.get("tier_checks"),
                "requires_human_approval": result.get("requires_human_approval"),
                "action_type": action_type,
            }
        # allowed==False أو None/مجهول ⇒ NOT approved (fail-closed — لا نختلق موافقة).
        return {
            "status": "halted",
            "reason": result.get("arabic_explanation") or "لم تُقَرّ الحَوكمة",
            "overall_risk": result.get("overall_risk"),
            "tier_checks": result.get("tier_checks"),
            "requires_human_approval": result.get("requires_human_approval"),
            "action_type": action_type,
        }
    except Exception as e:  # noqa: BLE001 — دفاعيّ: لا نرفع أبداً من guardrails_fn
        return {"status": "error", "note": f"تعذّر التحقّق من الحَوكمة: {e}"}


def build_live_adapters(authorization: str | None = None) -> dict:
    """يُرجِع قاموس المحوّلات الحيّة لتمريرها لـrun_field_intelligence.

    authorization: رأس التفويض القادم من الطلب. يُمرَّر للمحوّلات المحميّة بـJWT
    (memory/simulate تنادي نقاط المنصّة المحميّة ⇒ بدونه تُرجِع 401 ثمّ None).
    الطقس/التربة/الاستشعار خدمات داخليّة لا تتطلّبه (تبقى كما هي).

    الحَوكمة الحيّة (الأكثر حساسيّة للسلامة): يُضاف guardrails_fn فقط حين
    LIVE_GUARDRAILS_ENABLED (افتراضيّاً مفعّل). عند تعطيله (ENABLE_LIVE_GUARDRAILS=
    false) يُحذَف guardrails_fn ⇒ تبقى الحَوكمة not_evaluated ⇒ كلّ قرار استشاريّ فقط
    (executable=False) — رجوع آمن لسلوك ما قبل التفعيل بلا تغيير كود.

    الاستخدام في endpoint:
        adapters = build_live_adapters(authorization=authorization)
        run_field_intelligence(req, **adapters, ...)
    """

    def memory_fn(req):
        return memory_adapter(req, authorization=authorization)

    def simulate_fn(req, decision, state):
        return simulate_adapter(req, decision, state, authorization=authorization)

    def forecast_fn(req):
        # التوقّع الحيّ (Open-Meteo، keyless) — يُجلَب فعليّاً في run_field_intelligence.
        return weather_forecast_adapter(req, authorization=authorization)

    adapters: dict = {
        "weather_fn": weather_adapter,
        "soil_fn": soil_adapter,
        "sensing_fn": sensing_adapter,
        "memory_fn": memory_fn,
        "simulate_fn": simulate_fn,
        "forecast_fn": forecast_fn,
    }

    # تفعيل الحَوكمة الحيّة (DEFAULT ON). غيابها ⇒ not_evaluated ⇒ استشاريّ فقط.
    if LIVE_GUARDRAILS_ENABLED:

        def guardrails_fn(decision, state):
            return guardrails_adapter(decision, state, authorization=authorization)

        adapters["guardrails_fn"] = guardrails_fn

    return adapters
