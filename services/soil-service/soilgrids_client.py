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
# «لا بيانات تربة» بينما المزوّدُ يعمل — والمُدقِّق أعاد النداءَ بمهلة `40` فعادت
# بياناتٌ حقيقيّة. فالافتراضُ كان يُحوِّل بطءَ مزوّدٍ إلى غيابِ بيانات.
#
# رُفِع إلى `60` — أوسعَ من المقيس بهامشٍ معقول، ويبقى قابلاً للضبط بالبيئة.
# **حدُّ صدقٍ مُعلَن:** هذا يرفع سقفَ الانتظار ولا يُخفي البطء. والعلاجُ الأتمّ نقلُ
# الجلب إلى مهمّةٍ خلفيّةٍ بتخزينٍ مؤقّت — **لم تُنفّذه هذه الشريحة**.
SOILGRIDS_TIMEOUT = float(os.getenv("SOILGRIDS_TIMEOUT", "60").strip() or "60")

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


def fetch_soil_properties(lon: float, lat: float, *, client=None) -> dict | None:
    """يجلب خصائص تربة الطبقة العلويّة عند (lon, lat). None عند أيّ فشل (صدق).

    ``client``: عميل httpx اختياريّ للحقن (اختبار). حين None نُنشئ عميلاً مؤقّتاً.
    """
    try:
        import httpx
    except ImportError:  # pragma: no cover — httpx تبعيّة الخدمة
        return None

    params = [("lon", lon), ("lat", lat), ("depth", _TOP_DEPTH), ("value", "mean")]
    params += [("property", p) for p in _PROPS]

    def _do(cli) -> dict | None:
        try:
            resp = cli.get(SOILGRIDS_URL, params=params)
        except Exception:  # noqa: BLE001 — تعذّر وصول/مهلة ⇒ فشل ناعم
            return None
        if resp.status_code < 200 or resp.status_code >= 300:
            return None
        try:
            props = _extract(resp.json())
        except Exception:  # noqa: BLE001 — JSON شاذّ ⇒ فشل ناعم
            return None
        if not props:
            return None
        return {"source": "soilgrids", "lon": lon, "lat": lat, "properties": props}

    if client is not None:
        return _do(client)
    with httpx.Client(timeout=SOILGRIDS_TIMEOUT) as cli:
        return _do(cli)
