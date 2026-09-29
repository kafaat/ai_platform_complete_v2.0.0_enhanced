"""soilgrids_client.py — استيعاب خصائص التربة من SoilGrids (ISRIC، بيانات CC-BY 4.0).

يسدّ فجوة: لا مصدر تربة عالميّ في المنصّة. SoilGrids يوفّر خصائص تربة عالميّة 250م
مجّاناً (طين/رمل/غرين/pH/الكربون العضويّ/السعة التبادليّة) لأيّ إحداثيّة — مفيد حين
لا حسّاسات أرضيّة. **فشل ناعم**: أيّ خطأ/تعذّر وصول ⇒ ``None`` (صدق، لا اختراع قيمة).

الوحدات (تحويل من ترميز SoilGrids إلى وحدات مألوفة):
  • clay/sand/silt: g/kg ÷ 10 ⇒ نسبة مئويّة.
  • phh2o: (pH×10) ÷ 10 ⇒ pH.
  • soc (كربون عضويّ): dg/kg ÷ 100 ⇒ %.
  • cec (سعة تبادل كاتيونيّ): mmol(c)/kg (كما هي).

نقيّ الاعتماد على httpx (قابل للحقن للاختبار). الطبقة العلويّة (0–5سم) هي المُستعمَلة.
"""

from __future__ import annotations

import os

SOILGRIDS_URL = os.getenv(
    "SOILGRIDS_URL", "https://rest.isric.org/soilgrids/v2.0/properties/query"
).rstrip("/")
# **العطلُ الذي وُجِد هذا لأجله** (تدقيق v25، 2026-09-24): كان الافتراضُ `12` ثانيةً،
# وزمنُ استجابة ISRIC الحقيقيُّ المقيس ~`41` ثانية. فكلُّ جلبٍ حيٍّ ينتهي بمهلةٍ ويُقرَأ
# «لا بيانات تربة» بينما المزوّدُ يعمل.
#
# **وقياسُ Railway staging (2026-09-29) أبطل `60` أيضاً:** نقطةٌ زراعيّة (وادي زبيد
# 43.33,14.2) لم تُجِب ISRIC عنها في `90` ثانيةً مباشرةً، والخدمةُ أعادت 503 عند
# `60.6`ث. فالزمنُ متغيّرٌ بعُرض (5ث–32ث لنقطةٍ مُقنَّعة، >90ث لنقطةٍ حقيقيّة).
#
# لذلك صار الجلبُ **خلفيّاً** (``soilgrids_cache``) لا يحجز طلباً، وصارت المهلةُ حدَّ
# خيطٍ خلفيٍّ لا حدَّ انتظارِ مستدعٍ. `120` **حدٌّ لا قياس**: المقيسُ أنّ 90 لم تكفِ،
# ولا يُعرَف أنّ 120 تكفي.
SOILGRIDS_TIMEOUT = float(os.getenv("SOILGRIDS_TIMEOUT", "120").strip() or "120")

# نتائجُ الاستعلام. «لا تغطية» ليست «تعذّراً»: ISRIC يُجيب 200 وكلُّ القيم ``null``
# لأرضٍ مُقنَّعة (حضريّة/صخريّة/مائيّة) — قِيس حيّاً على صنعاء (44.2,15.35). وكانت
# الخدمةُ تُبلِّغ عنها «تعذّر الوصول»، فيُقرَأ غيابُ تغطيةٍ دائمٌ عطلاً عابراً يُعاد.
OK = "ok"
NO_COVERAGE = "no_coverage"
UNAVAILABLE = "unavailable"

# خصائص SoilGrids المطلوبة ومعامل التحويل لوحدة مألوفة (القسمة).
_PROPS = {
    "clay": ("clay_pct", 10.0),
    "sand": ("sand_pct", 10.0),
    "silt": ("silt_pct", 10.0),
    "phh2o": ("ph", 10.0),
    "soc": ("soc_pct", 100.0),
    "cec": ("cec", 1.0),
}
_TOP_DEPTH = "0-5cm"


