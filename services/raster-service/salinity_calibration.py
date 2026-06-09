"""
services/raster-service/salinity_calibration.py — معايرة مؤشّر الملوحة NDSI

البند ٢ من خطّة التنفيذ. المرجع: SOIL_INDICES_RESEARCH + بيانات السنيدار
الأرضيّة (sunaydar_soil_reference.yaml) + al_jawf/soil.yaml.

⚠️ ملاحظة صدق منهجيّة (الأهمّ):
المعايرة العلميّة الكاملة تحتاج أزواج (NDSI من القمر, EC مخبري) لنفس النقاط
بإحداثيّات GPS وتواريخ مطابقة لصور Sentinel. هذه البيانات **غير متوفّرة بعد**:
  - متوسّط EC ليس في ملفّ المرجع (pH/CaCO3/OM/P فقط)
  - 7 من 22 عيّنة تنقصها إحداثيّات GPS (لا تُطابَق بالقمر)
  - الحملتان استخدمتا طريقتين غير قابلتين للمقارنة (تخفيف 1:5 vs عجينة مشبعة)

لذلك هذه الوحدة **ليست انحدار معايرة مُلائَم (fitted regression)**، بل:
  ١. تصنيف نوعي لـNDSI مرتكز على نطاق ECe الموثّق للجوف [3.0–7.0] dS/m
  ٢. إطار يقبل أزواج (NDSI, EC) حقيقيّة لاحقاً لملاءمة انحدار فعلي
  ٣. تنبيهات مرتكزة على قيود التربة الموثّقة للسنيدار

عند جمعك عيّناتٍ بإحداثيّات + EC، استخدم fit_regression() لاستبدال
الـheuristic بانحدار حقيقي مُعاير محلّيّاً.
"""
from __future__ import annotations
from typing import Optional


# نطاق ECe الموثّق للجوف (من districts/al_jawf/soil.yaml + دراسة القمح)
ALJAWF_ECE_RANGE_DS_M = (3.0, 7.0)   # ميل للملوحة (saline tendency)

# عتبات NDSI → صنف ملوحة (heuristic إقليمي، ليس انحداراً مُلائَماً)
# المرجع: SOIL_INDICES_RESEARCH (NDSI > 0.1 ملوحة عالية، < 0 غير متأثّرة)
# مُرتكز على أنّ الجوف ضمن نطاق ECe 3–7، فالعتبات معدّلة لهذا السياق.
NDSI_SALINITY_CLASSES = [
    # (حدّ أدنى NDSI, الصنف, ECe تقديري dS/m, الإجراء)
    (0.15,  "high",      "> 6",     "ملوحة عالية — ريّ غسيل + تصريف عاجل"),
    (0.05,  "moderate",  "4 – 6",   "ملوحة متوسّطة — ريّ تنقيط + تجنّب الترسّب"),
    (-0.05, "low",       "3 – 4",   "ملوحة منخفضة — مراقبة دوريّة"),
    (-1.0,  "none",      "< 3",     "غير متأثّرة بالملوحة"),
]


def classify_ndsi_salinity(ndsi_value: float) -> dict:
    """يصنّف قيمة NDSI لصنف ملوحة (heuristic إقليمي للجوف).

    ⚠️ تقديري: تصنيف نوعي مرتكز على نطاق ECe الموثّق، ليس قياساً مخبريّاً.
    استخدمه للتنبيه والترتيب، لا كبديل عن تحليل EC مخبري.
    """
    for threshold, cls, ece_est, action in NDSI_SALINITY_CLASSES:
        if ndsi_value >= threshold:
            return {
                "ndsi": round(ndsi_value, 4),
                "salinity_class": cls,
                "ece_estimate_ds_m": ece_est,
                "action_ar": action,
                "is_estimate": True,
                "method": "regional_heuristic_aljawf",
                "note": "تقديري إقليمي — يحتاج تأكيد EC مخبري للقرار النهائي",
            }
    # لن يصل هنا (آخر عتبة -1.0 تلتقط الكلّ)
    return {"ndsi": ndsi_value, "salinity_class": "unknown", "is_estimate": True}


def fit_regression(samples: list[dict]) -> dict:
    """يلائم انحدار خطّي NDSI→ECe من أزواج حقيقيّة (عند توفّرها).

    samples: [{"ndsi": float, "ece_ds_m": float, "extraction_method": str}, ...]

    ⚠️ شروط الصحّة (يفرضها الكود):
      - 5 أزواج على الأقلّ (وإلّا الانحدار بلا معنى إحصائي)
      - طريقة استخلاص موحّدة (لا خلط 1:5 مع عجينة مشبعة)
    يُرجع المعاملات + R² ليحلّ محلّ الـheuristic عند جودة كافية.
    """
    if len(samples) < 5:
        return {"fitted": False,
                "reason": f"عيّنات غير كافية ({len(samples)} < 5) — استمرّ بالـheuristic"}

    methods = {s.get("extraction_method", "unknown") for s in samples}
    if len(methods) > 1:
        return {"fitted": False,
                "reason": f"طرق استخلاص مختلطة {methods} — وحّدها أوّلاً (1:5 vs عجينة مشبعة غير قابلة للمقارنة)"}

    # انحدار خطّي بسيط (least squares) بلا numpy — يعمل في أيّ بيئة
    xs = [s["ndsi"] for s in samples]
    ys = [s["ece_ds_m"] for s in samples]
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx == 0:
        return {"fitted": False, "reason": "تباين NDSI صفر — لا يمكن الملاءمة"}
    slope = sxy / sxx
    intercept = my - slope * mx
    # R²
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    return {
        "fitted": True,
        "model": "ece_ds_m = slope * NDSI + intercept",
        "slope": round(slope, 4),
        "intercept": round(intercept, 4),
        "r_squared": round(r2, 4),
        "n_samples": n,
        "extraction_method": methods.pop(),
        "quality": "good" if r2 >= 0.6 else "weak — اجمع عيّنات أكثر",
        "note": "انحدار محلّي مُعاير — يحلّ محلّ الـheuristic عند R²≥0.6",
    }


def predict_ece(ndsi_value: float, regression: Optional[dict] = None) -> dict:
    """يتنبّأ بـECe من NDSI: يستخدم الانحدار المُلائَم إن توفّر بجودة كافية،
    وإلّا يقع على الـheuristic الإقليمي."""
    if regression and regression.get("fitted") and regression.get("r_squared", 0) >= 0.6:
        ece = regression["slope"] * ndsi_value + regression["intercept"]
        return {
            "ndsi": round(ndsi_value, 4),
            "ece_predicted_ds_m": round(max(0.0, ece), 2),
            "method": "fitted_regression",
            "r_squared": regression["r_squared"],
            "is_estimate": True,
            "note": "من انحدار محلّي مُعاير — أدقّ من الـheuristic لكن يبقى تقديريّاً",
        }
    # وقوع على الـheuristic
    return classify_ndsi_salinity(ndsi_value)