def _extract(payload: dict) -> dict | None:
    """يستخرج قيم الطبقة العلويّة (0–5سم، mean) من ردّ SoilGrids ويحوّل وحداتها.

    يتسامح مع غياب خاصّية (يتخطّاها). يُعيد None إن لم تُستخرَج أيّ خاصيّة (ردّ فارغ/شاذّ).
    """
    layers = (((payload or {}).get("properties") or {}).get("layers")) or []
    out: dict[str, float] = {}
    for layer in layers:
        name = layer.get("name")
        spec = _PROPS.get(name)
        if not spec:
            continue
        out_key, divisor = spec
        for depth in layer.get("depths") or []:
            if depth.get("label") != _TOP_DEPTH:
                continue
            mean = (depth.get("values") or {}).get("mean")
            if isinstance(mean, (int, float)):
                out[out_key] = round(mean / divisor, 3)
            break
    return out or None


def _is_masked(payload: dict) -> bool:
    """ردٌّ سليمُ البنية يحمل طبقاتنا المطلوبة وكلُّ قِيَم الطبقة العلويّة فيه ``null``.

    هذا شكلُ «لا تغطية» كما عاد حيّاً من ISRIC — لا ردٌّ شاذّ. طبقاتٌ غائبة أو بلا
    عمقٍ علويّ ليست «لا تغطية» بل بنيةٌ لا نفهمها (``malformed``).
    """
    layers = (((payload or {}).get("properties") or {}).get("layers")) or []
    seen = False
    for layer in layers:
        if layer.get("name") not in _PROPS:
            continue
        for depth in layer.get("depths") or []:
            if depth.get("label") != _TOP_DEPTH:
                continue
            seen = True
            if (depth.get("values") or {}).get("mean") is not None:
                return False
    return seen


def query_soil_properties(lon: float, lat: float, *, client=None) -> dict:
    """يستعلم SoilGrids ويُصنِّف النتيجة — لا يرمي، ولا يخلط بين الأصناف.

    يُرجِع أحدَ ثلاثة:
      • ``{"outcome": "ok", "data": {...}}``
      • ``{"outcome": "no_coverage"}`` — ISRIC أجاب وليس لديه قيمٌ هنا (دائم).
      • ``{"outcome": "unavailable", "reason": ...}`` — ``timeout`` · ``unreachable`` ·
        ``http_<code>`` · ``malformed`` (عابرٌ غالباً). لا يُسرِّب العنوانَ ولا نصَّ الخطأ.

    ``client``: عميل httpx اختياريّ للحقن (اختبار). حين None نُنشئ عميلاً مؤقّتاً.
    """
    try:
        import httpx
    except ImportError:  # pragma: no cover — httpx تبعيّة الخدمة
        return {"outcome": UNAVAILABLE, "reason": "unreachable"}

    params = [("lon", lon), ("lat", lat), ("depth", _TOP_DEPTH), ("value", "mean")]
    params += [("property", p) for p in _PROPS]

    def _do(cli) -> dict:
        try:
            resp = cli.get(SOILGRIDS_URL, params=params)
        except httpx.TimeoutException:
            return {"outcome": UNAVAILABLE, "reason": "timeout"}
        except Exception:  # noqa: BLE001 — تعذّر وصول ⇒ فشل ناعم مُصنَّف
            return {"outcome": UNAVAILABLE, "reason": "unreachable"}
        if resp.status_code < 200 or resp.status_code >= 300:
            return {"outcome": UNAVAILABLE, "reason": f"http_{resp.status_code}"}
        try:
            payload = resp.json()
            props = _extract(payload)
        except Exception:  # noqa: BLE001 — JSON شاذّ ⇒ فشل ناعم مُصنَّف
            return {"outcome": UNAVAILABLE, "reason": "malformed"}
        if props:
            data = {"source": "soilgrids", "lon": lon, "lat": lat, "properties": props}
            return {"outcome": OK, "data": data}
        if _is_masked(payload):
            return {"outcome": NO_COVERAGE}
        return {"outcome": UNAVAILABLE, "reason": "malformed"}

    if client is not None:
        return _do(client)
    with httpx.Client(timeout=SOILGRIDS_TIMEOUT) as cli:
        return _do(cli)


def fetch_soil_properties(lon: float, lat: float, *, client=None) -> dict | None:
    """توافقٌ لمن يريد البيانات أو ``None`` فقط (صدق: لا اختراع). يُسقِط التصنيف —
    فمن يحتاج التمييزَ بين «لا تغطية» و«متعذّر» يستعمل ``query_soil_properties``."""
    result = query_soil_properties(lon, lat, client=client)
    return result["data"] if result["outcome"] == OK else None
